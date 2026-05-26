import pytest
from scorer import ConvictionScorer, LayerScores, ConvictionResult


def make_scorer(weights=None):
    return ConvictionScorer(layer_weights=weights)


def full_layers() -> LayerScores:
    """Perfect signal across all layers."""
    return LayerScores(
        whale=25,
        macro=20,
        fiat_flow=15,
        btc_lead=20,
        ta=10,
        social=10
    )


def weak_layers() -> LayerScores:
    """Very weak signal — below threshold."""
    return LayerScores(
        whale=5,
        macro=5,
        fiat_flow=0,
        btc_lead=5,
        ta=2,
        social=0
    )


# --- Classification ---

def test_high_conviction_gives_buy_high():
    s = make_scorer()
    result = s.score(full_layers())
    assert result.action == "BUY"
    assert result.confidence == "HIGH"
    assert result.total_score == 100


def test_medium_conviction_gives_buy_medium():
    s = make_scorer()
    ls = LayerScores(whale=15, macro=10, fiat_flow=8, btc_lead=10, ta=6, social=6)
    result = s.score(ls)
    assert result.action == "BUY"
    assert result.confidence == "MEDIUM"
    assert result.total_score == 55


def test_borderline_watch():
    s = make_scorer()
    # 10+10+5+10+5+6 = 46 → WATCH (45-54 range)
    ls = LayerScores(whale=10, macro=10, fiat_flow=5, btc_lead=10, ta=5, social=6)
    result = s.score(ls)
    assert result.action == "WATCH"


def test_low_score_skip():
    s = make_scorer()
    result = s.score(weak_layers())
    assert result.action == "SKIP"
    assert not result.should_trade


# --- Layer weights ---

def test_weights_applied_correctly():
    # Double the whale weight
    s = make_scorer(weights={
        "whale": 2.0, "macro": 1.0, "fiat_flow": 1.0,
        "btc_lead": 1.0, "ta": 1.0, "social": 1.0
    })
    ls = LayerScores(whale=10, macro=0, fiat_flow=0, btc_lead=0, ta=0, social=0)
    result = s.score(ls)
    # whale=10 * 2.0 = 20
    assert result.total_score == 20


def test_weights_downgrade_weak_layer():
    # Reduce social weight to 0.5
    s = make_scorer(weights={
        "whale": 1.0, "macro": 1.0, "fiat_flow": 1.0,
        "btc_lead": 1.0, "ta": 1.0, "social": 0.5
    })
    ls = LayerScores(whale=0, macro=0, fiat_flow=0, btc_lead=0, ta=0, social=10)
    result = s.score(ls)
    # social=10 * 0.5 = 5
    assert result.total_score == 5


# --- Score clamping ---

def test_score_capped_at_100():
    s = make_scorer(weights={k: 2.0 for k in ["whale", "macro", "fiat_flow", "btc_lead", "ta", "social"]})
    result = s.score(full_layers())
    assert result.total_score == 100


def test_score_floored_at_zero():
    s = make_scorer()
    ls = LayerScores()  # all zeros
    result = s.score(ls)
    assert result.total_score == 0


# --- Reasons ---

def test_reasons_include_strong_layers():
    s = make_scorer()
    result = s.score(full_layers())
    assert any("STRONG" in r for r in result.reasons)


def test_reasons_include_layer_names():
    s = make_scorer()
    ls = LayerScores(whale=20, macro=0, fiat_flow=0, btc_lead=0, ta=0, social=0)
    result = s.score(ls)
    assert any("whale" in r for r in result.reasons)


# --- Convenience method ---

def test_score_from_dict():
    s = make_scorer()
    result = s.score_from_dict({
        "whale": 25, "macro": 20, "fiat_flow": 15,
        "btc_lead": 20, "ta": 10, "social": 10
    })
    assert result.total_score == 100
    assert result.action == "BUY"
