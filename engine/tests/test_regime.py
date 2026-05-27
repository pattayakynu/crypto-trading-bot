import pytest
from unittest.mock import patch
import regime as regime_module
from regime import RegimeDetector, MarketRegime


def setup_function():
    """Reset module-level cache before each test."""
    regime_module._regime_cache = {"value": None, "ts": 0.0}


def make_detector():
    return RegimeDetector(client=None)


def test_bull_regime_btc_up_dxy_flat():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=7.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == MarketRegime.BULL


def test_bear_regime_btc_down():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=-6.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.0):
        assert d.detect() == MarketRegime.BEAR


def test_bear_regime_dxy_strong_overrides_btc_up():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=8.0), \
         patch.object(d, "get_dxy_10d_change", return_value=2.0):
        assert d.detect() == MarketRegime.BEAR


def test_sideways_regime_btc_moderate_dxy_flat():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=2.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == MarketRegime.SIDEWAYS


def test_sideways_regime_btc_flat():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=0.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.0):
        assert d.detect() == MarketRegime.SIDEWAYS


def test_detect_returns_valid_regime_string():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=0.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.0):
        result = d.detect()
        assert result in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)


def test_cache_prevents_second_fetch():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=7.0) as mock_btc, \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        d.detect()
        d.detect()
        assert mock_btc.call_count == 1   # Only called once — second hit uses cache


def test_btc_7d_change_returns_zero_on_network_error():
    d = make_detector()
    with patch("regime.httpx.get", side_effect=Exception("timeout")):
        assert d.get_btc_7d_change() == 0.0


# ── Hysteresis tests ──────────────────────────────────────────────────────────

def test_hysteresis_stays_bull_when_btc_drops_above_exit_threshold():
    """Once in BULL, stay BULL when BTC 7d drops to 3% (above 2% exit threshold)."""
    d = make_detector()
    # Warm up cache with BULL
    with patch.object(d, "get_btc_7d_change", return_value=7.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == "BULL"

    # Expire cache so next call re-evaluates
    regime_module._regime_cache["ts"] = 0.0

    # BTC drops to 3% — above the 2% exit threshold → stay BULL
    with patch.object(d, "get_btc_7d_change", return_value=3.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == "BULL"


def test_hysteresis_exits_bull_when_btc_drops_below_exit_threshold():
    """Once in BULL, exit to SIDEWAYS when BTC 7d falls below 2%."""
    d = make_detector()
    # Warm up cache with BULL
    with patch.object(d, "get_btc_7d_change", return_value=7.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == "BULL"

    # Expire cache
    regime_module._regime_cache["ts"] = 0.0

    # BTC drops to 1.5% — below 2% exit threshold → SIDEWAYS
    with patch.object(d, "get_btc_7d_change", return_value=1.5), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == "SIDEWAYS"


def test_hysteresis_exits_bull_to_bear_on_dxy_spike():
    """DXY spike overrides hysteresis — exit BULL directly to BEAR."""
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=7.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == "BULL"

    regime_module._regime_cache["ts"] = 0.0

    # DXY spikes to 2% while BTC still up — strong dollar overrides BULL
    with patch.object(d, "get_btc_7d_change", return_value=4.0), \
         patch.object(d, "get_dxy_10d_change", return_value=2.0):
        assert d.detect() == "BEAR"
