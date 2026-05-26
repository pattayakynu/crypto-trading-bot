import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock, call
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _make_perf(equity, recorded_at=None):
    p = MagicMock()
    p.equity = equity
    p.recorded_at = recorded_at or datetime(2025, 1, 1, 8, 0, 0)
    return p


def _make_trade(pnl):
    t = MagicMock()
    t.pnl = pnl
    return t


def _get_client():
    from main import app
    return TestClient(app)


def _mock_session(perf_rows, closed_trades):
    session = MagicMock()

    perf_query = MagicMock()
    perf_query.order_by.return_value.all.return_value = perf_rows

    trade_query = MagicMock()
    trade_query.filter.return_value.all.return_value = closed_trades

    session.query.side_effect = [perf_query, trade_query]
    return session


def test_get_performance_returns_stats():
    client = _get_client()
    perfs = [
        _make_perf(100.0, datetime(2025, 1, 1, 0, 0, 0)),
        _make_perf(108.0, datetime(2025, 1, 2, 0, 0, 0)),
    ]
    trades = [_make_trade(8.0), _make_trade(-2.0), _make_trade(3.5)]
    session = _mock_session(perfs, trades)
    with patch("routers.performance.get_session", return_value=session):
        resp = client.get("/api/performance", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_trades"] == 3
    assert data["total_pnl"] == pytest.approx(9.5)
    assert data["wins"] == 2
    assert data["losses"] == 1
    assert data["win_rate"] == pytest.approx(66.7)
    assert len(data["equity_curve"]) == 2
    assert data["equity_curve"][0]["equity"] == pytest.approx(100.0)


def test_get_performance_equity_curve_format():
    client = _get_client()
    perfs = [_make_perf(100.0, datetime(2025, 3, 15, 12, 0, 0))]
    session = _mock_session(perfs, [])
    with patch("routers.performance.get_session", return_value=session):
        resp = client.get("/api/performance", headers=HEADERS)
    assert resp.status_code == 200
    curve = resp.json()["equity_curve"]
    assert curve[0]["recorded_at"] == "2025-03-15T12:00:00"


def test_get_performance_no_data():
    client = _get_client()
    session = _mock_session([], [])
    with patch("routers.performance.get_session", return_value=session):
        resp = client.get("/api/performance", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_pnl"] == 0.0
    assert data["total_trades"] == 0
    assert data["wins"] == 0
    assert data["losses"] == 0
    assert data["win_rate"] == 0.0
    assert data["equity_curve"] == []


def test_get_performance_requires_api_key():
    client = _get_client()
    resp = client.get("/api/performance")
    assert resp.status_code == 401


def test_get_performance_wrong_key():
    client = _get_client()
    resp = client.get("/api/performance", headers={"X-API-Key": "bad"})
    assert resp.status_code == 401
