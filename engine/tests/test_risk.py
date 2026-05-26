import pytest
from risk import RiskManager, TRAILING_STOP_ACTIVATE_PCT, TRAILING_STOP_DISTANCE_PCT, BINANCE_FEE


def make_rm(equity=100.0):
    return RiskManager(equity=equity)


# ── Position sizing ──────────────────────────────────────────────────────────

def test_high_confidence_uses_max_pct():
    rm = make_rm(equity=100.0)
    size = rm.calc_position_size(conviction_score=80, confidence="HIGH")
    assert size <= 50.0  # max 50% of equity
    assert size >= 10.0  # min 10 USDT


def test_medium_confidence_smaller_than_high():
    rm = make_rm(equity=100.0)
    high = rm.calc_position_size(conviction_score=80, confidence="HIGH")
    med = rm.calc_position_size(conviction_score=60, confidence="MEDIUM")
    assert med <= high


def test_position_size_zero_when_equity_too_small():
    rm = make_rm(equity=10.0)  # 50% of 10 = 5, below MIN_POSITION_USDT=10
    size = rm.calc_position_size(conviction_score=55, confidence="MEDIUM")
    assert size == 0.0  # Can't trade — not enough equity


def test_position_size_capped_at_max_pct():
    rm = make_rm(equity=1000.0)
    size = rm.calc_position_size(conviction_score=100, confidence="HIGH")
    assert size <= 500.0  # Max 50% of 1000


# ── Stop-loss ────────────────────────────────────────────────────────────────

def test_sl_long_below_entry():
    rm = make_rm()
    sl = rm.calc_stop_loss(entry_price=100.0, side="LONG")
    assert sl < 100.0
    assert sl == pytest.approx(95.0)  # 5% below


def test_sl_short_above_entry():
    rm = make_rm()
    sl = rm.calc_stop_loss(entry_price=100.0, side="SHORT")
    assert sl > 100.0
    assert sl == pytest.approx(105.0)  # 5% above


# ── Take-profit ──────────────────────────────────────────────────────────────

def test_tp_high_confidence_long():
    rm = make_rm()
    tp = rm.calc_take_profit(entry_price=100.0, confidence="HIGH", side="LONG")
    assert tp == pytest.approx(108.0)  # 8% above


def test_tp_medium_confidence_long():
    rm = make_rm()
    tp = rm.calc_take_profit(entry_price=100.0, confidence="MEDIUM", side="LONG")
    assert tp == pytest.approx(105.0)  # 5% above


def test_tp_high_confidence_short():
    rm = make_rm()
    tp = rm.calc_take_profit(entry_price=100.0, confidence="HIGH", side="SHORT")
    assert tp == pytest.approx(92.0)  # 8% below


# ── Trailing stop ────────────────────────────────────────────────────────────

def test_trailing_stop_activates_at_threshold():
    rm = make_rm()
    # 3% profit = should activate
    assert rm.should_activate_trailing_stop(entry_price=100.0, current_price=103.0, side="LONG") is True


def test_trailing_stop_not_yet_active():
    rm = make_rm()
    assert rm.should_activate_trailing_stop(entry_price=100.0, current_price=101.0, side="LONG") is False


def test_trailing_stop_price_long():
    rm = make_rm()
    # Highest = 110, trail 1.5% below
    trail = rm.calc_trailing_stop(highest_price=110.0, side="LONG")
    assert trail == pytest.approx(110.0 * (1 - TRAILING_STOP_DISTANCE_PCT))


def test_trailing_stop_triggers_when_price_falls():
    rm = make_rm()
    # Highest 110, trail at ~108.35. Current = 107 → should trigger
    assert rm.should_trailing_stop(
        current_price=107.0, highest_price=110.0,
        trailing_stop_active=True, side="LONG"
    ) is True


def test_trailing_stop_no_trigger_if_inactive():
    rm = make_rm()
    assert rm.should_trailing_stop(
        current_price=107.0, highest_price=110.0,
        trailing_stop_active=False, side="LONG"
    ) is False


# ── SL/TP checks ─────────────────────────────────────────────────────────────

def test_stop_loss_triggered_long():
    rm = make_rm()
    assert rm.should_stop_loss(entry_price=100.0, current_price=94.0, stop_loss=95.0, side="LONG") is True


def test_stop_loss_not_triggered_long():
    rm = make_rm()
    assert rm.should_stop_loss(entry_price=100.0, current_price=96.0, stop_loss=95.0, side="LONG") is False


def test_take_profit_triggered_long():
    rm = make_rm()
    assert rm.should_take_profit(current_price=106.0, take_profit=105.0, side="LONG") is True


def test_take_profit_not_triggered_long():
    rm = make_rm()
    assert rm.should_take_profit(current_price=103.0, take_profit=105.0, side="LONG") is False


# ── PnL calculation ──────────────────────────────────────────────────────────

def test_pnl_profitable_long():
    rm = make_rm()
    # Buy 1 coin at 100, sell at 110
    pnl = rm.calc_pnl(entry_price=100.0, exit_price=110.0, qty=1.0, side="LONG")
    # Gross = 10, fees = (100+110)*1*0.001 = 0.21
    assert pnl == pytest.approx(10.0 - 0.21, abs=0.01)


def test_pnl_losing_long():
    rm = make_rm()
    pnl = rm.calc_pnl(entry_price=100.0, exit_price=95.0, qty=1.0, side="LONG")
    assert pnl < 0


def test_pnl_short_profitable():
    rm = make_rm()
    # Short at 100, close at 90
    pnl = rm.calc_pnl(entry_price=100.0, exit_price=90.0, qty=1.0, side="SHORT")
    assert pnl > 0


# ── Qty calculation ───────────────────────────────────────────────────────────

def test_calc_qty_basic():
    rm = make_rm()
    qty = rm.calc_qty(usdt_size=100.0, price=50.0)
    assert qty == pytest.approx(2.0)


def test_calc_qty_zero_price_safe():
    rm = make_rm()
    assert rm.calc_qty(usdt_size=100.0, price=0.0) == 0.0


# ── Position limit ────────────────────────────────────────────────────────────

def test_position_allowed_when_under_limit():
    rm = make_rm()
    assert rm.is_position_allowed(open_positions_count=1) is True


def test_position_blocked_at_limit():
    rm = make_rm()
    assert rm.is_position_allowed(open_positions_count=2) is False
