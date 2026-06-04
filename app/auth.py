import os
import re
import hashlib
import secrets
import json
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, session, redirect, render_template

from app.kv_client import redis_get, redis_set, redis_incr
from app.rate_limit import rate_limit
from app.constants import DEFAULT_DAILY_LIMIT, PBKDF2_ITERATIONS, MIN_PASSWORD_LENGTH

auth_bp = Blueprint("auth", __name__)

PBKDF2_PREFIX = "pbkdf2:sha256:"


def _get_user_limit(user_id):
    """Get daily translation limit for a user based on their subscription plan."""
    raw = redis_get(f"sub:{user_id}")
    if raw:
        try:
            import json as _json
            sub = _json.loads(raw)
            return int(sub.get("translations_per_day", DEFAULT_DAILY_LIMIT))
        except Exception:
            pass
    return DEFAULT_DAILY_LIMIT


def _hash_password(password, salt=None):
    """Hash password with PBKDF2-SHA256 (600k iterations)."""
    if salt is None:
        salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), PBKDF2_ITERATIONS)
    return f"{PBKDF2_PREFIX}{PBKDF2_ITERATIONS}:{salt}:{dk.hex()}"


def _verify_password(stored, password):
    """Verify password. Supports new PBKDF2 format and legacy SHA-256 format."""
    if not stored:
        return False
    try:
        if stored.startswith(PBKDF2_PREFIX):
            _, _, _, salt, dk_hex = stored.split(":", 4)
            iterations = int(stored.split(":")[2])
            dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations)
            return dk.hex() == dk_hex
        else:
            # Legacy SHA-256 format: "salt:hash"
            salt, _ = stored.split(":", 1)
            h = hashlib.sha256((salt + password).encode()).hexdigest()
            return f"{salt}:{h}" == stored
    except (ValueError, AttributeError, IndexError):
        return False


def _needs_rehash(stored):
    """Check if password hash needs upgrade to PBKDF2."""
    return stored and not stored.startswith(PBKDF2_PREFIX)


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
    limit = _get_user_limit(user_id)
    try:
        count = redis_incr(key)
        if count == 1:
            redis_set(key, "1", ex=86400)
    except Exception:
        return True
    if isinstance(count, int) and count > limit:
        return False
    return True


@auth_bp.route("/login")
def login_page():
    return render_template("login.html")


@auth_bp.route("/logout")
def logout():
    session.pop("user_id", None)
    session.pop("username", None)
    return redirect("/")


@auth_bp.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json()
    username = (data.get("username", "") or "").strip().lower()
    password = (data.get("password", "") or "").strip()

    if not re.match(r"^[a-z0-9_]{3,20}$", username):
        return jsonify({"error": "用户名需3-20位字母、数字或下划线"}), 400
    if len(password) < MIN_PASSWORD_LENGTH:
        return jsonify({"error": f"密码至少{MIN_PASSWORD_LENGTH}位"}), 400

    user_key = f"user:{username}"
    try:
        existing = redis_get(user_key)
    except Exception:
        existing = None

    if existing:
        return jsonify({"error": "该用户名已被注册"}), 409

    try:
        redis_set(user_key, json.dumps({
            "username": username,
            "password": _hash_password(password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False))
    except Exception as e:
        return jsonify({"error": "注册失败，请稍后重试"}), 500

    session["user_id"] = username
    session["username"] = username
    return jsonify({"success": True, "redirect": "/console"})


@auth_bp.route("/api/auth/login", methods=["POST"])
@rate_limit("login")
def login_api():
    data = request.get_json()
    username = (data.get("username", "") or "").strip().lower()
    password = (data.get("password", "") or "").strip()

    if not username or not password:
        return jsonify({"error": "请输入用户名和密码"}), 400

    user_key = f"user:{username}"
    try:
        raw = redis_get(user_key)
    except Exception:
        raw = None

    if not raw:
        return jsonify({"error": "用户名或密码错误"}), 400

    import json as _json
    try:
        user = _json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "账户数据异常，请联系客服"}), 500

    stored_pw = user.get("password", "")
    if not _verify_password(stored_pw, password):
        return jsonify({"error": "用户名或密码错误"}), 400

    # Auto-upgrade legacy SHA-256 hash to PBKDF2
    if _needs_rehash(stored_pw):
        user["password"] = _hash_password(password)
        try:
            redis_set(user_key, _json.dumps(user, ensure_ascii=False))
        except Exception:
            pass

    session["user_id"] = username
    session["username"] = username
    return jsonify({"success": True, "redirect": "/console"})


@auth_bp.route("/api/auth/me")
def me():
    if "user_id" not in session:
        return jsonify({"authenticated": False})

    username = session["user_id"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = redis_get(f"rate:{username}:{today}")
    return jsonify({
        "authenticated": True,
        "username": session.get("username", username),
        "usage": {
            "today": int(count) if count else 0,
            "limit": _get_user_limit(username),
        },
    })
