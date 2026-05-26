import pytest
from unittest.mock import MagicMock, AsyncMock
from auth import is_allowed, require_auth


def test_allowed_user_returns_true():
    assert is_allowed(user_id=123456, allowed_ids={123456, 999999}) is True


def test_unknown_user_returns_false():
    assert is_allowed(user_id=111111, allowed_ids={123456}) is False


def test_empty_allowed_set_blocks_all():
    assert is_allowed(user_id=123456, allowed_ids=set()) is False


@pytest.mark.asyncio
async def test_require_auth_calls_handler_for_allowed():
    update = MagicMock()
    update.effective_user.id = 123456
    context = MagicMock()
    handler = AsyncMock()

    decorated = require_auth(allowed_ids={123456})(handler)
    await decorated(update, context)
    handler.assert_awaited_once_with(update, context)


@pytest.mark.asyncio
async def test_require_auth_rejects_unknown():
    update = MagicMock()
    update.effective_user.id = 999
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()
    handler = AsyncMock()

    decorated = require_auth(allowed_ids={123456})(handler)
    await decorated(update, context)
    handler.assert_not_awaited()
    update.message.reply_text.assert_awaited_once()


@pytest.mark.asyncio
async def test_require_auth_reply_contains_unauthorized():
    update = MagicMock()
    update.effective_user.id = 777
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    context = MagicMock()

    @require_auth(allowed_ids={123456})
    async def dummy(u, c):
        pass

    await dummy(update, context)
    text = update.message.reply_text.call_args[0][0]
    assert "Unauthorized" in text or "nauthorized" in text
