import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from flask import Blueprint, request, jsonify, session, render_template

from app.auth import login_required
from app.kv_client import redis_get, redis_set, redis_keys, redis_del
from app.merchant import SUBSCRIPTION_PLANS

beta_bp = Blueprint("beta", __name__)

MAX_ERROR_LOG = 100


def log_error_to_kv(module, message, details=""):
    try:
        raw = redis_get("system:error_log")
        try:
            errors = json.loads(raw) if raw else []
        except (json.JSONDecodeError, TypeError):
            errors = []

        errors.append({
            "module": module,
            "message": str(message)[:500],
            "details": str(details)[:500],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        if len(errors) > MAX_ERROR_LOG:
            errors = errors[-MAX_ERROR_LOG:]

        redis_set("system:error_log", json.dumps(errors, ensure_ascii=False))
    except Exception:
        pass


@beta_bp.route("/api/health", methods=["GET"])
def health_check():
    results = {
        "deepseek_api": {"status": "unknown"},
        "kv_storage": {"status": "unknown"},
        "session": {"status": "ok"},
        "app": "国际宾客支持",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        results["deepseek_api"] = {"status": "error", "message": "DEEPSEEK_API_KEY 未配置"}
    else:
        try:
            req_body = json.dumps({
                "model": "deepseek-chat",
                "messages": [{"role": "user", "content": "health"}],
                "max_tokens": 10,
            }).encode("utf-8")
            req = Request(
                "https://api.deepseek.com/v1/chat/completions",
                data=req_body,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {api_key}",
                },
            )
            start = time.time()
            with urlopen(req, timeout=10) as r:
                json.loads(r.read().decode("utf-8"))
            latency = round((time.time() - start) * 1000)
            results["deepseek_api"] = {
                "status": "ok",
                "latency_ms": latency,
                "model": "deepseek-chat",
            }
        except Exception as e:
            results["deepseek_api"] = {"status": "error", "message": str(e)[:200]}

    try:
        test_key = "health:test"
        test_val = f"health_{int(time.time())}"
        redis_set(test_key, test_val, ex=60)
        read_back = redis_get(test_key)
        if read_back == test_val:
            upstash_url = os.getenv("UPSTASH_REDIS_REST_URL", "")
            backend = "redis" if upstash_url else "session"
            results["kv_storage"] = {"status": "ok", "backend": backend}
        else:
            results["kv_storage"] = {"status": "error", "message": "读写不一致"}
    except Exception as e:
        results["kv_storage"] = {"status": "error", "message": str(e)[:200]}

    try:
        session["health_test"] = True
        results["session"]["status"] = "ok"
    except Exception:
        results["session"]["status"] = "error"

    all_ok = all(
        v.get("status") == "ok" for v in results.values() if isinstance(v, dict)
    )
    results["status"] = "healthy" if all_ok else "degraded"

    return jsonify(results)


@beta_bp.route("/beta/feedback")
def feedback_page():
    return render_template("beta_feedback.html")


@beta_bp.route("/api/beta/feedback", methods=["POST"])
@login_required
def submit_feedback():
    user_id = session["user_id"]
    data = request.get_json()

    category = (data.get("category", "") or "").strip()
    content = (data.get("content", "") or "").strip()

    if not content:
        return jsonify({"error": "请输入反馈内容"}), 400
    if len(content) < 5:
        return jsonify({"error": "反馈内容太短，至少5个字"}), 400

    feedback_data = {
        "user_id": user_id,
        "category": category or "通用",
        "content": content,
        "contact": (data.get("contact", "") or "").strip(),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    redis_set(
        f"feedback:{user_id}:{int(time.time())}",
        json.dumps(feedback_data, ensure_ascii=False),
        ex=7776000,
    )

    return jsonify({"success": True, "message": "感谢您的反馈！我们会认真查看每一条建议。"})


@beta_bp.route("/api/beta/feedback", methods=["GET"])
@login_required
def list_feedback():
    user_id = session["user_id"]
    feedbacks = []
    try:
        keys = redis_keys(f"feedback:{user_id}:*") or []
    except Exception:
        keys = []
    for key in sorted(keys, reverse=True)[:50]:
        raw = redis_get(key)
        if raw:
            try:
                feedbacks.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                pass
    return jsonify({"feedbacks": feedbacks})


@beta_bp.route("/api/admin/errors", methods=["GET"])
def admin_errors():
    err = _require_admin()
    if err:
        return err

    try:
        raw = redis_get("system:error_log")
        errors = json.loads(raw) if raw else []
    except Exception:
        errors = []

    return jsonify({"errors": errors, "total": len(errors)})


_admin_token = "admin123456"  # 默认密码，登录后建议修改


@beta_bp.route("/api/admin/check")
def admin_check():
    return jsonify({"token_set": True})


def _get_admin_token():
    return _admin_token


def _set_admin_token(val):
    global _admin_token
    _admin_token = val.strip()
    redis_set("system:admin_token", _admin_token)


def _require_admin():
    admin_token = _get_admin_token()
    if admin_token:
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if token == admin_token:
            return None
        return jsonify({"error": "unauthorized"}), 401

    # No token configured — fallback to localhost
    if request.remote_addr not in ("127.0.0.1", "::1", "localhost"):
        return jsonify({"error": "unauthorized"}), 401
    return None


@beta_bp.route("/api/admin/setup", methods=["POST"])
def admin_setup():
    """First-time admin token setup. Open when no token exists yet."""
    existing = _get_admin_token()
    if existing:
        err = _require_admin()
        if err:
            return err

    data = request.get_json()
    if not data or not data.get("token", "").strip():
        return jsonify({"error": "请提供 token"}), 400

    _set_admin_token(data["token"].strip())
    return jsonify({"success": True, "message": "Admin token 已设置"})


@beta_bp.route("/api/admin/upgrade", methods=["POST"])
def admin_upgrade():
    err = _require_admin()
    if err:
        return err

    data = request.get_json()
    if not data:
        return jsonify({"error": "请求体不能为空"}), 400
    user_id = data.get("user_id", "").strip()
    plan_slug = data.get("plan", "").strip()

    if not user_id:
        return jsonify({"error": "缺少 user_id"}), 400
    if plan_slug not in SUBSCRIPTION_PLANS:
        return jsonify({"error": f"无效套餐，可选: {', '.join(SUBSCRIPTION_PLANS.keys())}"}), 400

    from datetime import datetime, timezone, timedelta

    plan = SUBSCRIPTION_PLANS[plan_slug]
    expires_at = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    sub_data = {
        "plan": plan_slug,
        "name": plan.get("name", ""),
        "features": plan.get("features", []),
        "translations_per_day": plan.get("translations_per_day", 20),
        "expires_at": expires_at,
        "upgraded_by_admin": datetime.now(timezone.utc).isoformat(),
    }

    redis_set(f"sub:{user_id}", json.dumps(sub_data, ensure_ascii=False))
    return jsonify({"success": True, "user_id": user_id, "plan": plan_slug, "expires_at": expires_at})


@beta_bp.route("/api/admin/users", methods=["GET"])
def admin_users():
    err = _require_admin()
    if err:
        return err

    sub_keys = redis_keys("sub:*")
    users = []
    for key in (sub_keys or []):
        uid = key.replace("sub:", "")
        raw = redis_get(key)
        plan = ""
        if raw:
            try:
                plan = json.loads(raw).get("plan", "")
            except (json.JSONDecodeError, TypeError):
                pass
        users.append({"user_id": uid, "plan": plan or "free"})
    return jsonify({"users": users, "total": len(users)})


@beta_bp.route("/admin")
def admin_page():
    from flask import render_template
    return render_template("admin.html")


@beta_bp.route("/api/seed/leschan/<key>")
def seed_leschan(key):
    """Temporary: seed merchant data for leschan account. Remove after use."""
    if key != "seed_2026_yangshuo":
        return jsonify({"error": "invalid key"}), 403

    import json as _json

    import hashlib, secrets
    def _hash(pw):
        salt = secrets.token_hex(16)
        return salt + ":" + hashlib.sha256((salt + pw).encode()).hexdigest()
    pwhash = _hash("200115")

    # Create user
    redis_set("user:leschan", _json.dumps({
        "username": "leschan",
        "password": pwhash,
        "created_at": "2026-06-05T00:00:00+00:00",
    }))

    # Create restaurant profile
    redis_set("profile:leschan", _json.dumps({
        "store_name": "大师傅金奖啤酒鱼（西街口总店）",
        "address": "阳朔县阳朔镇西街德业楼1-7号",
        "city": "桂林市阳朔县",
        "phone": "0773-8816826",
        "category": "餐厅",
        "description": "阳朔老牌啤酒鱼名店，招牌啤酒弄水骨鱼、钢管鸡、田螺酿、竹筒鸡，人均¥119。位于西街核心地段。",
        "updated_at": "2026-06-05T00:00:00+00:00",
    }, ensure_ascii=False), ex=7776000)

    # Also seed leschan_hotel
    pwhash2 = _hash("200115")
    redis_set("user:leschan_hotel", _json.dumps({
        "username": "leschan_hotel",
        "password": pwhash2,
        "created_at": "2026-06-05T00:00:00+00:00",
    }))
    redis_set("profile:leschan_hotel", _json.dumps({
        "store_name": "阳朔安缇雅民宿",
        "address": "阳朔县高田镇凤楼村竹蔸寨村委工农桥段",
        "city": "桂林市阳朔县",
        "phone": "+86-19126149225",
        "category": "酒店",
        "description": "35间客房，泳池/投影/SPA/山景浴缸房，24h前台，明确接受全球外宾入住。近工农桥，远眺月亮山。",
        "updated_at": "2026-06-05T00:00:00+00:00",
    }, ensure_ascii=False), ex=7776000)

    return jsonify({
        "success": True,
        "message": "Seeded: 大师傅金奖啤酒鱼 + 阳朔安缇雅民宿",
        "accounts": ["leschan (restaurant)", "leschan_hotel (hotel)"],
        "password": "200115",
    })
