import pytest
from btc_lead import BtcLeadSignal


def make_signal():
    return BtcLeadSignal(client=None)


# --- BTC move scoring ---

def test_strong_organic_btc_move_max_score():
    s = make_signal()
    assert s.score_btc_move(btc_change_pct=2.5, spot_futures_ratio=0.65) == 15


def test_moderate_organic_btc_move():
    s = make_signal()
    assert s.score_btc_move(btc_change_pct=1.2, spot_futures_ratio=0.60) == 10


def test_futures_driven_move_ignored():
    s = make_signal()
    # Large move but futures-driven
    assert s.score_btc_move(btc_change_pct=2.5, spot_futures_ratio=0.25) == 0


def test_tiny_btc_move_ignored():
    s = make_signal()
    assert s.score_btc_move(btc_change_pct=0.1, spot_futures_ratio=0.70) == 0


def test_moderate_mixed_ratio():
    s = make_signal()
    # Moderate move, mixed spot/futures
    assert s.score_btc_move(btc_change_pct=1.5, spot_futures_ratio=0.40) == 5


def test_negative_btc_move_spot_driven():
    s = make_signal()
    # BTC falling hard but spot-driven (e.g., capitulation) — still scores
    assert s.score_btc_move(btc_change_pct=-2.5, spot_futures_ratio=0.65) == 15


# --- Alt correlation scoring ---

def test_alt_outperforming_btc():
    s = make_signal()
    # BTC +2%, alt +4% = 2x = outperforming
    assert s.score_alt_correlation(btc_change_pct=2.0, alt_change_pct=4.0) == 5


def test_alt_following_btc():
    s = make_signal()
    # BTC +2%, alt +1.2% = 60% follow = confirmed
    assert s.score_alt_correlation(btc_change_pct=2.0, alt_change_pct=1.2) == 3


def test_alt_lagging_btc():
    s = make_signal()
    # BTC +2%, alt +0.2% = 10% follow = lagging
    assert s.score_alt_correlation(btc_change_pct=2.0, alt_change_pct=0.2) == 1


def test_alt_diverging_from_btc():
    s = make_signal()
    # BTC +2%, alt -1% = diverging = suspicious
    assert s.score_alt_correlation(btc_change_pct=2.0, alt_change_pct=-1.0) == 0


def test_btc_flat_no_correlation_score():
    s = make_signal()
    # BTC barely moved — no correlation signal
    assert s.score_alt_correlation(btc_change_pct=0.1, alt_change_pct=2.0) == 0


# --- Total score ---

def test_total_score_max_is_20():
    s = make_signal()
    score = s.total_score(
        btc_change_pct=3.0,
        spot_futures_ratio=0.70,
        alt_change_pct=5.0
    )
    assert score == 20


def test_total_score_futures_driven_minimum():
    s = make_signal()
    score = s.total_score(
        btc_change_pct=3.0,
        spot_futures_ratio=0.20,
        alt_change_pct=5.0
    )
    assert score == 0
