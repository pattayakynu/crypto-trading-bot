import os
from unittest.mock import patch
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _get_client():
    from main import app
    return TestClient(app)


def test_config_status_returns_all_keys():
    client = _get_client()
    resp = client.get("/api/config/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    for key in ("BINANCE_API_KEY", "BINANCE_SECRET_KEY", "CLAUDE_API_KEY",
                "DEEPSEEK_API_KEY", "TELEGRAM_BOT_TOKEN",
                "TELEGRAM_ALLOWED_USER_IDS", "WEB_API_KEY", "REDIS_URL"):
        assert key in data, f"missing key: {key}"


def test_config_status_true_when_key_is_set():
    client = _get_client()
    env = {
        "BINANCE_API_KEY": "real_key_abc123",
        "BINANCE_SECRET_KEY": "real_secret_xyz",
        "CLAUDE_API_KEY": "sk-ant-real",
        "DEEPSEEK_API_KEY": "sk-deep-real",
        "TELEGRAM_BOT_TOKEN": "123:ABC",
        "TELEGRAM_ALLOWED_USER_IDS": "123456",
        "WEB_API_KEY": "my-strong-secret",
        "REDIS_URL": "redis://redis:6379",
    }
    with patch.dict(os.environ, env, clear=False):
        resp = client.get("/api/config/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["BINANCE_API_KEY"] is True
    assert data["CLAUDE_API_KEY"] is True
    assert data["TELEGRAM_BOT_TOKEN"] is True
    assert data["WEB_API_KEY"] is True


def test_config_status_false_when_key_is_empty():
    client = _get_client()
    with patch.dict(os.environ, {"CLAUDE_API_KEY": "", "DEEPSEEK_API_KEY": ""}, clear=False):
        resp = client.get("/api/config/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["CLAUDE_API_KEY"] is False
    assert data["DEEPSEEK_API_KEY"] is False


def test_config_status_false_when_placeholder_value():
    client = _get_client()
    placeholders = {
        "WEB_API_KEY": "change-me-secret",
        "BINANCE_API_KEY": "your_binance_api_key_here",
        "CLAUDE_API_KEY": "your_anthropic_api_key_here",
        "TELEGRAM_BOT_TOKEN": "your_telegram_bot_token_here",
    }
    with patch.dict(os.environ, placeholders, clear=False):
        resp = client.get("/api/config/status", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert data["WEB_API_KEY"] is False
    assert data["BINANCE_API_KEY"] is False
    assert data["CLAUDE_API_KEY"] is False
    assert data["TELEGRAM_BOT_TOKEN"] is False


def test_config_status_requires_api_key():
    client = _get_client()
    resp = client.get("/api/config/status")
    assert resp.status_code == 401


def test_config_status_wrong_key():
    client = _get_client()
    resp = client.get("/api/config/status", headers={"X-API-Key": "wrong"})
    assert resp.status_code == 401
