import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import APIRouter, Query
from db import get_session
from models import Trade

router = APIRouter()


@router.get("/trades")
def get_trades(pair: str = Query(None), limit: int = Query(50, le=500)):
    """List closed trades, newest first. Optionally filter by pair."""
    session = get_session()
    try:
        q = session.query(Trade).filter(Trade.pnl.isnot(None))
        if pair:
            q = q.filter(Trade.pair == pair)
        trades = q.order_by(Trade.id.desc()).limit(limit).all()
        return [
            {
                "id": t.id,
                "pair": t.pair,
                "side": t.side,
                "market_type": getattr(t, "market_type", "SPOT"),
                "price": t.price,
                "qty": t.qty,
                "usdt_value": t.usdt_value,
                "pnl": t.pnl,
                "conviction_score": t.conviction_score,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in trades
        ]
    finally:
        session.close()
