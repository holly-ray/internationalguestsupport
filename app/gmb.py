import os
import json
import time
import sys
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import URLError
from flask import Blueprint, request, jsonify, session, redirect, render_template

from app.auth import login_required
from app.kv_client import redis_get, redis_set, redis_del

gmb_bp = Blueprint("gmb", __name__)

GMB_CLIENT_ID = os.getenv("GMB_CLIENT_ID", "")
GMB_CLIENT_SECRET = os.getenv("GMB_CLIENT_SECRET", "")
GMB_REDIRECT_URI = os.getenv("GMB_REDIRECT_URI", "")

OAUTH_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
OAUTH_TOKEN_URL = "https://oauth2.googleapis.com/token"
GMB_ACCOUNTS_URL = "https://mybusiness.googleapis.com/v4/accounts"
GMB_LOCATIONS_URL = "https://mybusiness.googleapis.com/v4/{parent}/locations"
GMB_SCOPE = "https://www.googleapis.com/auth/business.manage"

ERROR_MAP = {
    "access_denied": "您取消了授权",
    "invalid_grant": "授权已过期，请重新连接 Google",
    "permission_denied": "权限不足，请确认 Google 账号有商家管理权限",
    "not_found": "未找到相关资源",
    "already_exists": "该商家信息已存在",
    "resource_exhausted": "请求过于频繁，请稍后再试",
}


def _api_post_json(url, token, body):
    """POST JSON to a Google API. Returns (data, error)."""
    try:
        req = Request(
            url,
            data=json.dumps(body).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
        )
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except URLError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err_msg = err_body.get("error", {}).get("message", str(e.reason))
            err_status = err_body.get("error", {}).get("status", "UNKNOWN")
        except Exception:
            err_msg = str(e.reason)
            err_status = "UNKNOWN"
        return None, _map_error(err_status, err_msg)


def _api_get_json(url, token):
    """GET from a Google API. Returns (data, error)."""
    try:
        req = Request(url, headers={"Authorization": f"Bearer {token}"})
        with urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), None
    except URLError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err_msg = err_body.get("error", {}).get("message", str(e.reason))
            err_status = err_body.get("error", {}).get("status", "UNKNOWN")
        except Exception:
            err_msg = str(e.reason)
            err_status = "UNKNOWN"
        return None, _map_error(err_status, err_msg)


def _map_error(status, message):
    for key, cn in ERROR_MAP.items():
        if key in status.lower() or key in message.lower():
            return cn
    return message


def _get_valid_gmb_token(user_id):
    """Get a valid access token, refreshing if needed. Returns (token, account_id, error)."""
    raw = redis_get(f"gmb_token:{user_id}")
    if not raw:
        return None, None, "请先连接 Google 账号"

    try:
        token_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, None, "Token 数据损坏，请重新连接"

    access_token = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_at = token_data.get("expires_at", 0)
    account_id = token_data.get("account_id")

    # Return if still valid (>5 min remaining)
    if access_token and expires_at > time.time() + 300:
        return access_token, account_id, None

    # Refresh
    if not refresh_token:
        return None, None, "授权已过期，请重新连接 Google"

    return _refresh_token(user_id, refresh_token, account_id)


