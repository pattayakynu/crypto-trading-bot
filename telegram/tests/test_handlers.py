import sys
import os
import pytest
from unittest.mock import MagicMock, AsyncMock
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "engine"))
from db import Base, Trade, Position, LayerWeight, init_db

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from handlers import cmd_status, cmd_balance, cmd_pnl, cmd_trades, cmd_weights, cmd_settings, cmd_stop, cmd_start


@pytest.fixture
def db():
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    sess = Session(engine)
    yield sess
    sess.close()


def make_update():
    update = MagicMock()
    update.message.reply_text = AsyncMock()
    update.effective_user.id = 123456
    return update


# ── /start ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_start_sets_redis_and_replies():
    update = make_update()
    redis_mock = MagicMock()
    await cmd_start(update, MagicMock(), redis_client=redis_mock)
    redis_mock.set.assert_called_with("bot:control", "start")
    update.message.reply_text.assert_awaited_once()
    text = update.message.reply_text.call_args[0][0]
    assert "started" in text.lower() or "🟢" in text


# ── /stop ─────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_stop_sets_redis_and_replies():
    update = make_update()
    redis_mock = MagicMock()
    await cmd_stop(update, MagicMock(), redis_client=redis_mock)
    redis_mock.set.assert_called_with("bot:control", "stop")
    text = update.message.reply_text.call_args[0][0]
    assert "stopped" in text.lower() or "🔴" in text


# ── /status ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_status_running(db):
    update = make_update()
    redis_mock = MagicMock()
    redis_mock.get.return_value = b"running"
    await cmd_status(update, MagicMock(), redis_client=redis_mock, db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "RUNNING" in text


@pytest.mark.asyncio
async def test_cmd_status_stopped(db):
    update = make_update()
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    await cmd_status(update, MagicMock(), redis_client=redis_mock, db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "STOPPED" in text


@pytest.mark.asyncio
async def test_cmd_status_shows_open_positions(db):
    db.add(Position(pair="ETHUSDT", market_type="SPOT", side="LONG",
                    entry_price=3000.0, qty=0.01, usdt_value=30.0,
                    stop_loss=2850.0, take_profit=3150.0,
                    trailing_stop_active=False, highest_price=3000.0, conviction_score=70))
    db.commit()
    update = make_update()
    redis_mock = MagicMock()
    redis_mock.get.return_value = b"running"
    await cmd_status(update, MagicMock(), redis_client=redis_mock, db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "ETHUSDT" in text
    assert "1" in text  # 1 open position


# ── /balance ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_balance_shows_usdt():
    update = make_update()
    binance_mock = MagicMock()
    binance_mock.get_account.return_value = {
        "balances": [
            {"asset": "USDT", "free": "87.50", "locked": "0.00"},
            {"asset": "BTC", "free": "0.001", "locked": "0.00"},
        ]
    }
    await cmd_balance(update, MagicMock(), binance_client=binance_mock)
    text = update.message.reply_text.call_args[0][0]
    assert "87.50" in text or "87.5" in text


@pytest.mark.asyncio
async def test_cmd_balance_no_client():
    update = make_update()
    await cmd_balance(update, MagicMock(), binance_client=None)
    text = update.message.reply_text.call_args[0][0]
    assert "not available" in text.lower() or "⚠️" in text


# ── /pnl ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_pnl_shows_stats(db):
    db.add(Trade(pair="SOLUSDT", side="LONG", price=35.0, qty=1.0, usdt_value=35.0, pnl=2.67, market_type="SPOT"))
    db.add(Trade(pair="BNBUSDT", side="LONG", price=300.0, qty=0.1, usdt_value=30.0, pnl=-1.50, market_type="SPOT"))
    db.commit()
    update = make_update()
    await cmd_pnl(update, MagicMock(), db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "P&L" in text


@pytest.mark.asyncio
async def test_cmd_pnl_no_trades(db):
    update = make_update()
    await cmd_pnl(update, MagicMock(), db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "0" in text  # 0 trades, 0% win rate


# ── /trades ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_trades_shows_last_5(db):
    for i in range(7):
        db.add(Trade(pair=f"COIN{i}USDT", side="LONG", price=100.0, qty=0.1,
                     usdt_value=10.0, pnl=1.0 * (1 if i % 2 == 0 else -1), market_type="SPOT"))
    db.commit()
    update = make_update()
    await cmd_trades(update, MagicMock(), db_session=db)
    text = update.message.reply_text.call_args[0][0]
    # Should show max 5 trades
    assert text.count("USDT") <= 5


@pytest.mark.asyncio
async def test_cmd_trades_empty(db):
    update = make_update()
    await cmd_trades(update, MagicMock(), db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "No closed trades" in text


# ── /weights ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_weights_shows_all_layers(db):
    update = make_update()
    await cmd_weights(update, MagicMock(), db_session=db)
    text = update.message.reply_text.call_args[0][0]
    assert "whale" in text
    assert "macro" in text


# ── /settings ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cmd_settings_shows_env_keys():
    update = make_update()
    await cmd_settings(update, MagicMock())
    text = update.message.reply_text.call_args[0][0]
    assert "MAX_POSITIONS" in text
    assert "STOP_LOSS_PCT" in text
