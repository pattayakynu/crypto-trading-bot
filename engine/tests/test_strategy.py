import pytest
import pandas as pd
import numpy as np
from strategy import TaStrategy


def make_strategy():
    return TaStrategy()


def make_ohlcv(length: int = 100, trend: str = "up") -> pd.DataFrame:
    """Generate synthetic OHLCV data for testing."""
    np.random.seed(42)
    prices = [100.0]
    for _ in range(length - 1):
        if trend == "up":
            change = np.random.normal(0.003, 0.01)
        elif trend == "down":
            change = np.random.normal(-0.003, 0.01)
        else:
            change = np.random.normal(0, 0.01)
        prices.append(prices[-1] * (1 + change))

    df = pd.DataFrame({
        "open": prices,
        "high": [p * 1.005 for p in prices],
        "low": [p * 0.995 for p in prices],
        "close": prices,
        "volume": [1_000_000] * length,
    })
    return df


# --- RSI scoring ---

def test_rsi_oversold_max():
    s = make_strategy()
    assert s.score_rsi(rsi=28.0) == 4


def test_rsi_leaning_oversold():
    s = make_strategy()
    assert s.score_rsi(rsi=38.0) == 3


def test_rsi_neutral():
    s = make_strategy()
    assert s.score_rsi(rsi=52.0) == 2


def test_rsi_hot():
    s = make_strategy()
    assert s.score_rsi(rsi=65.0) == 1


def test_rsi_overbought_zero():
    s = make_strategy()
    assert s.score_rsi(rsi=75.0) == 0


# --- MACD scoring ---

def test_macd_bullish_cross_positive_hist():
    s = make_strategy()
    assert s.score_macd(macd_line=0.5, signal_line=0.3, histogram=0.2) == 3


def test_macd_bullish_cross_negative_hist():
    s = make_strategy()
    assert s.score_macd(macd_line=0.5, signal_line=0.3, histogram=-0.1) == 1


def test_macd_bearish():
    s = make_strategy()
    assert s.score_macd(macd_line=-0.5, signal_line=0.3, histogram=-0.3) == 0


# --- BB position scoring ---

def test_bb_at_lower_band():
    s = make_strategy()
    # Price at exactly lower band
    assert s.score_bb_position(price=100.0, bb_lower=100.0, bb_upper=110.0) == 3


def test_bb_lower_half():
    s = make_strategy()
    # Price in lower third
    assert s.score_bb_position(price=102.0, bb_lower=100.0, bb_upper=110.0) == 2


def test_bb_neutral():
    s = make_strategy()
    # Price in middle
    assert s.score_bb_position(price=105.0, bb_lower=100.0, bb_upper=110.0) == 1


def test_bb_at_upper_band():
    s = make_strategy()
    # Price at upper band = overbought
    assert s.score_bb_position(price=110.0, bb_lower=100.0, bb_upper=110.0) == 0


# --- EMA trend scoring ---

def test_ema_uptrend_healthy():
    s = make_strategy()
    # Fast EMA slightly above slow = healthy uptrend
    assert s.score_ema_trend(ema_fast=101.0, ema_slow=100.0) == 3


def test_ema_uptrend_too_far_chased():
    s = make_strategy()
    # Fast EMA way above slow = chased
    assert s.score_ema_trend(ema_fast=105.0, ema_slow=100.0) == 0


def test_ema_just_crossed_below():
    s = make_strategy()
    # Fast just dipped below slow (within 1%) = possible reversal
    assert s.score_ema_trend(ema_fast=99.5, ema_slow=100.0) == 2


def test_ema_downtrend():
    s = make_strategy()
    # Fast clearly below slow = downtrend
    assert s.score_ema_trend(ema_fast=95.0, ema_slow=100.0) == 0


# --- Total score ---

def test_total_score_capped_at_10():
    s = make_strategy()
    score = s.total_score(
        rsi=25.0,
        macd_line=0.5, signal_line=0.3, histogram=0.2,
        price=100.0, bb_lower=100.0, bb_upper=110.0,
        ema_fast=101.0, ema_slow=100.0
    )
    assert score == 10


def test_total_score_bearish_setup():
    s = make_strategy()
    score = s.total_score(
        rsi=75.0,
        macd_line=-0.5, signal_line=0.3, histogram=-0.3,
        price=110.0, bb_lower=100.0, bb_upper=110.0,
        ema_fast=95.0, ema_slow=100.0
    )
    assert score == 0


# --- DataFrame pipeline ---

def test_get_score_from_df_uptrend():
    s = make_strategy()
    df = make_ohlcv(length=100, trend="up")
    score = s.get_score_from_df(df)
    assert 0 <= score <= 10


def test_get_score_from_df_too_short_returns_zero():
    s = make_strategy()
    df = make_ohlcv(length=30, trend="up")
    score = s.get_score_from_df(df)
    assert score == 0
