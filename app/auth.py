import os
import re
import hashlib
import secrets
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, request, jsonify, session, redirect, render_template

from app.kv_client import redis_get, redis_set, redis_incr

auth_bp = Blueprint("auth", __name__)

DAILY_LIMIT = int(os.getenv("DAILY_TRANSLATION_LIMIT", "20"))


def _hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + password).encode()).hexdigest()
    return f"{salt}:{h}"


def _verify_password(stored, password):
    try:
        salt, _ = stored.split(":", 1)
    except (ValueError, AttributeError):
        return False
    return _hash_password(password, salt) == stored


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
        return True
    if isinstance(count, int) and count > DAILY_LIMIT:
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
    if len(password) < 6:
        return jsonify({"error": "密码至少6位"}), 400

    user_key = f"user:{username}"
    try:
        existing = redis_get(user_key)
    except Exception:
        existing = None

    if existing:
        return jsonify({"error": "该用户名已被注册"}), 409

    import json
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

    import json
    try:
        user = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"error": "账户数据异常，请联系客服"}), 500

    if not _verify_password(user.get("password", ""), password):
        return jsonify({"error": "用户名或密码错误"}), 400

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
            "limit": DAILY_LIMIT,
        },
    })
