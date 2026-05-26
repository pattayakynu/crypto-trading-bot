import json
import pytest
from unittest.mock import MagicMock
from publisher import (
    EventPublisher,
    CHANNEL_SIGNAL, CHANNEL_TRADE_OPENED, CHANNEL_TRADE_CLOSED,
    CHANNEL_POSITION_UPDATE, CHANNEL_REPORT, CHANNEL_ALERT,
    REDIS_KEY_PREFIX
)


def make_publisher():
    mock_redis = MagicMock()
    mock_redis.publish.return_value = 1
    return EventPublisher(redis_client=mock_redis), mock_redis


# ── Channel naming ────────────────────────────────────────────────────────────

def test_channels_use_prefix():
    assert CHANNEL_SIGNAL.startswith(REDIS_KEY_PREFIX)
    assert CHANNEL_TRADE_OPENED.startswith(REDIS_KEY_PREFIX)
    assert CHANNEL_TRADE_CLOSED.startswith(REDIS_KEY_PREFIX)
    assert CHANNEL_REPORT.startswith(REDIS_KEY_PREFIX)
    assert CHANNEL_ALERT.startswith(REDIS_KEY_PREFIX)


# ── Signal publish ────────────────────────────────────────────────────────────

def test_publish_signal_calls_redis():
    pub, mock_redis = make_publisher()
    result = pub.publish_signal("ETHUSDT", 72, "BUY", "HIGH", ["whale: STRONG"])
    assert result == 1
    mock_redis.publish.assert_called_once()
    channel, raw = mock_redis.publish.call_args[0]
    assert channel == CHANNEL_SIGNAL
    data = json.loads(raw)
    assert data["type"] == "signal"
    assert data["pair"] == "ETHUSDT"
    assert data["score"] == 72
    assert data["action"] == "BUY"
    assert data["confidence"] == "HIGH"


# ── Trade opened publish ──────────────────────────────────────────────────────

def test_publish_trade_opened():
    pub, mock_redis = make_publisher()
    pub.publish_trade_opened(
        pair="BTCUSDT", side="LONG", market_type="SPOT",
        entry_price=50000.0, qty=0.001, usdt_value=50.0,
        stop_loss=47500.0, take_profit=54000.0, conviction_score=80
    )
    channel, raw = mock_redis.publish.call_args[0]
    assert channel == CHANNEL_TRADE_OPENED
    data = json.loads(raw)
    assert data["type"] == "trade_opened"
    assert data["side"] == "LONG"
    assert data["market_type"] == "SPOT"
    assert data["conviction_score"] == 80


# ── Trade closed publish ──────────────────────────────────────────────────────

def test_publish_trade_closed():
    pub, mock_redis = make_publisher()
    pub.publish_trade_closed(
        pair="ETHUSDT", side="LONG", market_type="SPOT",
        entry_price=3000.0, exit_price=3150.0,
        qty=0.016, pnl=2.31, reason="take_profit"
    )
    channel, raw = mock_redis.publish.call_args[0]
    assert channel == CHANNEL_TRADE_CLOSED
    data = json.loads(raw)
    assert data["pnl"] == 2.31
    assert data["reason"] == "take_profit"


# ── Position update publish ───────────────────────────────────────────────────

def test_publish_position_update():
    pub, mock_redis = make_publisher()
    pub.publish_position_update("SOLUSDT", 145.0, 3.5, trailing_stop_active=True)
    channel, raw = mock_redis.publish.call_args[0]
    assert channel == CHANNEL_POSITION_UPDATE
    data = json.loads(raw)
    assert data["trailing_stop_active"] is True
    assert data["pnl_unrealized"] == 3.5


# ── Report publish ────────────────────────────────────────────────────────────

def test_publish_report():
    pub, mock_redis = make_publisher()
    pub.publish_report("BTC up 2%, market bullish", report_type="market")
    channel, raw = mock_redis.publish.call_args[0]
    assert channel == CHANNEL_REPORT
    data = json.loads(raw)
    assert data["report_type"] == "market"
    assert "BTC up 2%" in data["content"]


# ── Alert publish ─────────────────────────────────────────────────────────────

def test_publish_alert_warning():
    pub, mock_redis = make_publisher()
    pub.publish_alert("WARNING", "Drawdown approaching 15%", {"equity": 85.0})
    channel, raw = mock_redis.publish.call_args[0]
    assert channel == CHANNEL_ALERT
    data = json.loads(raw)
    assert data["level"] == "WARNING"
    assert data["data"]["equity"] == 85.0


def test_publish_alert_no_data():
    pub, mock_redis = make_publisher()
    pub.publish_alert("CRITICAL", "Drawdown limit hit")
    _, raw = mock_redis.publish.call_args[0]
    data = json.loads(raw)
    assert data["data"] == {}


# ── Error resilience ──────────────────────────────────────────────────────────

def test_publish_returns_zero_on_redis_error():
    mock_redis = MagicMock()
    mock_redis.publish.side_effect = Exception("Connection refused")
    pub = EventPublisher(redis_client=mock_redis)
    result = pub.publish_signal("BTCUSDT", 60, "BUY", "MEDIUM", [])
    assert result == 0
