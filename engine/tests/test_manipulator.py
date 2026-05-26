import pytest
from manipulator import ManipulationFilter, ManipulationResult


def test_fake_pump_detected_when_futures_driven():
    mf = ManipulationFilter()
    result = mf.check_btc_pump(btc_change_pct=2.1, spot_futures_ratio=0.3)
    assert result == ManipulationResult.FAKE_PUMP


def test_real_pump_passes():
    mf = ManipulationFilter()
    result = mf.check_btc_pump(btc_change_pct=2.1, spot_futures_ratio=0.75)
    assert result == ManipulationResult.CLEAN


def test_small_btc_move_always_clean():
    mf = ManipulationFilter()
    result = mf.check_btc_pump(btc_change_pct=0.8, spot_futures_ratio=0.2)
    assert result == ManipulationResult.CLEAN


def test_stop_hunt_detected():
    mf = ManipulationFilter()
    result = mf.check_stop_hunt(
        support_level=33.00,
        low_price=32.86,
        current_price=33.15,
        minutes_elapsed=2
    )
    assert result == ManipulationResult.STOP_HUNT_REVERSAL


def test_no_stop_hunt_if_price_stays_below():
    mf = ManipulationFilter()
    result = mf.check_stop_hunt(
        support_level=33.00,
        low_price=32.86,
        current_price=32.90,
        minutes_elapsed=2
    )
    assert result == ManipulationResult.CLEAN


def test_no_stop_hunt_if_dip_too_small():
    mf = ManipulationFilter()
    result = mf.check_stop_hunt(
        support_level=33.00,
        low_price=32.95,   # only 0.15% dip — not a hunt
        current_price=33.10,
        minutes_elapsed=2
    )
    assert result == ManipulationResult.CLEAN


def test_wash_trade_detected():
    mf = ManipulationFilter()
    result = mf.check_wash_trading(volume_ratio=4.0, trade_count_ratio=1.2)
    assert result == ManipulationResult.WASH_TRADE


def test_normal_volume_passes():
    mf = ManipulationFilter()
    result = mf.check_wash_trading(volume_ratio=2.5, trade_count_ratio=2.1)
    assert result == ManipulationResult.CLEAN


def test_spoof_order_detected():
    mf = ManipulationFilter()
    result = mf.check_spoof_order(wall_size_usdt=600_000, wall_age_seconds=15)
    assert result == ManipulationResult.SPOOF_ORDER


def test_old_wall_not_spoof():
    mf = ManipulationFilter()
    result = mf.check_spoof_order(wall_size_usdt=600_000, wall_age_seconds=60)
    assert result == ManipulationResult.CLEAN
