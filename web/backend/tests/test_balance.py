import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _make_binance_mock(free="87.50", locked="0.00"):
    m = MagicMock()
    m.get_account.return_value = {
        "balances": [{"asset": "USDT", "free": free, "locked": locked}]
    }
    return m


def _get_client():
    from main import app
    return TestClient(app)


def test_get_balance_returns_usdt():
    client = _get_client()
    mock = _make_binance_mock("87.50", "5.00")
    with patch("routers.balance._get_binance", return_value=mock):
        resp = client.get("/api/balance", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["asset"] == "USDT"
    assert data["free"] == pytest.approx(87.50)
    assert data["locked"] == pytest.approx(5.00)


def test_get_balance_requires_api_key():
    client = _get_client()
    resp = client.get("/api/balance")
    assert resp.status_code == 401


def test_get_balance_wrong_key():
    client = _get_client()
    resp = client.get("/api/balance", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401


def test_health_endpoint_no_auth():
    from main import app
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
