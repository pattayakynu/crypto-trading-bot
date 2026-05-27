from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, create_engine
from sqlalchemy.orm import DeclarativeBase, Session
import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///trading.db")


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"
    id = Column(Integer, primary_key=True)
    pair = Column(String, nullable=False)
    side = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    usdt_value = Column(Float, nullable=False)
    pnl = Column(Float, nullable=True)
    conviction_score = Column(Integer, nullable=True)
    market_type = Column(String, default="SPOT")
    created_at = Column(DateTime, default=datetime.utcnow)


class Position(Base):
    __tablename__ = "positions"
    id = Column(Integer, primary_key=True)
    pair = Column(String, nullable=False, unique=True)
    market_type = Column(String, default="SPOT")
    side = Column(String, default="LONG")
    entry_price = Column(Float, nullable=False)
    qty = Column(Float, nullable=False)
    usdt_value = Column(Float, nullable=False)
    stop_loss = Column(Float, nullable=False)
    take_profit = Column(Float, nullable=False)
    trailing_stop_active = Column(Boolean, default=False)
    highest_price = Column(Float, nullable=True)
    conviction_score = Column(Integer, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)


class LayerWeight(Base):
    __tablename__ = "layer_weights"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    weight = Column(Float, nullable=False, default=1.0)
    updated_at = Column(DateTime, default=datetime.utcnow)


class PairBlacklist(Base):
    __tablename__ = "pair_blacklist"
    id = Column(Integer, primary_key=True)
    pair = Column(String, nullable=False, unique=True)
    expires_at = Column(DateTime, nullable=False)
    reason = Column(String, nullable=True)


class Performance(Base):
    __tablename__ = "performance"
    id = Column(Integer, primary_key=True)
    equity = Column(Float, nullable=False)
    recorded_at = Column(DateTime, default=datetime.utcnow)


class SignalLog(Base):
    __tablename__ = "signal_log"
    id = Column(Integer, primary_key=True)
    pair = Column(String, nullable=False)
    total_score = Column(Integer, nullable=False)
    layer_scores = Column(String, nullable=True)
    action = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # ShortBrain fields — nullable for backward compatibility (old rows = NULL)
    short_total_score = Column(Integer, nullable=True)
    short_regime      = Column(String,  nullable=True)
    short_scores      = Column(String,  nullable=True)  # JSON string


def get_engine():
    return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def _migrate_signal_log(engine):
    """Add short_* columns to signal_log if they don't exist yet (idempotent)."""
    from sqlalchemy import text, inspect as sa_inspect
    inspector = sa_inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("signal_log")}
    migrations = [
        ("short_total_score", "INTEGER"),
        ("short_regime",      "TEXT"),
        ("short_scores",      "TEXT"),
    ]
    with engine.connect() as conn:
        for col_name, col_type in migrations:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE signal_log ADD COLUMN {col_name} {col_type}"))
        conn.commit()


def init_db(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.query(LayerWeight).count() == 0:
            for name in ["whale", "macro", "fiat_flow", "btc_lead", "ta", "social"]:
                session.add(LayerWeight(name=name, weight=1.0))
            session.commit()
    # Migrate existing signal_log table — add short columns if missing
    _migrate_signal_log(engine)
