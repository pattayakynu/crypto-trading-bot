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
