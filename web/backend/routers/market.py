import os
import time
import httpx
import feedparser
from fastapi import APIRouter

router = APIRouter()

WATCHLIST = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
PRICE_CACHE_TTL = 30    # seconds
NEWS_CACHE_TTL  = 300   # seconds


def _build_proxy() -> str | None:
    """Return BINANCE_PROXY as a proxy URL string for httpx."""
    raw = os.getenv("BINANCE_PROXY", "").strip()
    if not raw:
        return None
    # Already a full URL (http://user:pass@host:port)
    if raw.startswith("http"):
        return raw
    # Legacy format: host:port:user:pass
    parts = raw.split(":")
    if len(parts) == 4:
        host, port, user, password = parts
        return f"http://{user}:{password}@{host}:{port}"
    return None

_price_cache: dict = {"data": None, "ts": 0.0}
_news_cache:  dict = {"data": None, "ts": 0.0}

HIGH_IMPORTANCE_KEYWORDS = {"fed", "fomc", "sec", "etf", "btc", "crash", "ban", "hack"}


def _importance(title: str) -> str:
    lower = title.lower()
    return "high" if any(kw in lower for kw in HIGH_IMPORTANCE_KEYWORDS) else "normal"


@router.get("/market/prices")
def get_market_prices():
    """Return price + 24h % for the 5-coin watchlist. Cached 30s."""
    global _price_cache
    now = time.time()
    if _price_cache["data"] and now - _price_cache["ts"] < PRICE_CACHE_TTL:
        return _price_cache["data"]

    try:
        symbols_json = '["' + '","'.join(WATCHLIST) + '"]'
        resp = httpx.get(
            "https://api.binance.com/api/v3/ticker/24hr",
            params={"symbols": symbols_json},
            timeout=8,
            proxy=_build_proxy(),
        )
        resp.raise_for_status()
        tickers = {t["symbol"]: t for t in resp.json()}
        result = [
            {
                "symbol": sym.replace("USDT", ""),
                "price": float(tickers[sym]["lastPrice"]) if sym in tickers else None,
                "change_pct_24h": float(tickers[sym]["priceChangePercent"]) if sym in tickers else None,
            }
            for sym in WATCHLIST
        ]
        _price_cache = {"data": result, "ts": now}
        return result
    except Exception:
        if _price_cache["data"]:
            return _price_cache["data"]
        return [{"symbol": s.replace("USDT", ""), "price": None, "change_pct_24h": None} for s in WATCHLIST]


@router.get("/market/news")
def get_market_news():
    """Return crypto (CryptoPanic) + macro (Yahoo Finance RSS) news. Cached 5 min."""
    global _news_cache
    now = time.time()
    if _news_cache["data"] and now - _news_cache["ts"] < NEWS_CACHE_TTL:
        return _news_cache["data"]

    items = []

    # ── CryptoPanic (optional — cần API key) ──────────────────────────────────
    cp_key = os.getenv("CRYPTOPANIC_API_KEY", "")
    if cp_key:
        try:
            resp = httpx.get(
                "https://cryptopanic.com/api/v1/posts/",
                params={"auth_token": cp_key, "public": "true", "kind": "news"},
                timeout=8,
            )
            if resp.status_code == 200:
                for post in resp.json().get("results", [])[:10]:
                    title = post.get("title", "")
                    items.append({
                        "title": title,
                        "url": post.get("url", ""),
                        "source": post.get("source", {}).get("title", "CryptoPanic"),
                        "published_at": post.get("published_at", ""),
                        "category": "crypto",
                        "importance": _importance(title),
                    })
        except Exception:
            pass

    # ── CoinDesk RSS (crypto, miễn phí) ──────────────────────────────────────
    try:
        feed = feedparser.parse("https://www.coindesk.com/arc/outboundfeeds/rss/")
        for entry in feed.entries[:8]:
            title = entry.get("title", "")
            items.append({
                "title": title,
                "url": entry.get("link", ""),
                "source": "CoinDesk",
                "published_at": entry.get("published", ""),
                "category": "crypto",
                "importance": _importance(title),
            })
    except Exception:
        pass

    # ── Cointelegraph RSS (crypto, miễn phí) ─────────────────────────────────
    try:
        feed = feedparser.parse("https://cointelegraph.com/rss")
        for entry in feed.entries[:8]:
            title = entry.get("title", "")
            items.append({
                "title": title,
                "url": entry.get("link", ""),
                "source": "Cointelegraph",
                "published_at": entry.get("published", ""),
                "category": "crypto",
                "importance": _importance(title),
            })
    except Exception:
        pass

    # ── Yahoo Finance RSS (macro) ─────────────────────────────────────────────
    try:
        feed = feedparser.parse(
            "https://feeds.finance.yahoo.com/rss/2.0/headline"
            "?s=%5EGSPC,%5EDJI&region=US&lang=en-US"
        )
        for entry in feed.entries[:10]:
            title = entry.get("title", "")
            items.append({
                "title": title,
                "url": entry.get("link", ""),
                "source": "Yahoo Finance",
                "published_at": entry.get("published", ""),
                "category": "macro",
                "importance": _importance(title),
            })
    except Exception:
        pass

    items.sort(key=lambda x: x.get("published_at", ""), reverse=True)
    result = items[:20]
    _news_cache = {"data": result, "ts": now}
    return result
