import os
from fastapi import APIRouter

router = APIRouter()

# Vars we track — report only True/False, never the actual values
_TRACKED = [
    "BINANCE_API_KEY",
    "BINANCE_SECRET_KEY",
    "BINANCE_TESTNET",
    "CLAUDE_API_KEY",
    "DEEPSEEK_API_KEY",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_ALLOWED_USER_IDS",
    "WEB_API_KEY",
    "REDIS_URL",
    "SCAN_INTERVAL_SECONDS",
    "REPORT_TIMES",
]

# Values that count as "not configured" even when present
_PLACEHOLDER_VALUES = {
    "WEB_API_KEY": {"change-me-secret", "change-me-to-something-random"},
    "BINANCE_API_KEY": {"your_binance_api_key_here"},
    "BINANCE_SECRET_KEY": {"your_binance_secret_key_here"},
    "CLAUDE_API_KEY": {"your_anthropic_api_key_here"},
    "DEEPSEEK_API_KEY": {"your_deepseek_api_key_here"},
    "TELEGRAM_BOT_TOKEN": {"your_telegram_bot_token_here"},
}


def _is_configured(key: str) -> bool:
    val = os.getenv(key, "").strip()
    if not val:
        return False
    return val not in _PLACEHOLDER_VALUES.get(key, set())


@router.get("/config/status")
def config_status():
    """
    Return which environment variables are configured in the running container.
    Only returns True/False per key — never exposes actual values.
    """
    return {key: _is_configured(key) for key in _TRACKED}
