import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _make_position(pair="BTCUSDT"):
    p = MagicMock()
    p.pair = pair
    p.side = "LONG"
    p.market_type = "SPOT"
    p.entry_price = 65000.0
    p.qty = 0.001
    p.usdt_value = 65.0
    p.stop_loss = 61750.0
    p.take_profit = 69550.0
    p.trailing_stop_active = False
    p.highest_price = 66000.0
    p.conviction_score = 72
    return p


def _get_client():
    from main import app
    return TestClient(app)


def _mock_session(positions):
    session = MagicMock()
    session.query.return_value.all.return_value = positions
    return session


def test_get_positions_returns_list():
    client = _get_client()
    positions = [_make_position("BTCUSDT"), _make_position("ETHUSDT")]
    session = _mock_session(positions)
    with patch("routers.positions.get_session", return_value=session):
        resp = client.get("/api/positions", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert data[0]["pair"] == "BTCUSDT"
    assert data[1]["pair"] == "ETHUSDT"


def test_get_positions_response_shape():
    client = _get_client()
    session = _mock_session([_make_position()])
    with patch("routers.positions.get_session", return_value=session):
        resp = client.get("/api/positions", headers=HEADERS)
    assert resp.status_code == 200
    item = resp.json()[0]
    for key in ("pair", "side", "market_type", "entry_price", "qty",
                "usdt_value", "stop_loss", "take_profit",
                "trailing_stop_active", "highest_price", "conviction_score"):
        assert key in item, f"missing key: {key}"
    assert item["entry_price"] == pytest.approx(65000.0)
    assert item["stop_loss"] == pytest.approx(61750.0)
    assert item["trailing_stop_active"] is False


def test_get_positions_empty():
    client = _get_client()
    session = _mock_session([])
    with patch("routers.positions.get_session", return_value=session):
        resp = client.get("/api/positions", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_positions_requires_api_key():
    client = _get_client()
    resp = client.get("/api/positions")
    assert resp.status_code == 401


def test_get_positions_wrong_key():
    client = _get_client()
    resp = client.get("/api/positions", headers={"X-API-Key": "bad"})
    assert resp.status_code == 401
