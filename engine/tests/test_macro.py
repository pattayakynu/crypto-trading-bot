import pytest
from macro import MacroContext


def make_macro():
    return MacroContext()


# --- DXY scoring ---

def test_dxy_weak_dollar_gives_max():
    m = make_macro()
    assert m.score_dxy(dxy_change_pct=-0.5) == 10


def test_dxy_neutral_gives_partial():
    m = make_macro()
    assert m.score_dxy(dxy_change_pct=0.2) == 5


def test_dxy_strong_dollar_gives_zero():
    m = make_macro()
    assert m.score_dxy(dxy_change_pct=0.8) == 0


def test_dxy_exactly_at_bullish_threshold():
    m = make_macro()
    # -0.3% exactly = on the threshold → bullish
    assert m.score_dxy(dxy_change_pct=-0.3) == 10


def test_dxy_exactly_at_bearish_threshold():
    m = make_macro()
    # 0.5% exactly = on the threshold → bearish
    assert m.score_dxy(dxy_change_pct=0.5) == 0


# --- Gold scoring ---

def test_gold_and_crypto_both_rising_max_score():
    m = make_macro()
    # Both rising = true risk-on
    assert m.score_gold(gold_change_pct=0.8, crypto_change_pct=1.5) == 10


def test_gold_rising_crypto_falling_zero():
    m = make_macro()
    # Gold up, crypto down = flight to safety = bad
    assert m.score_gold(gold_change_pct=0.7, crypto_change_pct=-0.5) == 0


def test_gold_falling_crypto_rising_neutral():
    m = make_macro()
    # Gold down, crypto up = crypto-specific = neutral
    assert m.score_gold(gold_change_pct=-0.8, crypto_change_pct=1.0) == 5


def test_gold_flat_neutral():
    m = make_macro()
    assert m.score_gold(gold_change_pct=0.1, crypto_change_pct=0.5) == 5


# --- Total score ---

def test_total_score_max_is_20():
    m = make_macro()
    score = m.total_score(dxy_change_pct=-1.0, gold_change_pct=1.0, crypto_change_pct=2.0)
    assert score == 20


def test_total_score_bearish_macro():
    m = make_macro()
    score = m.total_score(dxy_change_pct=1.0, gold_change_pct=0.8, crypto_change_pct=-0.5)
    assert score == 0   # DXY strong=0 + gold up crypto down=0


def test_total_score_neutral_macro():
    m = make_macro()
    score = m.total_score(dxy_change_pct=0.2, gold_change_pct=0.1, crypto_change_pct=0.5)
    assert score == 10  # DXY neutral=5 + gold flat=5
