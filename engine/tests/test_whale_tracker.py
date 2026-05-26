import pytest
from whale_tracker import WhaleTracker


def make_tracker():
    return WhaleTracker(client=None)


def test_exchange_outflow_high_gives_max_score():
    t = make_tracker()
    assert t.score_exchange_outflow(outflow_pct_24h=3.5) == 10


def test_exchange_outflow_medium_gives_partial():
    t = make_tracker()
    assert t.score_exchange_outflow(outflow_pct_24h=1.5) == 5


def test_exchange_outflow_low_gives_zero():
    t = make_tracker()
    assert t.score_exchange_outflow(outflow_pct_24h=0.1) == 0


def test_funding_bullish_divergence():
    t = make_tracker()
    # Funding âm + giá tăng = organic spot buying
    assert t.score_funding_rate(funding_rate=-0.0001, price_change_pct=0.5) == 10


def test_funding_neutral_partial_score():
    t = make_tracker()
    assert t.score_funding_rate(funding_rate=0.00005, price_change_pct=0.3) == 5


def test_funding_crowded_longs_zero():
    t = make_tracker()
    # Funding cao + giá tăng mạnh = quá nhiều longs = nguy hiểm
    assert t.score_funding_rate(funding_rate=0.0003, price_change_pct=2.0) == 0


def test_oi_decreasing_while_price_rises():
    t = make_tracker()
    assert t.score_open_interest(oi_change_pct=-2.0, price_change_pct=1.0) == 5


def test_oi_increasing_gives_zero():
    t = make_tracker()
    assert t.score_open_interest(oi_change_pct=2.0, price_change_pct=1.0) == 0


def test_total_score_capped_at_25():
    t = make_tracker()
    score = t.total_score(
        outflow_pct_24h=5.0,
        funding_rate=-0.0002,
        price_change_pct=0.8,
        oi_change_pct=-3.0
    )
    assert score <= 25
    assert score == 25
