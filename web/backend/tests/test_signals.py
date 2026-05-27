import os
import pytest
from unittest.mock import patch, MagicMock
from datetime import datetime

os.environ.setdefault("WEB_API_KEY", "test-key")

from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _get_client():
    from main import app
    return TestClient(app)


def _mock_row(
    id: int,
    pair: str,
    total_score: int,
    layer_scores: str,
    action: str,
    created_at=None,
):
    row = MagicMock()
    row.id = id
    row.pair = pair
    row.total_score = total_score
    row.layer_scores = layer_scores
    row.action = action
    row.created_at = created_at or datetime(2026, 5, 27, 10, 0, 0)
    return row


# ── Basic contract ────────────────────────────────────────────────────────────

def test_signals_returns_five_pairs():
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        resp = client.get("/api/signals/latest", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    pairs = [d["pair"] for d in data]
    assert set(pairs) == {"BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"}


def test_signals_requires_api_key():
    client = _get_client()
    resp = client.get("/api/signals/latest")
    assert resp.status_code == 401


def test_signals_empty_scans_when_no_data():
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = []
        resp = client.get("/api/signals/latest", headers=HEADERS)

    assert resp.status_code == 200
    for coin in resp.json():
        assert coin["scans"] == []


# ── Layer score parsing ───────────────────────────────────────────────────────

def test_signals_parses_layer_scores():
    layers_json = '{"whale": 15, "macro": 18, "fiat_flow": 8, "btc_lead": 14, "ta": 8, "social": 6}'
    row = _mock_row(1, "BTCUSDT", 67, layers_json, "BUY")

    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    btc = next(d for d in data if d["pair"] == "BTCUSDT")
    assert len(btc["scans"]) == 1

    scan = btc["scans"][0]
    assert scan["total_score"] == 67
    assert scan["action"] == "BUY"
    assert scan["confidence"] == "MEDIUM"  # 55 <= 67 < 75

    whale = scan["layers"]["whale"]
    assert whale["score"] == 15
    assert whale["max"]   == 25
    assert whale["pct"]   == 60
    assert whale["strength"] == "MODERATE"  # 60% — between 40 and 70

    macro = scan["layers"]["macro"]
    assert macro["score"] == 18
    assert macro["strength"] == "STRONG"  # 18/20 = 90%


def test_signals_null_layer_scores_handled():
    """layer_scores = None should not crash — all layers become zero."""
    row = _mock_row(2, "ETHUSDT", 30, None, "SKIP")

    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)

    assert resp.status_code == 200
    eth = next(d for d in resp.json() if d["pair"] == "ETHUSDT")
    scan = eth["scans"][0]
    for layer_data in scan["layers"].values():
        assert layer_data["score"] == 0
        assert layer_data["strength"] == "NONE"


def test_signals_high_confidence():
    row = _mock_row(3, "BTCUSDT", 80, '{}', "BUY")
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    btc = next(d for d in resp.json() if d["pair"] == "BTCUSDT")
    assert btc["scans"][0]["confidence"] == "HIGH"


def test_signals_low_confidence():
    row = _mock_row(4, "BTCUSDT", 40, '{}', "SKIP")
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    btc = next(d for d in resp.json() if d["pair"] == "BTCUSDT")
    assert btc["scans"][0]["confidence"] == "LOW"


# ── Strength / confidence helpers ─────────────────────────────────────────────

def test_strength_strong():
    from routers.signals import _strength
    assert _strength(18, 20) == "STRONG"   # 90%
    assert _strength(14, 20) == "STRONG"   # 70% — exactly at threshold


def test_strength_moderate():
    from routers.signals import _strength
    assert _strength(10, 20) == "MODERATE"  # 50%
    assert _strength(8, 20)  == "MODERATE"  # 40% — exactly at threshold


def test_strength_weak():
    from routers.signals import _strength
    assert _strength(5, 20)  == "WEAK"   # 25%, score > 0
    assert _strength(1, 20)  == "WEAK"


def test_strength_none():
    from routers.signals import _strength
    assert _strength(0, 20) == "NONE"
    assert _strength(0, 0)  == "NONE"


def test_confidence_bands():
    from routers.signals import _confidence
    assert _confidence(80) == "HIGH"
    assert _confidence(75) == "HIGH"    # exactly at HIGH_CONVICTION
    assert _confidence(74) == "MEDIUM"
    assert _confidence(55) == "MEDIUM"  # exactly at MIN_CONVICTION
    assert _confidence(54) == "LOW"
    assert _confidence(0)  == "LOW"
