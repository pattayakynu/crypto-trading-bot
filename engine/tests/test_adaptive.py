import pytest
from datetime import datetime, timedelta
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from db import Base, LayerWeight, PairBlacklist, Performance, Trade, init_db
from adaptive import AdaptiveLearner, WEIGHT_MIN, WEIGHT_MAX, DRAWDOWN_GUARD_PCT, MIN_TRADES_BEFORE_ADJUST


@pytest.fixture
def session():
    """In-memory SQLite session for each test."""
    engine = create_engine("sqlite:///:memory:", echo=False)
    init_db(engine)
    Session = sessionmaker(bind=engine)
    sess = Session()
    yield sess
    sess.close()


def make_learner(session):
    return AdaptiveLearner(db_session=session)


def _seed_trades(session, n: int = MIN_TRADES_BEFORE_ADJUST):
    """Insert N dummy closed trades so weight adjustment can proceed."""
    for i in range(n):
        session.add(Trade(
            pair="BTCUSDT", side="LONG", price=50000.0,
            qty=0.001, usdt_value=50.0, pnl=1.0,
            conviction_score=60, market_type="SPOT",
        ))
    session.commit()


# ── LayerWeight tests ────────────────────────────────────────────────────────

def test_get_weights_returns_all_six(session):
    learner = make_learner(session)
    weights = learner.get_weights()
    assert set(weights.keys()) == {"whale", "macro", "fiat_flow", "btc_lead", "ta", "social"}


def test_no_weight_adjustment_below_min_sample(session):
    """Weights stay frozen until MIN_TRADES_BEFORE_ADJUST trades are recorded."""
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    weights_before = learner.get_weights()["whale"]
    # Only 5 trades — below the 30-trade minimum
    _seed_trades(session, n=5)
    learner.update_weights_after_trade(layer_scores, pnl=5.0)
    assert learner.get_weights()["whale"] == weights_before


def test_profitable_trade_increases_dominant_layer(session):
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    _seed_trades(session)   # meet minimum sample
    weights_before = learner.get_weights()["whale"]
    learner.update_weights_after_trade(layer_scores, pnl=5.0)
    weights_after = learner.get_weights()["whale"]
    assert weights_after > weights_before


def test_losing_trade_decreases_dominant_layer(session):
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    _seed_trades(session)
    weights_before = learner.get_weights()["whale"]
    learner.update_weights_after_trade(layer_scores, pnl=-3.0)
    weights_after = learner.get_weights()["whale"]
    assert weights_after < weights_before


def test_weight_never_falls_below_min(session):
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    _seed_trades(session)
    # Apply many losing trades
    for _ in range(100):
        learner.update_weights_after_trade(layer_scores, pnl=-10.0)
    assert learner.get_weights()["whale"] >= WEIGHT_MIN


def test_weight_never_exceeds_max(session):
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    _seed_trades(session)
    # Apply many profitable trades
    for _ in range(100):
        learner.update_weights_after_trade(layer_scores, pnl=10.0)
    assert learner.get_weights()["whale"] <= WEIGHT_MAX


def test_zero_score_layer_not_adjusted(session):
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    _seed_trades(session)
    before = learner.get_weights()["macro"]
    learner.update_weights_after_trade(layer_scores, pnl=5.0)
    after = learner.get_weights()["macro"]
    assert before == after


def test_reset_weights_back_to_one(session):
    learner = make_learner(session)
    layer_scores = {"whale": 25, "macro": 0, "fiat_flow": 0, "btc_lead": 0, "ta": 0, "social": 0}
    _seed_trades(session)
    learner.update_weights_after_trade(layer_scores, pnl=5.0)
    learner.reset_weights()
    for w in learner.get_weights().values():
        assert w == 1.0


# ── Pair blacklist tests ─────────────────────────────────────────────────────

def test_blacklist_pair_and_check(session):
    learner = make_learner(session)
    learner.blacklist_pair("ETHUSDT", "stop loss hit", hours=24)
    assert learner.is_blacklisted("ETHUSDT") is True


def test_non_blacklisted_pair_is_clean(session):
    learner = make_learner(session)
    assert learner.is_blacklisted("BTCUSDT") is False


def test_expired_blacklist_auto_removed(session):
    learner = make_learner(session)
    # Set expiry in the past
    past = datetime.utcnow() - timedelta(hours=1)
    session.add(PairBlacklist(pair="SOLUSDT", expires_at=past, reason="test"))
    session.commit()
    assert learner.is_blacklisted("SOLUSDT") is False
    # Should also be deleted from DB
    assert session.query(PairBlacklist).filter_by(pair="SOLUSDT").first() is None


def test_blacklist_updates_expiry_if_exists(session):
    learner = make_learner(session)
    learner.blacklist_pair("BNBUSDT", "loss 1", hours=1)
    learner.blacklist_pair("BNBUSDT", "loss 2", hours=48)
    row = session.query(PairBlacklist).filter_by(pair="BNBUSDT").first()
    assert (row.expires_at - datetime.utcnow()).total_seconds() > 40 * 3600


def test_clear_expired_blacklists(session):
    learner = make_learner(session)
    past = datetime.utcnow() - timedelta(hours=1)
    session.add(PairBlacklist(pair="X1USDT", expires_at=past, reason="old"))
    session.add(PairBlacklist(pair="X2USDT", expires_at=past, reason="old"))
    session.commit()
    removed = learner.clear_expired_blacklists()
    assert removed == 2


# ── Drawdown guard tests ─────────────────────────────────────────────────────

def test_drawdown_below_threshold_not_halted(session):
    learner = make_learner(session)
    learner.record_equity(100.0)
    result = learner.check_drawdown(current_equity=90.0)
    assert result["halted"] is False
    assert result["drawdown_pct"] == 0.10


def test_drawdown_at_threshold_halts(session):
    learner = make_learner(session)
    learner.record_equity(100.0)
    # Exactly 20% drawdown
    result = learner.check_drawdown(current_equity=80.0)
    assert result["halted"] is True
    assert result["drawdown_pct"] == 0.20


def test_drawdown_beyond_threshold_halts(session):
    learner = make_learner(session)
    learner.record_equity(100.0)
    result = learner.check_drawdown(current_equity=70.0)
    assert result["halted"] is True


def test_no_equity_history_not_halted(session):
    learner = make_learner(session)
    result = learner.check_drawdown(current_equity=100.0)
    assert result["halted"] is False


def test_peak_tracks_highest_equity(session):
    learner = make_learner(session)
    learner.record_equity(80.0)
    learner.record_equity(120.0)
    learner.record_equity(90.0)
    assert learner.get_peak_equity() == 120.0
