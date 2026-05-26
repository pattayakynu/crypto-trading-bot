import os

# Position sizing
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "2"))
STOP_LOSS_PCT = float(os.getenv("STOP_LOSS_PCT", "0.05"))       # 5% SL default
FUTURES_MAX_LEVERAGE = int(os.getenv("FUTURES_MAX_LEVERAGE", "2"))

# Take-profit tiers based on conviction score
# High conviction → let winners run further
TP_TIERS = {
    "HIGH":   0.08,   # 8% TP for HIGH conviction  (score >= 75)
    "MEDIUM": 0.05,   # 5% TP for MEDIUM conviction (score 55-74)
    "LOW":    0.03,   # 3% TP for WATCH signals (not traded, but for reference)
}

# Trailing stop: activates when price moves > threshold in our favor
TRAILING_STOP_ACTIVATE_PCT = 0.03   # Activate trailing stop at +3% profit
TRAILING_STOP_DISTANCE_PCT = 0.015  # Trail 1.5% below peak price

# Position sizing: Kelly-inspired, scaled by conviction
# base_size * conviction_multiplier, capped at max_pct of equity
BASE_POSITION_PCT = 0.40        # 40% of equity per trade baseline
MAX_POSITION_PCT = 0.50         # Never more than 50% of equity in one trade
MIN_POSITION_USDT = 10.0        # Minimum trade size in USDT

BINANCE_FEE = 0.001             # 0.1% per side, 0.2% round-trip


class RiskManager:
    def __init__(
        self,
        equity: float,
        stop_loss_pct: float = STOP_LOSS_PCT,
        max_positions: int = MAX_POSITIONS,
    ):
        self.equity = equity
        self.stop_loss_pct = stop_loss_pct
        self.max_positions = max_positions

    def calc_position_size(self, conviction_score: int, confidence: str) -> float:
        """
        Position size in USDT based on equity and conviction.
        High conviction → larger position (up to 50% of equity).
        Medium conviction → smaller position (40% of equity).
        """
        if confidence == "HIGH":
            pct = MAX_POSITION_PCT
        else:
            pct = BASE_POSITION_PCT

        # Scale slightly by score within confidence band
        score_factor = min(1.0, conviction_score / 100)
        size = self.equity * pct * score_factor

        # If equity is too small to trade at minimum, return 0 (don't trade)
        max_allowed = self.equity * MAX_POSITION_PCT
        if max_allowed < MIN_POSITION_USDT:
            return 0.0

        size = max(MIN_POSITION_USDT, size)
        size = min(max_allowed, size)
        return round(size, 2)

    def calc_stop_loss(self, entry_price: float, side: str = "LONG") -> float:
        """
        Calculate stop-loss price.
        LONG: SL below entry. SHORT: SL above entry.
        """
        if side == "LONG":
            return round(entry_price * (1 - self.stop_loss_pct), 8)
        else:
            return round(entry_price * (1 + self.stop_loss_pct), 8)

    def calc_take_profit(self, entry_price: float, confidence: str, side: str = "LONG") -> float:
        """
        Calculate take-profit price based on confidence tier.
        """
        tp_pct = TP_TIERS.get(confidence, TP_TIERS["MEDIUM"])
        if side == "LONG":
            return round(entry_price * (1 + tp_pct), 8)
        else:
            return round(entry_price * (1 - tp_pct), 8)

    def calc_trailing_stop(self, highest_price: float, side: str = "LONG") -> float:
        """
        Trailing stop price based on highest seen price since entry.
        Only meaningful after trailing stop is activated.
        """
        if side == "LONG":
            return round(highest_price * (1 - TRAILING_STOP_DISTANCE_PCT), 8)
        else:
            return round(highest_price * (1 + TRAILING_STOP_DISTANCE_PCT), 8)

    def should_activate_trailing_stop(self, entry_price: float, current_price: float, side: str = "LONG") -> bool:
        """
        Trailing stop activates once position is +3% in profit.
        """
        if side == "LONG":
            profit_pct = (current_price - entry_price) / entry_price
        else:
            profit_pct = (entry_price - current_price) / entry_price
        return profit_pct >= TRAILING_STOP_ACTIVATE_PCT

    def should_stop_loss(self, entry_price: float, current_price: float, stop_loss: float, side: str = "LONG") -> bool:
        """Check if current price has hit stop-loss."""
        if side == "LONG":
            return current_price <= stop_loss
        else:
            return current_price >= stop_loss

    def should_take_profit(self, current_price: float, take_profit: float, side: str = "LONG") -> bool:
        """Check if current price has hit take-profit."""
        if side == "LONG":
            return current_price >= take_profit
        else:
            return current_price <= take_profit

    def should_trailing_stop(
        self,
        current_price: float,
        highest_price: float,
        trailing_stop_active: bool,
        side: str = "LONG"
    ) -> bool:
        """Check if trailing stop should trigger."""
        if not trailing_stop_active:
            return False
        trail_price = self.calc_trailing_stop(highest_price, side)
        if side == "LONG":
            return current_price <= trail_price
        else:
            return current_price >= trail_price

    def calc_pnl(self, entry_price: float, exit_price: float, qty: float, side: str = "LONG") -> float:
        """Calculate realized PnL in USDT after fees."""
        if side == "LONG":
            gross = (exit_price - entry_price) * qty
        else:
            gross = (entry_price - exit_price) * qty
        fees = (entry_price + exit_price) * qty * BINANCE_FEE
        return round(gross - fees, 4)

    def calc_qty(self, usdt_size: float, price: float) -> float:
        """Convert USDT position size to coin quantity."""
        if price <= 0:
            return 0.0
        return round(usdt_size / price, 6)

    def is_position_allowed(self, open_positions_count: int) -> bool:
        """Check if we can open another position."""
        return open_positions_count < self.max_positions
