import pytest
from unittest.mock import MagicMock, patch
import regime as regime_module
from regime import MarketRegime
from short_brain import ShortBrain, ShortSignal, SHORT_THRESHOLD


def setup_function():
    regime_module._regime_cache = {"value": None, "ts": 0.0}


def make_brain(client=None):
    return ShortBrain(client=client)


def _make_klines(closes, volumes):
    """Build minimal klines: [open_time, open, high, low, close, volume, ...]"""
    rows = []
    for c, v in zip(closes, volumes):
        rows.append([0, "0", "0", "0", str(c), str(v), 0, "0", 0, "0", "0", "0"])
    return rows


# ── Signal 1: Alt Weakness ────────────────────────────────────────────────────

def test_alt_falling_btc_stable_max_score():
    b = make_brain()
    assert b.score_alt_weakness(btc_change=0.2, alt_change=-1.5) == 25


def test_alt_falling_into_btc_strength():
    b = make_brain()
    assert b.score_alt_weakness(btc_change=1.0, alt_change=-0.8) == 20


def test_alt_not_following_btc_pump():
    b = make_brain()
    # BTC +2%, alt +0.3% = follow_ratio 0.15 < 0.30 = very weak
    assert b.score_alt_weakness(btc_change=2.0, alt_change=0.3) == 15


def test_alt_moderate_underperformance():
    b = make_brain()
    # BTC +2%, alt +0.8% = follow_ratio 0.40 < 0.60 = moderately weak
    assert b.score_alt_weakness(btc_change=2.0, alt_change=0.8) == 10


def test_alt_following_btc_no_weakness():
    b = make_brain()
    # BTC +2%, alt +1.8% = follow_ratio 0.90 = following fine
    assert b.score_alt_weakness(btc_change=2.0, alt_change=1.8) == 0


def test_both_flat_no_signal():
    b = make_brain()
    assert b.score_alt_weakness(btc_change=0.1, alt_change=0.1) == 0


# ── Signal 2: Funding Reset ───────────────────────────────────────────────────

def test_funding_reset_detected():
    b = make_brain()
    b.get_funding_history = MagicMock(
        return_value=[0.00015, 0.00012, 0.0001, 0.00008, 0.00002]
    )
    assert b.score_funding_reset("ETHUSDT") == 25


def test_funding_partial_reset():
    b = make_brain()
    b.get_funding_history = MagicMock(
        return_value=[0.00008, 0.00007, 0.00006, 0.00005, 0.00005]
    )
    assert b.score_funding_reset("ETHUSDT") == 15


def test_funding_still_high_no_reset():
    b = make_brain()
    b.get_funding_history = MagicMock(
        return_value=[0.00015, 0.00014, 0.00013, 0.00012, 0.00011]
    )
    assert b.score_funding_reset("ETHUSDT") == 0


def test_funding_negative_returns_zero():
    b = make_brain()
    b.get_funding_history = MagicMock(
        return_value=[0.0001, 0.00005, 0.0, -0.00003, -0.0001]
    )
    assert b.score_funding_reset("ETHUSDT") == 0


def test_funding_no_history_returns_zero():
    b = make_brain()
    b.get_funding_history = MagicMock(return_value=[])
    assert b.score_funding_reset("ETHUSDT") == 0


def test_funding_no_client_returns_empty_history():
    b = make_brain(client=None)
    assert b.get_funding_history("ETHUSDT") == []


# ── Signal 3: Volume Exhaustion ───────────────────────────────────────────────

