import pytest
from datetime import datetime
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _make_trade(id=1, pair="BTCUSDT", side="BUY", pnl=5.20):
    t = MagicMock()
    t.id = id
    t.pair = pair
    t.side = side
    t.market_type = "SPOT"
    t.price = 65000.0
    t.qty = 0.001
    t.usdt_value = 65.0
    t.pnl = pnl
    t.conviction_score = 72
    t.created_at = datetime(2025, 1, 1, 12, 0, 0)
    return t


def _get_client():
    from main import app
    return TestClient(app)


def _mock_session(trades):
    session = MagicMock()
    # chain: query().filter().order_by().limit().all()
    (session.query.return_value
           .filter.return_value
           .order_by.return_value
           .limit.return_value
           .all.return_value) = trades
    # also handle pair filter chained twice
    (session.query.return_value
           .filter.return_value
           .filter.return_value
           .order_by.return_value
           .limit.return_value
           .all.return_value) = trades
    return session


def test_get_trades_returns_list():
    client = _get_client()
    trades = [_make_trade(1, "BTCUSDT", "BUY", 5.20),
              _make_trade(2, "ETHUSDT", "BUY", -1.10)]
    session = _mock_session(trades)
    with patch("routers.trades.get_session", return_value=session):
        resp = client.get("/api/trades", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["pair"] == "BTCUSDT"
    assert data[0]["pnl"] == pytest.approx(5.20)
    assert data[0]["market_type"] == "SPOT"
    assert data[1]["pair"] == "ETHUSDT"


def test_get_trades_response_shape():
    client = _get_client()
    trade = _make_trade()
    session = _mock_session([trade])
    with patch("routers.trades.get_session", return_value=session):
        resp = client.get("/api/trades", headers=HEADERS)
    assert resp.status_code == 200
    item = resp.json()[0]
    for key in ("id", "pair", "side", "market_type", "price", "qty",
                "usdt_value", "pnl", "conviction_score", "created_at"):
        assert key in item, f"missing key: {key}"
    assert item["created_at"] == "2025-01-01T12:00:00"


def test_get_trades_empty_returns_list():
    client = _get_client()
    session = _mock_session([])
    with patch("routers.trades.get_session", return_value=session):
        resp = client.get("/api/trades", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_trades_requires_api_key():
    client = _get_client()
    resp = client.get("/api/trades")
    assert resp.status_code == 401


def test_get_trades_wrong_key():
    client = _get_client()
    resp = client.get("/api/trades", headers={"X-API-Key": "bad"})
    assert resp.status_code == 401
