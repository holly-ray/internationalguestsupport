import json
from datetime import datetime, timezone
from flask import Blueprint, request, jsonify, session, render_template

from app.auth import login_required
from app.kv_client import redis_get, redis_set

guide_bp = Blueprint("guide", __name__)


@guide_bp.route("/api/guide/checklist", methods=["GET"])
@login_required
def get_checklist():
    user_id = session["user_id"]
    feature = request.args.get("feature", "gmb")
    if feature not in ("gmb", "tripadvisor"):
        return jsonify({"error": "invalid feature"}), 400

    raw = redis_get(f"guide_progress:{user_id}:{feature}")
    if not raw:
        return jsonify({"done_steps": []})
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return jsonify({"done_steps": []})
    return jsonify({"done_steps": data.get("done", [])})


@guide_bp.route("/api/guide/checklist", methods=["POST"])
@login_required
def save_checklist():
    user_id = session["user_id"]
    body = request.get_json() or {}
    feature = body.get("feature", "gmb")
    if feature not in ("gmb", "tripadvisor"):
        return jsonify({"error": "invalid feature"}), 400

    done_steps = body.get("done_steps", [])
    if not isinstance(done_steps, list):
        return jsonify({"error": "done_steps must be a list"}), 400

    redis_set(
        f"guide_progress:{user_id}:{feature}",
        json.dumps({
            "done": sorted(set(done_steps)),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }, ensure_ascii=False),
    )
    return jsonify({"success": True})
