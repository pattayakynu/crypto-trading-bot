import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _get_client():
    from main import app
    return TestClient(app)


def _make_redis(running_value=None):
    r = MagicMock()
    r.get.return_value = running_value
    return r


def test_bot_status_running():
    client = _get_client()
    redis_mock = _make_redis(b"running")
    with patch("routers.bot.get_redis", return_value=redis_mock):
        resp = client.get("/api/bot/status", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_bot_status_stopped():
    client = _get_client()
    redis_mock = _make_redis(None)
    with patch("routers.bot.get_redis", return_value=redis_mock):
        resp = client.get("/api/bot/status", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_bot_status_stopped_when_other_value():
    client = _get_client()
    redis_mock = _make_redis(b"stopped")
    with patch("routers.bot.get_redis", return_value=redis_mock):
        resp = client.get("/api/bot/status", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "stopped"


def test_bot_start_sends_command():
    client = _get_client()
    redis_mock = _make_redis()
    with patch("routers.bot.get_redis", return_value=redis_mock):
        resp = client.post("/api/bot/start", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["action"] == "start"
    redis_mock.set.assert_called_once_with("bot:control", "start")


def test_bot_stop_sends_command():
    client = _get_client()
    redis_mock = _make_redis()
    with patch("routers.bot.get_redis", return_value=redis_mock):
        resp = client.post("/api/bot/stop", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["action"] == "stop"
    redis_mock.set.assert_called_once_with("bot:control", "stop")


def test_bot_status_requires_api_key():
    client = _get_client()
    resp = client.get("/api/bot/status")
    assert resp.status_code == 401


def test_bot_start_requires_api_key():
    client = _get_client()
    resp = client.post("/api/bot/start")
    assert resp.status_code == 401


def test_bot_stop_requires_api_key():
    client = _get_client()
    resp = client.post("/api/bot/stop")
    assert resp.status_code == 401
