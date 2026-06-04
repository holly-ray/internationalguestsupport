import time
import functools
from flask import request, jsonify

from app.kv_client import redis_incr, redis_get, redis_set

# Default limits
LIMITS = {
    "login": {"window": 60, "max": 10},
    "translate": {"window": 60, "max": 30},
    "generate_description": {"window": 300, "max": 5},
    "export": {"window": 60, "max": 10},
}


def _get_ip():
    """Extract client IP. On Vercel, trusts X-Real-IP or last hop of X-Forwarded-For."""
    real_ip = request.headers.get("X-Real-IP", "")
    if real_ip:
        return real_ip.strip()
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        # Vercel appends the real client IP as the last entry
        parts = [p.strip() for p in forwarded.split(",")]
        if parts:
            return parts[-1]
    return request.remote_addr or "127.0.0.1"


def _rate_key(prefix, identifier):
    """Generate a sliding-window rate key: rate:{prefix}:{id}:{window_block}"""
    limit_config = LIMITS.get(prefix, {"window": 60, "max": 30})
    window = limit_config["window"]
    block = int(time.time() / window)
    return f"rate_limit:{prefix}:{identifier}:{block}"


def check_rate_limit(prefix, identifier=None):
    """Check and increment a rate counter. Returns (allowed, retry_after_seconds)."""
    limit_config = LIMITS.get(prefix)
    if not limit_config:
        return True, 0

    window = limit_config["window"]
    max_req = limit_config["max"]
    key = _rate_key(prefix, identifier)

    count = redis_incr(key)
    if isinstance(count, int) and count == 1:
        redis_set(key, "1", ex=window * 2)

    if isinstance(count, int) and count > max_req:
        return False, window

    return True, 0


def rate_limit(prefix, identifier_fn=None):
    """Decorator factory for rate limiting a Flask endpoint.

    Usage:
        @rate_limit("login")
        def login(): ...

        @rate_limit("translate", identifier_fn=lambda: session.get("user_id"))
        def translate(): ...
    """
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            if identifier_fn:
                identifier = identifier_fn()
            elif prefix == "login":
                identifier = _get_ip()
            else:
                identifier = _get_ip()

            if not identifier:
                identifier = _get_ip()

            allowed, retry = check_rate_limit(prefix, identifier)
            if not allowed:
                return jsonify({
                    "error": f"请求过于频繁，请 {retry} 秒后重试",
                    "retry_after": retry,
                }), 429

            return fn(*args, **kwargs)
        return wrapper
    return decorator