def _refresh_token(user_id, refresh_token, account_id):
    """Exchange refresh_token for new access_token."""
    try:
        body = urlencode({
            "client_id": GMB_CLIENT_ID,
            "client_secret": GMB_CLIENT_SECRET,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }).encode("utf-8")
        req = Request(
            OAUTH_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(req, timeout=15) as r:
            resp = json.loads(r.read().decode("utf-8"))

        new_access_token = resp.get("access_token")
        new_expires_in = resp.get("expires_in", 3600)

        redis_set(
            f"gmb_token:{user_id}",
            json.dumps({
                "access_token": new_access_token,
                "refresh_token": refresh_token,
                "expires_at": time.time() + new_expires_in - 60,
                "account_id": account_id,
            }),
        )
        return new_access_token, account_id, None
    except URLError as e:
        return None, None, f"Token 刷新失败：{str(e.reason)}"
    except Exception as e:
        return None, None, f"Token 刷新失败：{str(e)}"


# ---- Routes ----

@gmb_bp.route("/gmb")
def gmb_status_page():
    return render_template("gmb_status.html")


@gmb_bp.route("/gmb/connect")
@login_required
def gmb_connect():
    if not GMB_CLIENT_ID or not GMB_CLIENT_SECRET:
        return render_template("gmb_status.html", error="Google OAuth 尚未配置，请使用手动上架指南。")

    state = os.urandom(16).hex()
    redis_set(f"oauth_state:{state}", session["user_id"], ex=600)

    params = urlencode({
        "client_id": GMB_CLIENT_ID,
        "redirect_uri": GMB_REDIRECT_URI,
        "response_type": "code",
        "scope": GMB_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return redirect(f"{OAUTH_AUTH_URL}?{params}")


@gmb_bp.route("/gmb/callback")
def gmb_callback():
    code = request.args.get("code", "")
    state = request.args.get("state", "")
    error = request.args.get("error", "")

    if error:
        cn_msg = ERROR_MAP.get(error, f"Google 授权失败：{error}")
        return render_template("gmb_status.html", error=cn_msg)

    if not code or not state:
        return render_template("gmb_status.html", error="授权参数不完整")

    # Verify state
    stored_user = redis_get(f"oauth_state:{state}")
    redis_del(f"oauth_state:{state}")

    if not stored_user:
        return render_template("gmb_status.html", error="授权会话已过期，请重新连接")

    # Load user into session if not already
    if "user_id" not in session:
        session["user_id"] = stored_user

    user_id = stored_user

    # Exchange code for tokens
    try:
        body = urlencode({
            "code": code,
            "client_id": GMB_CLIENT_ID,
            "client_secret": GMB_CLIENT_SECRET,
            "redirect_uri": GMB_REDIRECT_URI,
            "grant_type": "authorization_code",
        }).encode("utf-8")
        req = Request(
            OAUTH_TOKEN_URL,
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with urlopen(req, timeout=15) as r:
            token_resp = json.loads(r.read().decode("utf-8"))
    except URLError as e:
        try:
            err_body = json.loads(e.read().decode("utf-8"))
            err_msg = err_body.get("error_description", str(e.reason))
        except Exception:
            err_msg = str(e.reason)
        return render_template("gmb_status.html", error=f"Token 交换失败：{err_msg}")
    except Exception as e:
        return render_template("gmb_status.html", error=f"Token 交换失败：{str(e)}")

    access_token = token_resp.get("access_token")
    refresh_token = token_resp.get("refresh_token")
    expires_in = token_resp.get("expires_in", 3600)

    if not access_token:
        return render_template("gmb_status.html", error="未能获取访问令牌，请重试")

    # Discover or create GMB account
    accounts_data, err = _api_get_json(GMB_ACCOUNTS_URL, access_token)
    if err:
        return render_template("gmb_status.html", error=f"获取 GMB 账号失败：{err}")

    accounts = accounts_data.get("accounts", []) if accounts_data else []
    if accounts:
        account_name = accounts[0]["name"]  # e.g., "accounts/123456789"
        account_id = account_name.split("/")[-1]
    else:
        # Create an account
        create_data, err = _api_post_json(
            GMB_ACCOUNTS_URL, access_token,
            {"accountName": "account", "type": "PERSONAL"},
        )
        if err:
            return render_template("gmb_status.html", error=f"创建 GMB 账号失败：{err}")
        account_name = create_data.get("name", "")
        account_id = account_name.split("/")[-1]

    # Store token
    redis_set(
        f"gmb_token:{user_id}",
        json.dumps({
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": time.time() + expires_in - 60,
            "account_id": account_id,
        }),
    )

    return redirect("/gmb/form")


@gmb_bp.route("/gmb/form")
def gmb_form_page():
    return render_template("gmb_form.html")


@gmb_bp.route("/api/gmb/config", methods=["GET"])
def gmb_config():
    """Report whether GMB OAuth is configured."""
    return jsonify({
        "oauth_configured": bool(GMB_CLIENT_ID and GMB_CLIENT_SECRET and GMB_REDIRECT_URI),
    })


@gmb_bp.route("/api/gmb/status", methods=["GET"])
@login_required
def gmb_api_status():
    user_id = session["user_id"]
    raw = redis_get(f"gmb_token:{user_id}")
    if not raw:
        return jsonify({"connected": False})

    try:
        token_data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"connected": False})

    access_token, account_id, err = _get_valid_gmb_token(user_id)
    if err:
        return jsonify({"connected": False, "error": err})

    # Check for existing listing
    raw_loc = redis_get(f"gmb_location:{user_id}")
    if raw_loc:
        try:
            loc = json.loads(raw_loc)
            return jsonify({
                "connected": True,
                "has_listing": True,
                "location_name": loc.get("location_name", ""),
                "location_id": loc.get("location_id", ""),
            })
        except (json.JSONDecodeError, TypeError):
            pass

    return jsonify({"connected": True, "has_listing": False})


@gmb_bp.route("/api/gmb/create", methods=["POST"])
@login_required
def gmb_create_listing():
    user_id = session["user_id"]
    access_token, account_id, err = _get_valid_gmb_token(user_id)
    if err:
        return jsonify({"error": err}), 401

    data = request.get_json()
    if not data:
        return jsonify({"error": "请提供商家信息"}), 400

    store_name = (data.get("storeName") or "").strip()
    if not store_name:
        return jsonify({"error": "商家名称不能为空"}), 400

    # Build location payload
    location = {
        "locationName": store_name,
        "primaryPhone": (data.get("primaryPhone") or "").strip(),
        "primaryCategory": {"categoryId": data.get("primaryCategory", "")} if data.get("primaryCategory") else {},
        "websiteUrl": (data.get("websiteUrl") or "").strip(),
        "languageCode": "zh-CN",
    }

    # Address
    addr = data.get("address", {})
    if addr:
        location["storefrontAddress"] = {
            "addressLines": [addr.get("addressLines", "").strip()] if addr.get("addressLines") else [],
            "locality": addr.get("locality", "").strip(),
            "administrativeArea": addr.get("administrativeArea", "").strip(),
            "regionCode": addr.get("regionCode", "CN"),
            "postalCode": addr.get("postalCode", "").strip(),
        }

    # Regular hours
    hours = data.get("regularHours", {})
    if hours and hours.get("periods"):
        location["regularHours"] = {"periods": hours["periods"]}

    # Description
    desc = (data.get("description") or "").strip()
    if desc:
        location["profile"] = {"description": desc[:750]}

    # Create location
    url = f"https://mybusiness.googleapis.com/v4/accounts/{account_id}/locations"
    result, api_err = _api_post_json(url, access_token, location)

    if api_err:
        print(f"GMB create error: {api_err}", file=sys.stderr)
        return jsonify({"error": f"Google 商家创建失败：{api_err}"}), 500

    location_name = result.get("name", "")  # "accounts/X/locations/Y"
    location_id = location_name.split("/")[-1] if location_name else ""

    # Store location info
    redis_set(
        f"gmb_location:{user_id}",
        json.dumps({"location_id": location_id, "location_name": store_name}),
    )

    return jsonify({
        "success": True,
        "location_id": location_id,
        "location_name": store_name,
    })


@gmb_bp.route("/api/gmb/disconnect", methods=["POST"])
@login_required
def gmb_disconnect():
    user_id = session["user_id"]
    redis_del(f"gmb_token:{user_id}")
    redis_del(f"gmb_location:{user_id}")
    return jsonify({"success": True})
