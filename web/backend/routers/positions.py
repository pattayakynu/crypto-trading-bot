import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import APIRouter
from db import get_session
from models import Position

router = APIRouter()


@router.get("/positions")
def get_positions():
    """Return all currently open positions."""
    session = get_session()
    try:
        positions = session.query(Position).all()
        return [
            {
                "pair": p.pair,
                "side": p.side,
                "market_type": p.market_type,
                "entry_price": p.entry_price,
                "qty": p.qty,
                "usdt_value": p.usdt_value,
                "stop_loss": p.stop_loss,
                "take_profit": p.take_profit,
                "trailing_stop_active": p.trailing_stop_active,
                "highest_price": p.highest_price,
                "conviction_score": p.conviction_score,
            }
            for p in positions
        ]
    finally:
        session.close()
