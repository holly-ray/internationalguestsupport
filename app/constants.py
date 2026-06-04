"""
Centralized constants for 国际宾客支持.
Import from here instead of scattering magic numbers across modules.
"""

# ---- Rate Limiting ----
DAILY_TRANSLATION_LIMIT = 20
RATE_LIMIT_TTL = 86400  # 24 hours

# ---- TTLs (seconds) ----
PROFILE_TTL = 7776000       # 90 days
FEEDBACK_TTL = 7776000      # 90 days
PAY_ORDER_TTL = 2592000     # 30 days
OAUTH_STATE_TTL = 600       # 10 minutes

# ---- Error Logging ----
MAX_ERROR_LOG = 100
