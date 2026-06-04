"""
Centralized constants for WaiBin.
Import from here instead of scattering magic numbers across modules.
"""

# ---- Rate Limiting ----
DAILY_TRANSLATION_LIMIT = 20
RATE_LIMIT_TTL = 86400  # 24 hours

# ---- Verification ----
VERIFICATION_MODE = "demo"  # set to "production" in real env
VERIFY_CODE_TTL = 300  # 5 minutes
MAX_VERIFY_ATTEMPTS = 5

# ---- TTLs (seconds) ----
PROFILE_TTL = 7776000       # 90 days
FEEDBACK_TTL = 7776000      # 90 days
PAY_ORDER_TTL = 2592000     # 30 days
OAUTH_STATE_TTL = 600       # 10 minutes

# ---- Error Logging ----
MAX_ERROR_LOG = 100
