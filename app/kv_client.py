import os
import json
import time
import threading
from urllib.request import Request, urlopen

_REST_URL = os.getenv("UPSTASH_REDIS_REST_URL", "").strip().lstrip("﻿")
_REST_TOKEN = os.getenv("UPSTASH_REDIS_REST_TOKEN", "").strip().lstrip("﻿")

_REDIS_OK = None  # None=untested, True=working, False=failed
_REDIS_LAST_CHECK = 0
_REDIS_RETRY_INTERVAL = 5  # shorter retry — was 30s, caused stale reads

# In-memory fallback store with TTL
_MEMORY_STORE = {}
_MEMORY_MAX_ENTRIES = 5000
_MEMORY_LOCK = threading.Lock()


def _memory_prune():
    now = time.time()
    expired = [
        k for k, v in _MEMORY_STORE.items()
        if v.get("exp") and v["exp"] < now
    ]
    for k in expired:
        del _MEMORY_STORE[k]


def _memory_get(key):
    with _MEMORY_LOCK:
        entry = _MEMORY_STORE.get(key)
        if entry is None:
            return None
        exp = entry.get("exp")
        if exp and time.time() > exp:
            del _MEMORY_STORE[key]
            return None
        return entry.get("val")


def _memory_set(key, value, ex=None):
    with _MEMORY_LOCK:
        if len(_MEMORY_STORE) > _MEMORY_MAX_ENTRIES:
            _memory_prune()
        entry = {"val": str(value)}
        if ex:
            entry["exp"] = time.time() + int(ex)
        _MEMORY_STORE[key] = entry


def _memory_incr(key):
    with _MEMORY_LOCK:
        val = _memory_get(key)
        new_val = (int(val) + 1) if val is not None else 1
        entry = _MEMORY_STORE.get(key, {})
        entry["val"] = str(new_val)
        _MEMORY_STORE[key] = entry
        return new_val


def _memory_del(key):
    with _MEMORY_LOCK:
        _MEMORY_STORE.pop(key, None)


def _memory_keys(pattern):
    import re
    escaped = re.escape(pattern).replace(r"\*", ".*")
    try:
        compiled = re.compile("^" + escaped + "$")
    except Exception:
        return []
    with _MEMORY_LOCK:
        now = time.time()
        matched = []
        for key in list(_MEMORY_STORE.keys()):
            entry = _MEMORY_STORE.get(key)
            if entry is None:
                continue
            exp = entry.get("exp")
            if exp and now > exp:
                del _MEMORY_STORE[key]
                continue
            if compiled.match(key):
                matched.append(key)
        return matched


def _memory_exists(key):
    return 1 if _memory_get(key) is not None else 0


def _redis_configured():
    return bool(_REST_URL and _REST_TOKEN)


def _redis_cmd(*args):
    """Send a raw Redis command via Upstash REST API. Returns None on failure."""
    global _REDIS_OK
    if not _redis_configured():
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
        result = resp.get("result")
        _REDIS_OK = True
        return result
    except Exception:
        _REDIS_OK = False
        return None


# ---- Public API — Redis primary, in-memory fallback ----

def redis_get(key):
    if _redis_configured():
        result = _redis_cmd("GET", key)
        if result is not None or _REDIS_OK:
            return result
    return _memory_get(key)


def redis_set(key, value, ex=None):
    if _redis_configured():
        if ex:
            result = _redis_cmd("SET", key, str(value), "EX", str(ex))
        else:
            result = _redis_cmd("SET", key, str(value))
        if result is not None or _REDIS_OK:
            return result
    _memory_set(key, value, ex)
    return True


def redis_incr(key):
    if _redis_configured():
        result = _redis_cmd("INCR", key)
        if result is not None:
            return result
    return _memory_incr(key)


def redis_del(key):
    if _redis_configured():
        result = _redis_cmd("DEL", key)
        if result is not None or _REDIS_OK:
            return
    _memory_del(key)


def redis_exists(key):
    if _redis_configured():
        result = _redis_cmd("EXISTS", key)
        if result is not None:
            return result
    return _memory_exists(key)


def redis_keys(pattern):
    if _redis_configured():
        result = _redis_cmd("KEYS", pattern)
        if isinstance(result, list):
            return result
        return []
    return _memory_keys(pattern)


def is_redis_available():
    if _redis_configured():
        return _redis_cmd("PING") == "PONG"
    return False
