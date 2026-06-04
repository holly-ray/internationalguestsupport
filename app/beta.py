import json
import os
import sys
import time
from datetime import datetime, timezone
from urllib.request import Request, urlopen
from flask import Blueprint, request, jsonify, session, render_template

from app.auth import login_required
from app.kv_client import redis_get, redis_set, redis_keys

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
    """View error log. Protected by ADMIN_TOKEN env var or localhost."""
    admin_token = os.getenv("ADMIN_TOKEN", "").strip()
    if admin_token:
        token = request.headers.get("Authorization", "").replace("Bearer ", "").strip()
        if token != admin_token:
            return jsonify({"error": "unauthorized"}), 401
    elif request.remote_addr not in ("127.0.0.1", "::1", "localhost"):
        return jsonify({"error": "unauthorized"}), 401

    try:
        raw = redis_get("system:error_log")
        errors = json.loads(raw) if raw else []
    except Exception:
        errors = []

    return jsonify({"errors": errors, "total": len(errors)})
