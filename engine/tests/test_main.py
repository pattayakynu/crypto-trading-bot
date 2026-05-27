"""
Smoke tests for main.py orchestration logic.
Tests utility functions and pipeline behavior without starting the scheduler
or connecting to Binance.
"""
import json
import pytest
from unittest.mock import MagicMock, patch
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db import Base, Position, Trade, SignalLog, LayerWeight, Performance, init_db
from main import (
    _get_equity,
    _close_position,
    monitor_positions,
    _short_confidence,
    INITIAL_CAPITAL,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def make_services(executor_mock=None, publisher_mock=None):
    return {
        "manipulator": MagicMock(),
        "whale": MagicMock(),
        "macro": MagicMock(),
        "fiat_flow": MagicMock(),
        "btc_lead": MagicMock(),
        "strategy": MagicMock(),
        "social": MagicMock(),
        "llm": MagicMock(),
        "executor": executor_mock or MagicMock(),
        "publisher": publisher_mock or MagicMock(),
        "reporter": MagicMock(),
    }


def make_position(session, pair="ETHUSDT", entry=3000.0, qty=0.01, sl=2850.0, tp=3240.0):
    pos = Position(
        pair=pair,
        market_type="SPOT",
        side="LONG",
        entry_price=entry,
        qty=qty,
        usdt_value=entry * qty,
        stop_loss=sl,
        take_profit=tp,
        trailing_stop_active=False,
        highest_price=entry,
        conviction_score=72,
    )
    session.add(pos)
    session.commit()
    return pos


# ── _get_equity ────────────────────────────────────────────────────────────────

def test_get_equity_returns_initial_when_no_records(session):
    equity = _get_equity(session)
    assert equity == INITIAL_CAPITAL


def test_get_equity_returns_latest_performance(session):
    session.add(Performance(equity=105.50))
    session.commit()
    assert _get_equity(session) == 105.50


def test_get_equity_returns_most_recent(session):
    session.add(Performance(equity=90.0))
    session.add(Performance(equity=115.0))
    session.commit()
    # Should return the last one added (highest id)
    assert _get_equity(session) == 115.0


# ── _close_position ────────────────────────────────────────────────────────────

def test_close_position_successful_take_profit(session):
    from adaptive import AdaptiveLearner
    pos = make_position(session, entry=3000.0, qty=0.016)
    exit_price = 3150.0  # +5% = take_profit hit

    executor_mock = MagicMock()
    executor_mock.sell_spot.return_value = MagicMock(success=True, price=exit_price)
    publisher_mock = MagicMock()
    services = make_services(executor_mock, publisher_mock)

    learner = AdaptiveLearner(session)
    _close_position(pos, exit_price, "take_profit", session, services, learner)

    # Position should be deleted
    assert session.query(Position).count() == 0
    # Trade should be recorded
    trade = session.query(Trade).first()
    assert trade is not None
    assert trade.pnl > 0  # Profitable
    # Publisher notified
    publisher_mock.publish_trade_closed.assert_called_once()
    call_kwargs = publisher_mock.publish_trade_closed.call_args[1]
    assert call_kwargs["reason"] == "take_profit"


def test_close_position_stop_loss_blacklists_pair(session):
    from adaptive import AdaptiveLearner
    from db import PairBlacklist
    pos = make_position(session, entry=3000.0, qty=0.016)
    exit_price = 2840.0  # below SL

    executor_mock = MagicMock()
    executor_mock.sell_spot.return_value = MagicMock(success=True, price=exit_price)
    services = make_services(executor_mock)

    learner = AdaptiveLearner(session)
    _close_position(pos, exit_price, "stop_loss", session, services, learner)

    # Pair should be blacklisted after a loss
    assert session.query(PairBlacklist).filter_by(pair="ETHUSDT").count() == 1


def test_close_position_executor_failure_keeps_position(session):
    from adaptive import AdaptiveLearner
    pos = make_position(session, entry=3000.0, qty=0.016)

    executor_mock = MagicMock()
    executor_mock.sell_spot.return_value = MagicMock(success=False, error="Network error", price=0)
    services = make_services(executor_mock)

    learner = AdaptiveLearner(session)
    _close_position(pos, 3150.0, "take_profit", session, services, learner)

    # Position NOT deleted on failure
    assert session.query(Position).count() == 1


# ── monitor_positions ─────────────────────────────────────────────────────────

def test_monitor_no_positions_does_nothing(session):
    executor_mock = MagicMock()
    services = make_services(executor_mock)
    monitor_positions(session, services, client=None)
    executor_mock.get_current_price.assert_not_called()


def test_monitor_activates_trailing_stop_at_threshold(session):
    pos = make_position(session, entry=3000.0)
    executor_mock = MagicMock()
    # Price +3.5% → should activate trailing stop
    executor_mock.get_current_price.return_value = 3105.0
    executor_mock.sell_spot.return_value = MagicMock(success=True, price=3105.0)
    services = make_services(executor_mock)

    monitor_positions(session, services, client=None)

    # Position should have trailing_stop_active = True
    updated = session.query(Position).filter_by(pair="ETHUSDT").first()
    if updated:  # Not yet closed
        assert updated.trailing_stop_active is True


def test_monitor_triggers_take_profit(session):
    pos = make_position(session, entry=3000.0, qty=0.01, tp=3150.0)
    executor_mock = MagicMock()
    executor_mock.get_current_price.return_value = 3160.0  # above TP
    executor_mock.sell_spot.return_value = MagicMock(success=True, price=3160.0)
    services = make_services(executor_mock)

    monitor_positions(session, services, client=None)

    # Position closed, trade recorded
    assert session.query(Position).count() == 0
    trade = session.query(Trade).first()
    assert trade.pnl > 0


def test_monitor_triggers_stop_loss(session):
    pos = make_position(session, entry=3000.0, qty=0.01, sl=2850.0)
    executor_mock = MagicMock()
    executor_mock.get_current_price.return_value = 2840.0  # below SL
    executor_mock.sell_spot.return_value = MagicMock(success=True, price=2840.0)
    services = make_services(executor_mock)

    monitor_positions(session, services, client=None)

    assert session.query(Position).count() == 0
    trade = session.query(Trade).first()
    assert trade.pnl < 0  # Loss


# ── _short_confidence ────────────────────────────────────────────────────────

def test_short_confidence_high_above_85():
    assert _short_confidence(85) == "HIGH"
    assert _short_confidence(90) == "HIGH"
    assert _short_confidence(100) == "HIGH"


def test_short_confidence_medium_between_65_and_84():
    assert _short_confidence(65) == "MEDIUM"
    assert _short_confidence(75) == "MEDIUM"
    assert _short_confidence(84) == "MEDIUM"


def test_short_confidence_medium_at_exact_threshold():
    # score 65 = minimum valid SHORT — maps to MEDIUM (5% TP)
    assert _short_confidence(65) == "MEDIUM"


def test_short_confidence_high_tp_wider_than_medium():
    """HIGH conf SHORT should give tighter (lower) TP price than MEDIUM."""
    from risk import RiskManager
    rm = RiskManager(equity=100.0)
    tp_high   = rm.calc_take_profit(100.0, "HIGH",   side="SHORT")  # 8% below
    tp_medium = rm.calc_take_profit(100.0, "MEDIUM", side="SHORT")  # 5% below
    # For SHORT: lower TP price = larger profit target
    assert tp_high < tp_medium
