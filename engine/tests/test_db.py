import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db import Base, Trade, Position, LayerWeight, PairBlacklist, Performance, SignalLog


def make_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def test_trade_has_conviction_score():
    session = make_session()
    trade = Trade(pair="SOLUSDT", side="BUY", price=33.20,
                  qty=1.0, usdt_value=33.20, conviction_score=78)
    session.add(trade)
    session.commit()
    t = session.query(Trade).first()
    assert t.conviction_score == 78


def test_layer_weights_initialized():
    session = make_session()
    for name in ["whale", "macro", "fiat_flow", "btc_lead", "ta", "social"]:
        session.add(LayerWeight(name=name, weight=1.0))
    session.commit()
    assert session.query(LayerWeight).count() == 6


def test_signal_log_stores_breakdown():
    session = make_session()
    log = SignalLog(
        pair="SOLUSDT",
        total_score=78,
        layer_scores='{"whale":18,"macro":12,"fiat_flow":8,"btc_lead":15,"ta":10,"social":15}',
        action="BUY"
    )
    session.add(log)
    session.commit()
    assert session.query(SignalLog).count() == 1


def test_position_supports_short():
    session = make_session()
    pos = Position(
        pair="BTCUSDT", market_type="FUTURES", side="SHORT",
        entry_price=60000.0, qty=0.001, usdt_value=60.0,
        stop_loss=63000.0, take_profit=57000.0
    )
    session.add(pos)
    session.commit()
    p = session.query(Position).first()
    assert p.side == "SHORT"
    assert p.market_type == "FUTURES"