def test_volume_exhaustion_strong():
    b = make_brain()
    closes = [100.0] * 17 + [105.0, 104.8, 105.1]
    # baseline avg = 1000.0; recent avg = (600+500+400)/3 = 500 → ratio 0.50 ≤ 0.55
    volumes = [1000.0] * 17 + [600.0, 500.0, 400.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 25


def test_volume_exhaustion_moderate():
    b = make_brain()
    closes = [100.0] * 17 + [105.0, 104.8, 105.1]
    # baseline avg = 1000.0; recent avg = (850+800+750)/3 ≈ 800 → ratio 0.80 ≤ 0.85
    volumes = [1000.0] * 17 + [850.0, 800.0, 750.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 15


def test_no_exhaustion_volume_not_declining():
    b = make_brain()
    closes = [100.0] * 17 + [105.0, 104.8, 105.1]
    # recent avg = (900+950+1100)/3 ≈ 983 ≥ baseline 1000 → not declining
    volumes = [1000.0] * 17 + [900.0, 950.0, 1100.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 0


def test_no_exhaustion_price_not_near_high():
    b = make_brain()
    closes = [105.0] * 10 + [90.0] * 10   # Price dropped well away from high
    volumes = [1000.0] * 17 + [900.0, 700.0, 500.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 0


def test_volume_no_client_returns_zero():
    b = make_brain(client=None)
    assert b.score_volume_exhaustion("ETHUSDT") == 0


# ── Signal 4: Macro Bearish ───────────────────────────────────────────────────

def test_macro_bearish_strong_dxy():
    b = make_brain()
    # DXY +1.6% ≥ strong threshold (1.5)
    with patch("macro.dxy_change_pct", return_value=1.6):
        assert b.score_macro_bearish() == 25


def test_macro_bearish_moderate_dxy():
    b = make_brain()
    # DXY +1.12% — between moderate (1.0) and strong (1.5)
    with patch("macro.dxy_change_pct", return_value=1.12):
        assert b.score_macro_bearish() == 15


def test_macro_bullish_dxy_falling():
    b = make_brain()
    # DXY falling → no bearish signal
    with patch("macro.dxy_change_pct", return_value=-0.8):
        assert b.score_macro_bearish() == 0


# ── get_short_signal: risk filters ───────────────────────────────────────────

def test_blocked_in_bull_regime():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BULL):
        sig = b.get_short_signal(
            "ETHUSDT", btc_change=2.0, alt_change=-1.0, has_open_long=False
        )
    assert sig.should_short is False
    assert sig.blocked_reason is not None
    assert "BULL" in sig.blocked_reason


def test_blocked_by_open_long():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(return_value=[0.0001])
        sig = b.get_short_signal(
            "ETHUSDT", btc_change=0.0, alt_change=-1.5, has_open_long=True
        )
    assert sig.should_short is False
    assert "LONG" in sig.blocked_reason


def test_blocked_by_very_negative_funding():
    """Only VERY negative funding (< -0.02%) should block — not slightly negative."""
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(return_value=[-0.0003])  # -0.03% = very negative
        sig = b.get_short_signal(
            "ETHUSDT", btc_change=0.0, alt_change=-1.5, has_open_long=False
        )
    assert sig.should_short is False
    assert "negative" in sig.blocked_reason.lower()


def test_slightly_negative_funding_not_blocked():
    """Slightly negative funding (-0.01%) is normal in bear market — should NOT block."""
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(return_value=[-0.0001])  # -0.01% = slightly negative
        b.get_klines = MagicMock(return_value=[])
        with patch("short_brain.yf.Ticker") as mock_yf:
            import pandas as pd
            mock_yf.return_value.history.return_value = pd.DataFrame(
                {"Close": [25.0] * 10 + [25.0]}
            )
            sig = b.get_short_signal(
                "ETHUSDT", btc_change=0.2, alt_change=-1.5, has_open_long=False
            )
    assert sig.blocked_reason is None  # Not blocked by funding


def test_should_short_above_threshold():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(
            return_value=[0.00015, 0.0001, 0.00005, 0.00003, 0.00001]
        )
        b.get_klines = MagicMock(return_value=_make_klines(
            [100.0] * 17 + [105.0, 104.8, 105.1],
            [1000.0] * 17 + [900.0, 600.0, 450.0],
        ))
        with patch("short_brain.yf.Ticker") as mock_yf:
            import pandas as pd
            mock_yf.return_value.history.return_value = pd.DataFrame(
                {"Close": [25.0] * 10 + [25.4]}
            )
            sig = b.get_short_signal(
                "ETHUSDT", btc_change=0.2, alt_change=-1.5, has_open_long=False
            )
    assert sig.score >= SHORT_THRESHOLD
    assert sig.should_short is True
    assert sig.regime == MarketRegime.BEAR


def test_signal_scores_populated_in_result():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.SIDEWAYS):
        b.get_funding_history = MagicMock(return_value=[0.0])
        b.get_klines = MagicMock(return_value=[])
        with patch("short_brain.yf.Ticker") as mock_yf:
            import pandas as pd
            mock_yf.return_value.history.return_value = pd.DataFrame(
                {"Close": [25.0] * 10 + [25.0]}
            )
            sig = b.get_short_signal(
                "ETHUSDT", btc_change=0.2, alt_change=-1.5, has_open_long=False
            )
    assert "alt_weakness"      in sig.signal_scores
    assert "funding_reset"     in sig.signal_scores
    assert "volume_exhaustion" in sig.signal_scores
    assert "macro_bearish"     in sig.signal_scores
    assert "trend_breakdown"   in sig.signal_scores


# ── Signal 5: Trend Breakdown ────────────────────────────────────────────────

def test_trend_breakdown_strong_downtrend_weak_bounce():
    """Price 12% below high, 1% bounce, weak volume → 25 pts."""
    b = make_brain()
    # Period high = 100, current = 88 → decline 12% (≥10%)
    # recent_low (last 7 excl current) = 87, current = 88 → bounce 1.15% (in 0.5%-5%)
    closes  = [100.0] * 13 + [90.0, 88.0, 87.0, 87.5, 88.0, 87.0, 88.0]
    volumes = [1000.0] * 17 + [700.0, 650.0, 680.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_trend_breakdown("ETHUSDT") == 25


def test_trend_breakdown_moderate_downtrend():
    """Price 7% below high, valid bounce, weak volume → 15 pts."""
    b = make_brain()
    closes  = [100.0] * 13 + [94.0, 93.0, 93.0, 93.0, 93.5, 93.0, 93.5]
    volumes = [1000.0] * 17 + [700.0, 650.0, 680.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    score = b.score_trend_breakdown("ETHUSDT")
    assert score == 15


def test_trend_breakdown_no_signal_price_near_high():
    """Price near high → volume_exhaustion territory, not trend breakdown."""
    b = make_brain()
    closes  = [100.0] * 17 + [99.0, 98.5, 99.5]
    volumes = [1000.0] * 17 + [700.0, 650.0, 680.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_trend_breakdown("ETHUSDT") == 0


def test_trend_breakdown_no_signal_strong_volume_bounce():
    """Strong volume on bounce = real recovery, not dead cat."""
    b = make_brain()
    closes  = [100.0] * 13 + [90.0, 88.0, 87.0, 87.5, 88.0, 87.0, 88.0]
    volumes = [500.0] * 17 + [900.0, 1100.0, 1200.0]  # Volume increasing = real
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_trend_breakdown("ETHUSDT") == 0


def test_trend_breakdown_no_signal_bounce_too_large():
    """Bounce > 5% = might be real recovery, skip."""
    b = make_brain()
    # recent_low = 80, current = 87 → bounce 8.75% > 5%
    closes  = [100.0] * 13 + [85.0, 82.0, 80.0, 81.0, 83.0, 82.0, 87.0]
    volumes = [1000.0] * 17 + [700.0, 650.0, 680.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_trend_breakdown("ETHUSDT") == 0
