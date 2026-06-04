import os
import json
import time
from urllib.request import Request, urlopen
from flask import session as flask_session

_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "")
_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")

_SESSION_KEY = "_kv"
_REDIS_OK = False
_REDIS_LAST_CHECK = 0
_REDIS_RETRY_INTERVAL = 30  # retry Redis ping after 30s on failure


def _check_redis():
    """Test Redis connectivity. Retries periodically on failure."""
    global _REDIS_OK, _REDIS_LAST_CHECK
    if _REDIS_OK:
        return True
    if not _REST_URL or not _REST_TOKEN:
        return False
    # Don't retry on every call — respect cooldown
    now = time.time()
    if _REDIS_LAST_CHECK and (now - _REDIS_LAST_CHECK) < _REDIS_RETRY_INTERVAL:
        return False
    _REDIS_LAST_CHECK = now
    try:
        body = json.dumps(["PING"]).encode("utf-8")
        req = Request(
            _REST_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_REST_TOKEN}",
            },
        )
        with urlopen(req, timeout=5) as r:
            resp = json.loads(r.read().decode("utf-8"))
        _REDIS_OK = resp.get("result") == "PONG"
        return _REDIS_OK
    except Exception:
        return False


def _redis_cmd(*args):
    """Send a raw Redis command via Upstash REST API."""
    if not _REST_URL or not _REST_TOKEN:
        return None
    try:
        body = json.dumps(args).encode("utf-8")
        req = Request(
            _REST_URL,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {_REST_TOKEN}",
            },
        )
        with urlopen(req, timeout=5) as r:
            resp = json.loads(r.read().decode("utf-8"))
        return resp.get("result")
    except Exception:
        global _REDIS_OK
        _REDIS_OK = False  # force re-check on next call
        return None


def _session_store():
    """Get or create the session-based KV store."""
    if _SESSION_KEY not in flask_session:
        flask_session[_SESSION_KEY] = {}
    return flask_session[_SESSION_KEY]


def _session_get(key):
    store = _session_store()
    entry = store.get(key)
    if entry is None:
        return None
    exp = entry.get("exp")
    if exp and time.time() > exp:
        del store[key]
        return None
    return entry.get("val")


def _session_set(key, value, ex=None):
    store = _session_store()
    entry = {"val": str(value)}
    if ex:
        entry["exp"] = time.time() + int(ex)
    store[key] = entry


def _session_incr(key):
    val = _session_get(key)
    if val is None:
        _session_set(key, "1")
        return 1
    new_val = int(val) + 1
    store = _session_store()
    if key in store:
        store[key]["val"] = str(new_val)
    return new_val


def _session_del(key):
    store = _session_store()
    store.pop(key, None)


# ---- Public API ----

def redis_get(key):
    if _check_redis():
        return _redis_cmd("GET", key)
    return _session_get(key)


def redis_set(key, value, ex=None):
    if _check_redis():
        if ex:
            return _redis_cmd("SET", key, str(value), "EX", str(ex))
        return _redis_cmd("SET", key, str(value))
    _session_set(key, value, ex)
    return True


def redis_incr(key):
    if _check_redis():
        return _redis_cmd("INCR", key)
    return _session_incr(key)


def redis_del(key):
    if _check_redis():
        return _redis_cmd("DEL", key)
    _session_del(key)


def redis_exists(key):
    if _check_redis():
        return _redis_cmd("EXISTS", key)
    return 1 if _session_get(key) is not None else 0


def redis_keys(pattern):
    """Return list of keys matching pattern."""
    if _check_redis():
        result = _redis_cmd("KEYS", pattern)
        if isinstance(result, list):
            return result
        return []
    store = _session_store()
    import re
    escaped = re.escape(pattern).replace(r"\*", ".*")
    try:
        compiled = re.compile("^" + escaped + "$")
    except Exception:
        return []
    matched = []
    for key in list(store.keys()):
        entry = store.get(key)
        if entry is None:
            continue
        exp = entry.get("exp")
        if exp and time.time() > exp:
            del store[key]
            continue
        if compiled.match(key):
            matched.append(key)
    return matched


def is_redis_available():
    """Check if Redis is actually working. Used by auth to detect degraded mode."""
    return _check_redis()
