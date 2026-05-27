import pytest
from llm_advisor import LlmAdvisor


def make_advisor():
    return LlmAdvisor(claude_key=None, deepseek_key=None)


SAMPLE_CONTEXT = dict(
    symbol="ETHUSDT",
    conviction_score=72,
    layer_scores={"whale": 20, "macro": 15, "fiat_flow": 10, "btc_lead": 15, "ta": 8, "social": 4},
    price_change_pct=1.8,
    reasons=["whale: STRONG (20/25)", "macro: STRONG (15/20)"],
)

BUY_RESPONSE = {"signal": "BUY", "confidence": "HIGH", "key_reason": "Strong whale signal", "risk_flag": None}
SKIP_RESPONSE = {"signal": "SKIP", "confidence": "LOW", "key_reason": "Macro risk", "risk_flag": "DXY rising"}


# --- Disagreement Protocol ---

def test_both_buy_gives_buy():
    a = make_advisor()
    result = a.analyze_with_mock(**SAMPLE_CONTEXT, mock_claude=BUY_RESPONSE, mock_deepseek=BUY_RESPONSE)
    assert result["final_signal"] == "BUY"
    assert result["agreement"] is True
    assert result["disagreement_skipped"] is False


def test_both_skip_gives_skip():
    a = make_advisor()
    result = a.analyze_with_mock(**SAMPLE_CONTEXT, mock_claude=SKIP_RESPONSE, mock_deepseek=SKIP_RESPONSE)
    assert result["final_signal"] == "SKIP"
    assert result["agreement"] is True


def test_disagreement_skips_trade():
    a = make_advisor()
    result = a.analyze_with_mock(**SAMPLE_CONTEXT, mock_claude=BUY_RESPONSE, mock_deepseek=SKIP_RESPONSE)
    assert result["final_signal"] == "SKIP"
    assert result["agreement"] is False
    assert result["disagreement_skipped"] is True


def test_disagreement_reversed():
    a = make_advisor()
    result = a.analyze_with_mock(**SAMPLE_CONTEXT, mock_claude=SKIP_RESPONSE, mock_deepseek=BUY_RESPONSE)
    assert result["final_signal"] == "SKIP"
    assert result["disagreement_skipped"] is True


# --- Signal parsing ---

def test_buy_case_insensitive():
    a = make_advisor()
    assert a._parse_signal({"signal": "buy"}) == "BUY"
    assert a._parse_signal({"signal": "Buy"}) == "BUY"


def test_skip_fallback_for_unknown():
    a = make_advisor()
    assert a._parse_signal({"signal": "HOLD"}) == "SKIP"
    assert a._parse_signal({}) == "SKIP"


# --- No API key fallback ---

def test_no_claude_key_returns_skip():
    a = LlmAdvisor(claude_key=None, deepseek_key=None)
    result = a.analyze(**SAMPLE_CONTEXT)
    # Both fail gracefully → both return SKIP → agree on SKIP
    assert result["final_signal"] == "SKIP"
    assert result["agreement"] is True


# --- Response structure ---

def test_result_has_all_keys():
    a = make_advisor()
    result = a.analyze_with_mock(**SAMPLE_CONTEXT, mock_claude=BUY_RESPONSE, mock_deepseek=BUY_RESPONSE)
    assert "final_signal" in result
    assert "agreement" in result
    assert "disagreement_skipped" in result
    assert "claude" in result
    assert "deepseek" in result


# ── SHORT dual-LLM tests ──────────────────────────────────────────────────────

SHORT_RESPONSE = {
    "signal": "SHORT",
    "confidence": "HIGH",
    "key_reason": "Funding reset + alt weakness",
    "risk_flag": None,
}

SHORT_CONTEXT = dict(
    symbol="ETHUSDT",
    short_score=75,
    signal_scores={
        "alt_weakness": 25,
        "funding_reset": 25,
        "volume_exhaustion": 15,
        "macro_bearish": 10,
    },
    regime="BEAR",
    reasons=["alt_weakness=25", "funding_reset=25"],
)


def test_short_both_short_gives_short():
    a = make_advisor()
    result = a.analyze_short_with_mock(
        **SHORT_CONTEXT, mock_claude=SHORT_RESPONSE, mock_deepseek=SHORT_RESPONSE
    )
    assert result["final_signal"] == "SHORT"
    assert result["agreement"] is True
    assert result["disagreement_skipped"] is False


def test_short_disagreement_gives_skip():
    a = make_advisor()
    result = a.analyze_short_with_mock(
        **SHORT_CONTEXT, mock_claude=SHORT_RESPONSE, mock_deepseek=SKIP_RESPONSE
    )
    assert result["final_signal"] == "SKIP"
    assert result["disagreement_skipped"] is True


def test_parse_short_signal():
    a = make_advisor()
    assert a._parse_short_signal({"signal": "SHORT"}) == "SHORT"
    assert a._parse_short_signal({"signal": "short"}) == "SHORT"
    assert a._parse_short_signal({"signal": "SKIP"}) == "SKIP"
    assert a._parse_short_signal({}) == "SKIP"


def test_short_result_has_all_keys():
    a = make_advisor()
    result = a.analyze_short_with_mock(
        **SHORT_CONTEXT, mock_claude=SHORT_RESPONSE, mock_deepseek=SHORT_RESPONSE
    )
    assert "final_signal" in result
    assert "agreement" in result
    assert "disagreement_skipped" in result
    assert "claude" in result
    assert "deepseek" in result
