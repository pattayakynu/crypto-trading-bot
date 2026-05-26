import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from fastapi import APIRouter
from db import get_session
from models import Trade, Performance

router = APIRouter()


@router.get("/performance")
def get_performance():
    """Return equity curve, total PnL, trade stats."""
    session = get_session()
    try:
        equity_rows = (
            session.query(Performance)
            .order_by(Performance.recorded_at)
            .all()
        )
        closed_trades = session.query(Trade).filter(Trade.pnl.isnot(None)).all()
        total_pnl = sum(t.pnl for t in closed_trades)
        wins = sum(1 for t in closed_trades if t.pnl > 0)
        losses = sum(1 for t in closed_trades if t.pnl <= 0)
        win_rate = (wins / len(closed_trades) * 100) if closed_trades else 0.0

        return {
            "equity_curve": [
                {
                    "equity": p.equity,
                    "recorded_at": p.recorded_at.isoformat() if p.recorded_at else None,
                }
                for p in equity_rows
            ],
            "total_pnl": round(total_pnl, 4),
            "total_trades": len(closed_trades),
            "wins": wins,
            "losses": losses,
            "win_rate": round(win_rate, 1),
        }
    finally:
        session.close()
