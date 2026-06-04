import json
from flask import Blueprint, request, jsonify, session
from app.auth import login_required
from app.kv_client import redis_get, redis_set
from app.constants import PROFILE_TTL

merchant_bp = Blueprint("merchant", __name__)

PROFILE_FIELDS = ["store_name", "address", "city", "phone", "category", "description"]

SUBSCRIPTION_PLANS = {
    "free": {
        "name": "免费版",
        "price": 0,
        "price_label": "¥0/月",
        "translations_per_day": 20,
        "languages": ["en", "ja", "ko", "ru"],
        "features": [
            "每日翻译 20 次",
            "4 语种支持（英日韩俄）",
            "PDF 导出",
            "图片导出（ZIP）",
            "门店信息管理",
            "Google 商家上架（3 次/月）",
            "PSB 登记培训",
            "MRZ 护照识别",
        ],
        "gmb_limit": 3,
    },
    "pro": {
        "name": "专业版",
        "price": 29,
        "price_label": "¥29/月",
        "translations_per_day": 200,
        "languages": ["en", "ja", "ko", "ru", "fr", "de", "es", "ar"],
        "features": [
            "每日翻译 200 次",
            "8 语种支持（+ 法德西阿）",
            "PDF 导出（含企业 Logo）",
            "高清图片导出",
            "门店信息管理",
            "Google 商家无限次",
            "TripAdvisor 辅助上架",
            "PSB 登记培训 + MRZ 工具",
            "出入境机构查询",
            "翻译记录搜索",
            "优先客服支持",
        ],
        "gmb_limit": 999,
    },
    "business": {
        "name": "企业版",
        "price": 99,
        "price_label": "¥99/月",
        "translations_per_day": 1000,
        "languages": ["en", "ja", "ko", "ru", "fr", "de", "es", "ar", "th", "vi", "it", "pt"],
        "features": [
            "每日翻译 1000 次",
            "12 语种支持",
            "PDF 导出（含 Logo + 自定义页眉）",
            "高清图片导出",
            "门店信息管理",
            "Google 商家无限次",
            "TripAdvisor 辅助上架",
            "PSB 登记培训 + MRZ 工具",
            "出入境机构查询",
            "翻译记录搜索 + 导出",
            "批量翻译（一次翻译多份物料）",
            "专属客户经理",
            "API 对接支持",
        ],
        "gmb_limit": 999,
    },
}


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
    redis_set(f"profile:{user_id}", json.dumps(profile, ensure_ascii=False), ex=PROFILE_TTL)
    return jsonify({"success": True, "profile": profile})


@merchant_bp.route("/api/merchant/history", methods=["GET"])
@login_required
def get_history():
    user_id = session["user_id"]
    raw = redis_get(f"history:{user_id}")
    if raw:
        try:
            history = json.loads(raw)
            if isinstance(history, list):
                return jsonify(history[-200:])
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
    plan = SUBSCRIPTION_PLANS.get("free", {})
    return jsonify({
        "plan": "free",
        "name": plan.get("name", "免费版"),
        "features": plan.get("features", []),
        "translations_per_day": plan.get("translations_per_day", 20),
        "expires_at": None,
    })
