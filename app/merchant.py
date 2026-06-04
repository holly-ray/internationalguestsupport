import json
from flask import Blueprint, request, jsonify, session
from app.auth import login_required
from app.kv_client import redis_get, redis_set

merchant_bp = Blueprint("merchant", __name__)

PROFILE_FIELDS = ["store_name", "address", "city", "phone", "category", "description"]


@merchant_bp.route("/console")
def console():
    return __import__("flask").render_template("console.html")


@merchant_bp.route("/api/merchant/profile", methods=["GET"])
@login_required
def get_profile():
    user_id = session["user_id"]
    raw = redis_get(f"profile:{user_id}")
    if raw:
        return jsonify(json.loads(raw))
    return jsonify({})


@merchant_bp.route("/api/merchant/profile", methods=["POST"])
@login_required
def save_profile():
    user_id = session["user_id"]
    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供门店信息"}), 400

    profile = {}
    for field in PROFILE_FIELDS:
        profile[field] = (data.get(field, "") or "").strip()

    if not profile["store_name"]:
        return jsonify({"error": "门店名称不能为空"}), 400

    from datetime import datetime, timezone

    profile["updated_at"] = datetime.now(timezone.utc).isoformat()
    redis_set(f"profile:{user_id}", json.dumps(profile, ensure_ascii=False), ex=7776000)
    return jsonify({"success": True, "profile": profile})


@merchant_bp.route("/api/merchant/history", methods=["GET"])
@login_required
def get_history():
    user_id = session["user_id"]
    raw = redis_get(f"history:{user_id}")
    if raw:
        try:
            return jsonify(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            return jsonify([])
    return jsonify([])


@merchant_bp.route("/api/merchant/stats", methods=["GET"])
@login_required
def get_stats():
    from datetime import datetime, timezone
    from app.auth import DAILY_LIMIT
    from app.kv_client import redis_get as kv_get

    user_id = session["user_id"]
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    count = kv_get(f"rate:{user_id}:{today}")
    total = kv_get(f"total:{user_id}")

    return jsonify({
        "today": int(count) if count else 0,
        "limit": DAILY_LIMIT,
        "total_all_time": int(total) if total else 0,
    })


@merchant_bp.route("/api/merchant/subscription", methods=["GET"])
@login_required
def get_subscription():
    user_id = session["user_id"]
    raw = redis_get(f"sub:{user_id}")
    if raw:
        try:
            return jsonify(json.loads(raw))
        except (json.JSONDecodeError, TypeError):
            pass
    from app.payjs import SUBSCRIPTION_PLANS
    plan = SUBSCRIPTION_PLANS.get("free", {})
    return jsonify({
        "plan": "free",
        "name": plan.get("name", "免费版"),
        "features": plan.get("features", []),
        "translations_per_day": plan.get("translations_per_day", 20),
        "expires_at": None,
    })
