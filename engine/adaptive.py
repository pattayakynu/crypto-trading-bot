from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session
from db import LayerWeight, PairBlacklist, Performance

# Adaptive learning config
WEIGHT_ADJUST_STEP = 0.05       # Adjust weights by 5% per closed trade
WEIGHT_MIN = 0.3                # Floor — never ignore a layer completely
WEIGHT_MAX = 2.0                # Ceiling — never overweight too much
PROFITABLE_THRESHOLD = 0.0      # PnL > 0 = profitable trade

# Drawdown guard
DRAWDOWN_GUARD_PCT = 0.20       # Stop trading if drawdown > 20% from peak
DRAWDOWN_RESUME_PCT = 0.10      # Resume if recovered to within 10% of peak

# Pair blacklist
DEFAULT_BLACKLIST_HOURS = 24    # Blacklist a pair for 24h after a loss


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AdaptiveLearner:
    def __init__(self, db_session: Session):
        self.session = db_session

    # ── LayerWeight management ──────────────────────────────────────────────

    def get_weights(self) -> dict:
        """Load all layer weights from DB. Returns {name: weight}."""
        rows = self.session.query(LayerWeight).all()
        return {row.name: row.weight for row in rows}

    def update_weights_after_trade(self, layer_scores: dict, pnl: float) -> dict:
        """
        After a trade closes, adjust weights based on which layers contributed
        and whether the trade was profitable.

        - Profitable trade: increase weight of layers that scored highest (they helped)
        - Losing trade: decrease weight of layers that scored highest (they misled)

        layer_scores: {"whale": 20, "macro": 15, ...}
        pnl: realized profit/loss in USDT
        Returns the updated weights dict.
        """
        profitable = pnl > PROFITABLE_THRESHOLD
        total_score = sum(layer_scores.values()) or 1

        for name, score in layer_scores.items():
            if score <= 0:
                continue  # Layer didn't contribute — skip

            contribution_pct = score / total_score
            adjustment = WEIGHT_ADJUST_STEP * contribution_pct

            row = self.session.query(LayerWeight).filter_by(name=name).first()
            if not row:
                continue

            if profitable:
                row.weight = min(WEIGHT_MAX, row.weight + adjustment)
            else:
                row.weight = max(WEIGHT_MIN, row.weight - adjustment)

        self.session.commit()
        return self.get_weights()

    def reset_weights(self) -> None:
        """Reset all layer weights back to 1.0."""
        for row in self.session.query(LayerWeight).all():
            row.weight = 1.0
        self.session.commit()

    # ── Pair blacklist ──────────────────────────────────────────────────────

    def blacklist_pair(self, pair: str, reason: str, hours: int = DEFAULT_BLACKLIST_HOURS) -> None:
        """Add a pair to the blacklist after a bad trade."""
        expires_at = _now() + timedelta(hours=hours)
        existing = self.session.query(PairBlacklist).filter_by(pair=pair).first()
        if existing:
            existing.expires_at = expires_at
            existing.reason = reason
        else:
            self.session.add(PairBlacklist(pair=pair, expires_at=expires_at, reason=reason))
        self.session.commit()

    def is_blacklisted(self, pair: str) -> bool:
        """Check if a pair is currently blacklisted."""
        row = self.session.query(PairBlacklist).filter_by(pair=pair).first()
        if not row:
            return False
        if _now() >= row.expires_at:
            self.session.delete(row)
            self.session.commit()
            return False
        return True

    def clear_expired_blacklists(self) -> int:
        """Remove expired blacklist entries. Returns count removed."""
        now = _now()
        expired = self.session.query(PairBlacklist).filter(PairBlacklist.expires_at <= now).all()
        count = len(expired)
        for row in expired:
            self.session.delete(row)
        self.session.commit()
        return count

    # ── Drawdown guard ──────────────────────────────────────────────────────

    def record_equity(self, equity: float) -> None:
        """Record current equity snapshot."""
        self.session.add(Performance(equity=equity, recorded_at=_now()))
        self.session.commit()

    def get_peak_equity(self) -> float:
        """Return the highest equity ever recorded."""
        rows = self.session.query(Performance).order_by(Performance.equity.desc()).first()
        return rows.equity if rows else 0.0

    def check_drawdown(self, current_equity: float) -> dict:
        """
        Check if drawdown guard should trigger.
        Returns {"halted": bool, "drawdown_pct": float, "peak": float}
        """
        peak = self.get_peak_equity()
        if peak <= 0:
            return {"halted": False, "drawdown_pct": 0.0, "peak": current_equity}

        drawdown_pct = (peak - current_equity) / peak

        return {
            "halted": drawdown_pct >= DRAWDOWN_GUARD_PCT,
            "drawdown_pct": round(drawdown_pct, 4),
            "peak": peak,
        }
