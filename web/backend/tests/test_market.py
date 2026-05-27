import os
import pytest
from unittest.mock import patch, MagicMock

# Set env var BEFORE main is imported (main.py reads WEB_API_KEY at import time)
os.environ.setdefault("WEB_API_KEY", "test-key")

from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _get_client():
    # Reset module-level caches before each test
    import routers.market as m
    m._price_cache["ts"] = 0.0
    m._price_cache["data"] = None
    from main import app
    return TestClient(app)


def _binance_ticker_response():
    return [
        {"symbol": "BTCUSDT", "lastPrice": "67420.00", "priceChangePercent": "1.24"},
        {"symbol": "ETHUSDT", "lastPrice": "3210.00",  "priceChangePercent": "-0.87"},
        {"symbol": "BNBUSDT", "lastPrice": "598.00",   "priceChangePercent": "0.51"},
        {"symbol": "SOLUSDT", "lastPrice": "178.00",   "priceChangePercent": "-2.14"},
        {"symbol": "ADAUSDT", "lastPrice": "0.452",    "priceChangePercent": "3.20"},
    ]


def test_prices_returns_five_coins():
    client = _get_client()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = _binance_ticker_response()
    mock_resp.raise_for_status = lambda: None
    with patch("routers.market.httpx.get", return_value=mock_resp):
        resp = client.get("/api/market/prices", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert data[0]["symbol"] == "BTC"
    assert data[0]["price"] == pytest.approx(67420.0)
    assert data[0]["change_pct_24h"] == pytest.approx(1.24)


def test_prices_requires_api_key():
    client = _get_client()
    resp = client.get("/api/market/prices")
    assert resp.status_code == 401


def test_prices_uses_cache_within_ttl():
    import routers.market as m
    import time
    client = _get_client()
    cached = [{"symbol": "BTC", "price": 99999.0, "change_pct_24h": 5.0}]
    m._price_cache["data"] = cached
    m._price_cache["ts"] = time.time()  # just set, within TTL
    with patch("routers.market.httpx.get") as mock_get:
        resp = client.get("/api/market/prices", headers=HEADERS)
        mock_get.assert_not_called()
    assert resp.json() == cached


def test_prices_returns_stale_cache_on_binance_error():
    import routers.market as m
    client = _get_client()
    stale = [{"symbol": "BTC", "price": 65000.0, "change_pct_24h": 0.5}]
    m._price_cache["data"] = stale
    m._price_cache["ts"] = 0.0  # expired
    with patch("routers.market.httpx.get", side_effect=Exception("timeout")):
        resp = client.get("/api/market/prices", headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json() == stale


def test_prices_returns_null_prices_when_no_cache_and_binance_error():
    client = _get_client()
    with patch("routers.market.httpx.get", side_effect=Exception("timeout")):
        resp = client.get("/api/market/prices", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 5
    assert all(item["price"] is None for item in data)


# ── /news tests ───────────────────────────────────────────────────────────────

def _reset_news_cache():
    import routers.market as m
    m._news_cache["ts"] = 0.0
    m._news_cache["data"] = None


def test_news_returns_list():
    _reset_news_cache()
    client = _get_client()

    mock_cp = MagicMock()
    mock_cp.status_code = 200
    mock_cp.json.return_value = {
        "results": [
            {
                "title": "Bitcoin ETF inflows hit record",
                "url": "https://example.com/1",
                "source": {"title": "CoinDesk"},
                "published_at": "2026-05-27T10:00:00Z",
            }
        ]
    }

    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(
            title="Fed holds rates steady",
            link="https://example.com/2",
            published="Tue, 27 May 2026 09:00:00 +0000",
        )
    ]
    mock_feed.entries[0].get = lambda key, default="": {
        "title": "Fed holds rates steady",
        "link": "https://example.com/2",
        "published": "Tue, 27 May 2026 09:00:00 +0000",
    }.get(key, default)

    with patch.dict(os.environ, {"CRYPTOPANIC_API_KEY": "test-cp-key"}), \
         patch("routers.market.httpx.get", return_value=mock_cp), \
         patch("routers.market.feedparser.parse", return_value=mock_feed):
        resp = client.get("/api/market/news", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert any(item["category"] == "crypto" for item in data)
    assert any(item["category"] == "macro" for item in data)


def test_news_importance_high_for_etf_keyword():
    import routers.market as m
    assert m._importance("Bitcoin ETF approved by SEC") == "high"
    assert m._importance("crypto market update") == "normal"
    assert m._importance("Fed FOMC meeting minutes") == "high"
    assert m._importance("BTC hits new high") == "high"


def test_news_uses_cache():
    import routers.market as m
    import time
    m._news_cache["data"] = [{"title": "cached", "url": "", "source": "", "published_at": "", "category": "crypto", "importance": "normal"}]
    m._news_cache["ts"] = time.time()
    client = _get_client()
    with patch("routers.market.httpx.get") as mock_get, \
         patch("routers.market.feedparser.parse") as mock_parse:
        resp = client.get("/api/market/news", headers=HEADERS)
        mock_get.assert_not_called()
        mock_parse.assert_not_called()
    assert resp.json()[0]["title"] == "cached"


def test_news_survives_cryptopanic_failure():
    _reset_news_cache()
    client = _get_client()

    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(
            title="Market recap",
            link="https://example.com/3",
            published="Tue, 27 May 2026 08:00:00 +0000",
        )
    ]
    mock_feed.entries[0].get = lambda key, default="": {
        "title": "Market recap",
        "link": "https://example.com/3",
        "published": "Tue, 27 May 2026 08:00:00 +0000",
    }.get(key, default)

    with patch.dict(os.environ, {"CRYPTOPANIC_API_KEY": "key"}), \
         patch("routers.market.httpx.get", side_effect=Exception("CP down")), \
         patch("routers.market.feedparser.parse", return_value=mock_feed):
        resp = client.get("/api/market/news", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["source"] == "Yahoo Finance"
