import os
import sys

# Reuse engine models at runtime (shared Docker volume mount at /app/engine)
_engine_path = os.path.join(os.path.dirname(__file__), "..", "..", "engine")
if _engine_path not in sys.path:
    sys.path.insert(0, os.path.abspath(_engine_path))

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///trading.db")

_engine = None


def _get_engine():
    global _engine
    if _engine is None:
        _engine = create_engine(
            DATABASE_URL,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_session() -> Session:
    return Session(_get_engine())
