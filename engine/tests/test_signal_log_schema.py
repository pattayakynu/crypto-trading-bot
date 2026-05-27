"""Test: SignalLog model có 3 cột short mới, nullable, backward-compatible."""
import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, inspect
from db import Base, SignalLog, init_db


def _fresh_engine():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def test_signal_log_has_short_columns():
    engine = _fresh_engine()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("signal_log")}
    assert "short_total_score" in cols
    assert "short_regime" in cols
    assert "short_scores" in cols


def test_short_columns_are_nullable():
    engine = _fresh_engine()
    inspector = inspect(engine)
    col_map = {c["name"]: c for c in inspector.get_columns("signal_log")}
    assert col_map["short_total_score"]["nullable"] is True
    assert col_map["short_regime"]["nullable"] is True
    assert col_map["short_scores"]["nullable"] is True


def test_old_row_without_short_data():
    """Rows cũ không có short data — không crash khi đọc."""
    from sqlalchemy.orm import Session
    engine = _fresh_engine()
    with Session(engine) as s:
        s.add(SignalLog(pair="BTCUSDT", total_score=60, layer_scores="{}", action="BUY"))
        s.commit()
        row = s.query(SignalLog).first()
    assert row.short_total_score is None
    assert row.short_regime is None
    assert row.short_scores is None


def test_new_row_with_short_data():
    """Rows mới có đủ short data — ghi và đọc đúng."""
    import json
    from sqlalchemy.orm import Session
    engine = _fresh_engine()
    scores = {"alt_weakness": 0, "funding_reset": 15, "volume_exhaustion": 25, "macro_bearish": 0}
    with Session(engine) as s:
        s.add(SignalLog(
            pair="ETHUSDT", total_score=45, layer_scores="{}", action="SKIP",
            short_total_score=40, short_regime="SIDEWAYS",
            short_scores=json.dumps(scores),
        ))
        s.commit()
        row = s.query(SignalLog).first()
    assert row.short_total_score == 40
    assert row.short_regime == "SIDEWAYS"
    assert json.loads(row.short_scores)["funding_reset"] == 15
