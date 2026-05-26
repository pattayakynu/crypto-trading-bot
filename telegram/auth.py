import os
from functools import wraps
from typing import Callable


def _load_allowed_ids() -> set[int]:
    raw = os.getenv("TELEGRAM_ALLOWED_USER_IDS", "")
    return {int(uid.strip()) for uid in raw.split(",") if uid.strip()}


def is_allowed(user_id: int, allowed_ids: set[int] = None) -> bool:
    if allowed_ids is None:
        allowed_ids = _load_allowed_ids()
    return user_id in allowed_ids


def require_auth(allowed_ids: set[int] = None):
    """Decorator factory — only lets whitelisted user IDs through."""
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(update, context):
            uid = update.effective_user.id
            ids = allowed_ids if allowed_ids is not None else _load_allowed_ids()
            if not is_allowed(uid, ids):
                await update.message.reply_text("⛔ Unauthorized.")
                return
            return await func(update, context)
        return wrapper
    return decorator
