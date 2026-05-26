"""
SQLAlchemy models for the telegram service.
Mirrors engine/db.py — both services share the same SQLite volume (/data/trading.db).
"""
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


def get_engine():
    return create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


def init_db(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.query(LayerWeight).count() == 0:
            for name in ["whale", "macro", "fiat_flow", "btc_lead", "ta", "social"]:
                session.add(LayerWeight(name=name, weight=1.0))
            session.commit()
