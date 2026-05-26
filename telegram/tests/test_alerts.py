import json
import pytest
from alerts import format_alert


# ── trade_opened ──────────────────────────────────────────────────────────────

def test_format_trade_opened_long():
    event = {
        "type": "trade_opened",
        "pair": "SOLUSDT",
        "side": "LONG",
        "entry_price": 33.20,
        "stop_loss": 31.54,
        "take_profit": 35.86,
        "conviction_score": 72,
    }
    msg = format_alert(event)
    assert msg is not None
    assert "SOLUSDT" in msg
    assert "31.54" in msg
    assert "35.86" in msg
    assert "72" in msg
    assert "📈" in msg or "LONG" in msg


def test_format_trade_opened_short():
    event = {
        "type": "trade_opened",
        "pair": "BTCUSDT",
        "side": "SHORT",
        "entry_price": 65000.0,
        "stop_loss": 68250.0,
        "take_profit": 59800.0,
        "conviction_score": 65,
    }
    msg = format_alert(event)
    assert "BTCUSDT" in msg
    assert "SHORT" in msg


# ── trade_closed ──────────────────────────────────────────────────────────────

def test_format_trade_closed_win():
    event = {
        "type": "trade_closed",
        "pair": "SOLUSDT",
        "side": "LONG",
        "exit_price": 35.86,
        "pnl": 2.67,
        "reason": "take_profit",
    }
    msg = format_alert(event)
    assert "SOLUSDT" in msg
    assert "2.67" in msg
    assert "✅" in msg
    assert "Take Profit" in msg


def test_format_trade_closed_loss():
    event = {
        "type": "trade_closed",
        "pair": "BNBUSDT",
        "exit_price": 285.0,
        "pnl": -1.50,
        "reason": "stop_loss",
    }
    msg = format_alert(event)
    assert "1.50" in msg or "-1.5" in msg
    assert "❌" in msg
    assert "Stop Loss" in msg


def test_format_trade_closed_trailing_stop():
    event = {
        "type": "trade_closed",
        "pair": "ETHUSDT",
        "exit_price": 3100.0,
        "pnl": 1.20,
        "reason": "trailing_stop",
    }
    msg = format_alert(event)
    assert "Trailing Stop" in msg


# ── signal ────────────────────────────────────────────────────────────────────

def test_format_signal_buy_notifies():
    event = {
        "type": "signal",
        "pair": "ETHUSDT",
        "score": 72,
        "action": "BUY",
        "confidence": "HIGH",
    }
    msg = format_alert(event)
    assert msg is not None
    assert "ETHUSDT" in msg
    assert "72" in msg


def test_format_signal_skip_returns_none():
    event = {
        "type": "signal",
        "pair": "XRPUSDT",
        "score": 40,
        "action": "SKIP",
        "confidence": "LOW",
    }
    assert format_alert(event) is None


# ── alert ─────────────────────────────────────────────────────────────────────

def test_format_alert_warning():
    event = {
        "type": "alert",
        "level": "WARNING",
        "message": "Drawdown approaching 15%",
    }
    msg = format_alert(event)
    assert "⚠️" in msg
    assert "15%" in msg


def test_format_alert_critical():
    event = {
        "type": "alert",
        "level": "CRITICAL",
        "message": "Drawdown guard triggered",
    }
    msg = format_alert(event)
    assert "🚨" in msg


# ── report ────────────────────────────────────────────────────────────────────

def test_format_report_returns_content():
    event = {
        "type": "report",
        "content": "📊 *Market Report*\nBTC: $65,000 (+2.5%)",
    }
    msg = format_alert(event)
    assert "BTC" in msg
    assert "$65,000" in msg


# ── legacy events ─────────────────────────────────────────────────────────────

def test_format_low_balance():
    event = {"event": "low_balance", "balance": 45.0}
    msg = format_alert(event)
    assert "45" in msg
    assert "⚠️" in msg


def test_format_drawdown_guard():
    event = {"event": "drawdown_guard", "equity": 75.0, "drawdown_pct": 25.0}
    msg = format_alert(event)
    assert "25" in msg or "stopped" in msg.lower()
    assert "🚨" in msg


def test_format_unknown_event_returns_none():
    event = {"type": "unknown_event_xyz"}
    assert format_alert(event) is None


def test_format_bot_started():
    assert "🟢" in format_alert({"event": "bot_started"})


def test_format_bot_stopped():
    assert "🔴" in format_alert({"event": "bot_stopped"})
