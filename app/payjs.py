import hashlib
import json
import os
import time
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError
from flask import Blueprint, request, jsonify, session, render_template

from app.auth import login_required
from app.kv_client import redis_get, redis_set

payjs_bp = Blueprint("payjs", __name__)

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


def _payjs_sign(params, api_key):
    sorted_keys = sorted(k for k in params if k != "sign")
    sign_str = "&".join(f"{k}={params[k]}" for k in sorted_keys)
    sign_str += f"&key={api_key}"
    return hashlib.md5(sign_str.encode("utf-8")).hexdigest().upper()


def _payjs_post(endpoint, params):
    merchant_id = os.getenv("PAYJS_MERCHANT_ID", "")
    api_key = os.getenv("PAYJS_API_KEY", "")
    if not merchant_id or not api_key:
        return None, "PayJS 未配置（请设置 PAYJS_MERCHANT_ID 和 PAYJS_API_KEY 环境变量）"

    params["mchid"] = merchant_id
    params["sign"] = _payjs_sign(params, api_key)

    try:
        body = urlencode(params).encode("utf-8")
        req = Request(
            f"https://payjs.cn/api/{endpoint}",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode("utf-8")), None
    except URLError as e:
        return None, f"PayJS 请求失败：{str(e.reason)}"
    except Exception as e:
        return None, f"PayJS 请求异常：{str(e)}"


@payjs_bp.route("/subscription")
def subscription_page():
    return render_template("subscription_upgrade.html")


@payjs_bp.route("/api/pay/create-order", methods=["POST"])
@login_required
def create_order():
    user_id = session["user_id"]
    data = request.get_json()
    plan_slug = data.get("plan", "").strip() if data else ""

    if plan_slug not in SUBSCRIPTION_PLANS or plan_slug == "free":
        return jsonify({"error": "无效的套餐"}), 400

    plan = SUBSCRIPTION_PLANS[plan_slug]
    amount = plan["price"] * 100  # PayJS expects fen

    order_id = f"sub_{user_id[:8]}_{int(time.time())}"

    params = {
        "body": f"国际宾客支持 - {plan['name']}",
        "out_trade_no": order_id,
        "total_fee": str(amount),
        "attach": json.dumps({"user_id": user_id, "plan": plan_slug}),
    }

    callback_url = os.getenv("PAYJS_CALLBACK_URL", "")
    if callback_url:
        params["notify_url"] = callback_url

    result, error = _payjs_post("native", params)
    if error:
        return jsonify({"error": error}), 500

    if result.get("return_code") != 1:
        return jsonify({"error": result.get("return_msg", "支付创建失败")}), 500

    redis_set(
        f"pay_order:{order_id}",
        json.dumps({
            "user_id": user_id,
            "plan": plan_slug,
            "amount": plan["price"],
            "status": "pending",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }),
        ex=7200,
    )

    return jsonify({
        "success": True,
        "order_id": order_id,
        "qr_code_url": result.get("code_url", ""),
        "payjs_order_id": result.get("payjs_order_id", ""),
        "amount": plan["price"],
        "amount_label": plan["price_label"],
    })


@payjs_bp.route("/api/pay/callback", methods=["POST"])
def payment_callback():
    api_key = os.getenv("PAYJS_API_KEY", "")
    if not api_key:
        return "fail", 500

    data = request.form.to_dict()

    received_sign = data.get("sign", "")
    calculated_sign = _payjs_sign(data, api_key)
    if received_sign.upper() != calculated_sign.upper():
        return "fail", 403

    if data.get("return_code") != "1":
        return "fail", 400

    attach_raw = data.get("attach", "{}")
    try:
        attach = json.loads(attach_raw)
    except (json.JSONDecodeError, TypeError):
        return "fail", 400

    user_id = attach.get("user_id")
    plan_slug = attach.get("plan")
    order_id = data.get("out_trade_no", "")

    if not user_id or not plan_slug:
        return "fail", 400

    order_raw = redis_get(f"pay_order:{order_id}")
    if not order_raw:
        return "fail", 404

    plan = SUBSCRIPTION_PLANS.get(plan_slug, {})
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(days=30)).isoformat()

    sub_data = {
        "plan": plan_slug,
        "name": plan.get("name", ""),
        "features": plan.get("features", []),
        "translations_per_day": plan.get("translations_per_day", 20),
        "expires_at": expires_at,
        "order_id": order_id,
        "payjs_order_id": data.get("payjs_order_id", ""),
        "created_at": now.isoformat(),
    }

    try:
        redis_set(f"sub:{user_id}", json.dumps(sub_data, ensure_ascii=False))
        try:
            order_data = json.loads(order_raw)
        except (json.JSONDecodeError, TypeError):
            order_data = {}
        order_data["status"] = "paid"
        order_data["upgraded_at"] = now.isoformat()
        redis_set(f"pay_order:{order_id}", json.dumps(order_data), ex=2592000)
    except Exception:
        try:
            from app.beta import log_error_to_kv
            log_error_to_kv("payjs.callback", "Subscription upgrade failed",
                            json.dumps({"user_id": user_id, "plan": plan_slug, "order_id": order_id}))
        except Exception:
            pass
        redis_set(f"pay_order:{order_id}:pending_upgrade", json.dumps(sub_data, ensure_ascii=False), ex=2592000)
        return "success", 200

    return "success", 200


@payjs_bp.route("/api/pay/status", methods=["GET"])
@login_required
def order_status():
    user_id = session["user_id"]
    order_id = request.args.get("order_id", "").strip()

    if not order_id:
        return jsonify({"error": "缺少 order_id"}), 400

    order_raw = redis_get(f"pay_order:{order_id}")
    if not order_raw:
        return jsonify({"status": "not_found"}), 404

    try:
        order_data = json.loads(order_raw)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"status": "error"}), 500

    sub_raw = redis_get(f"sub:{user_id}")
    sub_data = None
    if sub_raw:
        try:
            parsed_sub = json.loads(sub_raw)
            if parsed_sub.get("order_id") == order_id:
                sub_data = parsed_sub
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify({
        "order_status": order_data.get("status", "unknown"),
        "subscription": sub_data,
    })
