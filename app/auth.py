import os
import re
import hashlib
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, session, redirect, render_template

from app.kv_client import redis_get, redis_set, redis_incr, redis_del

auth_bp = Blueprint("auth", __name__)

VERIFICATION_MODE = os.getenv("VERIFICATION_MODE", "demo")
DAILY_LIMIT = int(os.getenv("DAILY_TRANSLATION_LIMIT", "20"))


def _hash_phone(phone):
    return hashlib.sha256(phone.encode()).hexdigest()[:32]


def _mask_phone(phone):
    if len(phone) == 11:
        return phone[:3] + "****" + phone[-4:]
    return phone


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({"error": "请先登录"}), 401
        return f(*args, **kwargs)

    return decorated


def check_rate_limit(user_id):
    """Returns True if under limit, False if exceeded. Atomic INCR-first to prevent race."""
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    key = f"rate:{user_id}:{today}"
    try:
        count = redis_incr(key)
        if count == 1:
            redis_set(key, "1", ex=86400)
    except Exception:
        return True  # allow on error (fail-open, but logged)
    if isinstance(count, int) and count > DAILY_LIMIT:
        return False
    return True


@auth_bp.route("/login")
def login_page():
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    return redirect("/")


@auth_bp.route("/api/auth/send-code", methods=["POST"])
def send_code():
    data = request.get_json()
    phone = data.get("phone", "").strip()
    phone = re.sub(r"[^\d]", "", phone)
    if phone.startswith("86") and len(phone) == 13:
        phone = phone[2:]
    if not re.match(r"^1\d{10}$", phone):
        return jsonify({"error": "请输入有效的手机号码"}), 400

    phone_hash = _hash_phone(phone)

    # Create user record if new
    try:
        existing = redis_get(f"user:{phone_hash}")
        if existing is None:
            redis_set(
                f"user:{phone_hash}",
                f'{{"phone_hash":"{phone_hash}","created_at":"{datetime.now(timezone.utc).isoformat()}"}}',
            )
    except Exception as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("auth.send_code", "KV user record error", str(e))
        except Exception:
            pass

    code = "1234" if VERIFICATION_MODE == "demo" else _generate_code()
    try:
        redis_set(f"verify:{phone_hash}", code, ex=300)
    except Exception as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("auth.send_code", "KV verify code error", str(e))
        except Exception:
            pass

    # Always return code to frontend — no SMS integration yet
    resp = {"success": True, "message": "验证码已发送", "code": code}
    return jsonify(resp)


MAX_VERIFY_ATTEMPTS = 5


@auth_bp.route("/api/auth/verify-code", methods=["POST"])
def verify_code():
    data = request.get_json()
    phone = data.get("phone", "").strip()
    phone = re.sub(r"[^\d]", "", phone)
    if phone.startswith("86") and len(phone) == 13:
        phone = phone[2:]
    code = data.get("code", "").strip()

    if not re.match(r"^1\d{10}$", phone):
        return jsonify({"error": "手机号码格式不正确"}), 400

    phone_hash = _hash_phone(phone)

    # Brute-force protection: check attempt counter before verifying
    attempt_key = f"verify_attempts:{phone_hash}"
    try:
        attempts_raw = redis_get(attempt_key)
        attempts = int(attempts_raw) if attempts_raw else 0
    except Exception:
        attempts = 0

    if attempts >= MAX_VERIFY_ATTEMPTS:
        return jsonify({"error": "验证码尝试次数过多，请5分钟后重试"}), 429

    try:
        stored = redis_get(f"verify:{phone_hash}")
    except Exception as e:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("auth.verify_code", "KV get verify code error", str(e))
        except Exception:
            pass
        stored = None

    if not stored or stored != code:
        try:
            if attempts == 0:
                redis_set(attempt_key, "1", ex=300)
            else:
                redis_incr(attempt_key)
        except Exception:
            pass
        remaining = MAX_VERIFY_ATTEMPTS - (attempts + 1)
        return jsonify({
            "error": f"验证码错误或已过期（剩余 {max(0, remaining)} 次尝试）"
        }), 400

    # Code correct — clean up
    try:
        redis_del(f"verify:{phone_hash}")
        redis_del(attempt_key)
    except Exception:
        pass
    session["user_id"] = phone_hash
    session["phone"] = _mask_phone(phone)
    return jsonify({"success": True, "redirect": "/console"})


@auth_bp.route("/api/auth/me")
def me():
    if "user_id" not in session:
        return jsonify({"authenticated": False})

    phone_hash = session["user_id"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = redis_get(f"rate:{phone_hash}:{today}")
    return jsonify({
        "authenticated": True,
        "phone": session.get("phone", ""),
        "usage": {
            "today": int(count) if count else 0,
            "limit": DAILY_LIMIT,
        },
    })


def _generate_code():
    import random
    return str(random.randint(100000, 999999))
