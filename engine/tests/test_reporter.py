import pytest
from reporter import MarketReporter


SAMPLE_DATA = {
    "btc_price": 65000,
    "btc_change_24h": 2.5,
    "eth_change_24h": -0.8,
    "total_market_cap_b": 2300,
    "btc_dominance": 54.3,
    "open_positions": 1,
    "total_pnl": 3.45,
    "equity": 103.45,
}


def make_reporter():
    return MarketReporter(claude_key=None, deepseek_key=None)


# ── Template section ──────────────────────────────────────────────────────────

def test_template_contains_btc_price():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "65,000" in text


def test_template_contains_positive_pnl():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "+$3.45" in text


def test_template_contains_negative_pnl():
    r = make_reporter()
    data = {**SAMPLE_DATA, "total_pnl": -2.10}
    text = r.build_template_section(data)
    assert "-$2.10" in text


def test_template_contains_equity():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "103.45" in text


def test_template_contains_timestamp():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "UTC" in text


def test_template_contains_open_positions():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "1" in text  # open_positions = 1


def test_template_positive_btc_change_formatted():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "+2.50%" in text


def test_template_negative_eth_change_formatted():
    r = make_reporter()
    text = r.build_template_section(SAMPLE_DATA)
    assert "-0.80%" in text


# ── Full report (no LLM) ──────────────────────────────────────────────────────

def test_report_without_llm_has_footer():
    r = make_reporter()
    report = r.build_report(SAMPLE_DATA, include_llm=False)
    assert "Trading Bot" in report


def test_report_without_llm_no_analysis_section():
    r = make_reporter()
    report = r.build_report(SAMPLE_DATA, include_llm=False)
    # No LLM keys → no analysis sections
    assert "Phân tích kỹ thuật" not in report
    assert "Nhận định vĩ mô" not in report


def test_report_is_string():
    r = make_reporter()
    report = r.build_report(SAMPLE_DATA, include_llm=False)
    assert isinstance(report, str)
    assert len(report) > 100


# ── Schedule check ────────────────────────────────────────────────────────────

def test_should_send_at_07():
    r = make_reporter()
    assert r.should_send_report(hour=7, minute=0) is True


def test_should_send_at_12():
    r = make_reporter()
    assert r.should_send_report(hour=12, minute=0) is True


def test_should_send_at_17():
    r = make_reporter()
    assert r.should_send_report(hour=17, minute=0) is True


def test_should_send_at_22():
    r = make_reporter()
    assert r.should_send_report(hour=22, minute=0) is True


def test_should_not_send_at_other_times():
    r = make_reporter()
    assert r.should_send_report(hour=9, minute=30) is False
    assert r.should_send_report(hour=15, minute=0) is False
    assert r.should_send_report(hour=7, minute=1) is False


# ── LLM fallback ─────────────────────────────────────────────────────────────

def test_deepseek_returns_empty_without_key():
    r = make_reporter()
    result = r.get_deepseek_analysis(SAMPLE_DATA)
    assert result == ""


def test_claude_returns_empty_without_key():
    r = make_reporter()
    result = r.get_claude_commentary(SAMPLE_DATA)
    assert result == ""
