# Market Data Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Thêm PriceTickerBar (giá 5 coin real-time) và NewsFeed (CryptoPanic + Yahoo Finance RSS) vào dashboard.

**Architecture:** FastAPI backend proxy với 2 endpoint mới (`/api/market/prices`, `/api/market/news`) cache in-memory. Frontend dùng SWR hooks poll mỗi 10s (giá) / 5 phút (news). Layout Option B: ticker full-width trên đầu, news cạnh EquityChart (1/3).

**Tech Stack:** Python `httpx` + `feedparser` (backend); React SWR + Tailwind (frontend); Binance REST API; CryptoPanic API; Yahoo Finance RSS.

---

## File Map

| File | Action |
|------|--------|
| `web/backend/requirements.txt` | Sửa — thêm `feedparser==6.0.11` |
| `web/backend/routers/market.py` | Tạo mới — `/prices` + `/news` + cache + helpers |
| `web/backend/tests/test_market.py` | Tạo mới — tests cho cả 2 endpoint |
| `web/backend/main.py` | Sửa — register market router |
| `docker-compose.yml` | Sửa — thêm `CRYPTOPANIC_API_KEY` cho web-backend |
| `web/frontend/lib/hooks.ts` | Sửa — thêm `useMarketPrices`, `useMarketNews`, types |
| `web/frontend/components/PriceTickerBar.tsx` | Tạo mới |
| `web/frontend/components/NewsFeed.tsx` | Tạo mới |
| `web/frontend/app/page.tsx` | Sửa — thêm 2 component, update layout |
| `web/frontend/__tests__/components.test.tsx` | Sửa — thêm tests cho 2 component mới |

---

## Task 1: Backend — `/api/market/prices` endpoint

**Files:**
- Create: `web/backend/routers/market.py`
- Modify: `web/backend/requirements.txt`
- Test: `web/backend/tests/test_market.py`

- [ ] **Step 1: Thêm feedparser vào requirements.txt**

Mở `web/backend/requirements.txt`, thêm dòng cuối:
```
feedparser==6.0.11
```

- [ ] **Step 2: Viết failing test cho /prices**

Tạo file `web/backend/tests/test_market.py`:

```python
import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

HEADERS = {"X-API-Key": "test-key"}


def _get_client():
    # Reset module-level caches trước mỗi test
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
```

- [ ] **Step 3: Chạy test để xác nhận FAIL**

```bash
cd web/backend
pytest tests/test_market.py -v
```

Expected: `ImportError` hoặc `404` vì `market.py` chưa tồn tại.

- [ ] **Step 4: Tạo `web/backend/routers/market.py` với `/prices`**

```python
import os
import time
import httpx
from fastapi import APIRouter

router = APIRouter()

WATCHLIST = ["BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT"]
PRICE_CACHE_TTL = 30   # giây
NEWS_CACHE_TTL  = 300  # giây

_price_cache: dict = {"data": None, "ts": 0.0}
_news_cache:  dict = {"data": None, "ts": 0.0}

HIGH_IMPORTANCE_KEYWORDS = {"fed", "fomc", "sec", "etf", "btc", "crash", "ban", "hack"}


def _importance(title: str) -> str:
    lower = title.lower()
    return "high" if any(kw in lower for kw in HIGH_IMPORTANCE_KEYWORDS) else "normal"


@router.get("/market/prices")
def get_market_prices():
    """Trả về giá + % 24h cho 5 coin watchlist. Cache 30s."""
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
```

- [ ] **Step 5: Chạy test /prices — phải PASS**

```bash
cd web/backend
pytest tests/test_market.py::test_prices_returns_five_coins \
       tests/test_market.py::test_prices_requires_api_key \
       tests/test_market.py::test_prices_uses_cache_within_ttl \
       tests/test_market.py::test_prices_returns_stale_cache_on_binance_error \
       tests/test_market.py::test_prices_returns_null_prices_when_no_cache_and_binance_error \
       -v
```

Expected: 5 PASSED.

- [ ] **Step 6: Commit**

```bash
git add web/backend/requirements.txt web/backend/routers/market.py web/backend/tests/test_market.py
git commit -m "feat(backend): add /api/market/prices endpoint with 30s cache"
```

---

## Task 2: Backend — `/api/market/news` endpoint

**Files:**
- Modify: `web/backend/routers/market.py` (thêm `/news` endpoint)
- Modify: `web/backend/tests/test_market.py` (thêm tests)

- [ ] **Step 1: Thêm failing tests cho /news vào `web/backend/tests/test_market.py`**

Append vào cuối file `web/backend/tests/test_market.py`:

```python
def test_news_returns_list():
    import routers.market as m
    m._news_cache["ts"] = 0.0
    m._news_cache["data"] = None
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

    import feedparser as _fp
    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(
            title="Fed holds rates steady",
            link="https://example.com/2",
            published="Tue, 27 May 2026 09:00:00 +0000",
        )
    ]

    with patch.dict(os.environ, {"CRYPTOPANIC_API_KEY": "test-cp-key"}), \
         patch("routers.market.httpx.get", return_value=mock_cp), \
         patch("routers.market.feedparser.parse", return_value=mock_feed):
        resp = client.get("/api/market/news", headers=HEADERS)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    # CryptoPanic item
    assert any(item["category"] == "crypto" for item in data)
    # Macro item
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
    import routers.market as m
    m._news_cache["ts"] = 0.0
    m._news_cache["data"] = None
    client = _get_client()

    mock_feed = MagicMock()
    mock_feed.entries = [
        MagicMock(
            title="Market recap",
            link="https://example.com/3",
            published="Tue, 27 May 2026 08:00:00 +0000",
        )
    ]
    with patch.dict(os.environ, {"CRYPTOPANIC_API_KEY": "key"}), \
         patch("routers.market.httpx.get", side_effect=Exception("CP down")), \
         patch("routers.market.feedparser.parse", return_value=mock_feed):
        resp = client.get("/api/market/news", headers=HEADERS)
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) >= 1
    assert data[0]["source"] == "Yahoo Finance"
```

- [ ] **Step 2: Chạy failing tests**

```bash
cd web/backend
pytest tests/test_market.py::test_news_returns_list -v
```

Expected: `FAILED` — `AttributeError: module 'routers.market' has no attribute` `/news` endpoint.

- [ ] **Step 3: Thêm `/news` endpoint vào `web/backend/routers/market.py`**

Append vào cuối file (sau phần `_importance`):

```python
@router.get("/market/news")
def get_market_news():
    """Trả về tin tức crypto (CryptoPanic) + macro (Yahoo RSS). Cache 5 phút."""
    global _news_cache
    now = time.time()
    if _news_cache["data"] and now - _news_cache["ts"] < NEWS_CACHE_TTL:
        return _news_cache["data"]

    import feedparser
    items = []

    # ── CryptoPanic ───────────────────────────────────────────────────────────
    cp_key = os.getenv("CRYPTOPANIC_API_KEY", "")
    if cp_key:
        try:
            resp = httpx.get(
                "https://cryptopanic.com/api/v1/posts/",
                params={"auth_token": cp_key, "public": "true", "kind": "news"},
                timeout=8,
            )
            if resp.status_code == 200:
                for post in resp.json().get("results", [])[:15]:
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
```

- [ ] **Step 4: Chạy tất cả tests /news — phải PASS**

```bash
cd web/backend
pytest tests/test_market.py -v
```

Expected: tất cả PASSED (9 tests tổng).

- [ ] **Step 5: Commit**

```bash
git add web/backend/routers/market.py web/backend/tests/test_market.py
git commit -m "feat(backend): add /api/market/news endpoint (CryptoPanic + Yahoo RSS, 5min cache)"
```

---

## Task 3: Register router + env var

**Files:**
- Modify: `web/backend/main.py`
- Modify: `docker-compose.yml`

- [ ] **Step 1: Register market router trong `web/backend/main.py`**

Tìm dòng:
```python
from routers import balance, trades, positions, performance, config as config_router
from routers import bot as bot_router
```

Thay bằng:
```python
from routers import balance, trades, positions, performance, config as config_router
from routers import bot as bot_router
from routers import market as market_router
```

Tìm dòng cuối cùng của phần `include_router`:
```python
app.include_router(config_router.router, prefix="/api", **_protected)
```

Thêm sau đó:
```python
app.include_router(market_router.router, prefix="/api", **_protected)
```

- [ ] **Step 2: Kiểm tra /health và /prices route đã register**

```bash
cd web/backend
python -c "from main import app; routes = [r.path for r in app.routes]; print([r for r in routes if 'market' in r])"
```

Expected output: `['/api/market/prices', '/api/market/news']`

- [ ] **Step 3: Thêm `CRYPTOPANIC_API_KEY` vào `docker-compose.yml`**

Trong service `web-backend`, tìm block `environment:` và thêm:
```yaml
      CRYPTOPANIC_API_KEY: ${CRYPTOPANIC_API_KEY:-}
```

- [ ] **Step 4: Thêm `CRYPTOPANIC_API_KEY` vào `.env` trên server**

(Lệnh chạy trên server — không commit key vào git)
```bash
# Nếu engine đang dùng key này, lấy từ .env engine:
grep CRYPTOPANIC .env
# Nếu chưa có, thêm:
echo "CRYPTOPANIC_API_KEY=your_key_here" >> .env
```

- [ ] **Step 5: Commit**

```bash
git add web/backend/main.py docker-compose.yml
git commit -m "feat(backend): register market router, add CRYPTOPANIC_API_KEY to compose"
```

---

## Task 4: Frontend hooks

**Files:**
- Modify: `web/frontend/lib/hooks.ts`

- [ ] **Step 1: Thêm types và hooks vào `web/frontend/lib/hooks.ts`**

Append vào cuối file `web/frontend/lib/hooks.ts`:

```typescript
// ── Market Prices ─────────────────────────────────────────────────────────────

export interface CoinPrice {
  symbol: string;
  price: number | null;
  change_pct_24h: number | null;
}

export function useMarketPrices() {
  return useSWR<CoinPrice[]>('/api/market/prices', fetcher, { refreshInterval: 10_000 });
}

// ── Market News ───────────────────────────────────────────────────────────────

export interface NewsItem {
  title: string;
  url: string;
  source: string;
  published_at: string;
  category: 'crypto' | 'macro';
  importance: 'normal' | 'high';
}

export function useMarketNews() {
  return useSWR<NewsItem[]>('/api/market/news', fetcher, { refreshInterval: 300_000 });
}
```

- [ ] **Step 2: Kiểm tra TypeScript compile không lỗi**

```bash
cd web/frontend
npx tsc --noEmit
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/lib/hooks.ts
git commit -m "feat(frontend): add useMarketPrices and useMarketNews hooks"
```

---

## Task 5: PriceTickerBar component

**Files:**
- Create: `web/frontend/components/PriceTickerBar.tsx`
- Modify: `web/frontend/__tests__/components.test.tsx`

- [ ] **Step 1: Viết failing test — append vào cuối `web/frontend/__tests__/components.test.tsx`**

Đầu tiên, cập nhật mock của `../lib/hooks` để thêm 2 hook mới. Tìm dòng:
```typescript
jest.mock('../lib/hooks', () => ({
  useBalance: jest.fn(),
  usePositions: jest.fn(),
  usePerformance: jest.fn(),
  useTrades: jest.fn(),
  useBotStatus: jest.fn(),
  useWebSocket: jest.fn(() => []),
}));
```

Thay bằng:
```typescript
jest.mock('../lib/hooks', () => ({
  useBalance: jest.fn(),
  usePositions: jest.fn(),
  usePerformance: jest.fn(),
  useTrades: jest.fn(),
  useBotStatus: jest.fn(),
  useWebSocket: jest.fn(() => []),
  useMarketPrices: jest.fn(),
  useMarketNews: jest.fn(),
}));
```

Thêm import ở dưới dòng `import EventFeed`:
```typescript
import PriceTickerBar from '../components/PriceTickerBar';
import NewsFeed from '../components/NewsFeed';
```

Append tests vào cuối file:
```typescript
// ────────────────────────────────────────────────────────────────────────────
describe('PriceTickerBar', () => {
  it('renders skeleton when loading', () => {
    (hooks.useMarketPrices as jest.Mock).mockReturnValue({ data: null, isLoading: true });
    const { container } = render(<PriceTickerBar />);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders coin prices with green color for positive change', () => {
    (hooks.useMarketPrices as jest.Mock).mockReturnValue({
      data: [
        { symbol: 'BTC', price: 67420, change_pct_24h: 1.24 },
        { symbol: 'ETH', price: 3210,  change_pct_24h: -0.87 },
      ],
      isLoading: false,
    });
    render(<PriceTickerBar />);
    expect(screen.getByText('BTC')).toBeInTheDocument();
    expect(screen.getByText('ETH')).toBeInTheDocument();
    expect(screen.getByText(/1\.24%/)).toBeInTheDocument();
    expect(screen.getByText(/0\.87%/)).toBeInTheDocument();
  });

  it('renders em-dash when price is null', () => {
    (hooks.useMarketPrices as jest.Mock).mockReturnValue({
      data: [{ symbol: 'BTC', price: null, change_pct_24h: null }],
      isLoading: false,
    });
    render(<PriceTickerBar />);
    expect(screen.getByText('—')).toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Chạy failing test**

```bash
cd web/frontend
npx jest PriceTickerBar --no-coverage 2>&1 | tail -10
```

Expected: `Cannot find module '../components/PriceTickerBar'`.

- [ ] **Step 3: Tạo `web/frontend/components/PriceTickerBar.tsx`**

```tsx
'use client';
import { useMarketPrices, type CoinPrice } from '@/lib/hooks';

export default function PriceTickerBar() {
  const { data, isLoading } = useMarketPrices();

  if (isLoading || !data) {
    return (
      <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 flex gap-6 items-center">
        {['BTC', 'ETH', 'BNB', 'SOL', 'ADA'].map(s => (
          <div key={s} className="flex gap-2 items-center animate-pulse">
            <div className="h-3 w-8 bg-gray-700 rounded" />
            <div className="h-3 w-16 bg-gray-700 rounded" />
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-4 py-2.5 flex items-center flex-wrap gap-y-1">
      {data.map((coin: CoinPrice, i: number) => (
        <div key={coin.symbol} className="flex items-center">
          {i > 0 && <span className="text-gray-700 mx-3">|</span>}
          <span className="text-white font-semibold text-sm">{coin.symbol}</span>
          <span className="text-white text-sm ml-1.5">
            {coin.price != null
              ? `$${coin.price.toLocaleString('en-US', {
                  maximumFractionDigits: coin.price >= 1 ? 2 : 4,
                })}`
              : '—'}
          </span>
          {coin.change_pct_24h != null && (
            <span
              className={`text-xs ml-1.5 ${
                coin.change_pct_24h >= 0 ? 'text-green-400' : 'text-red-400'
              }`}
            >
              {coin.change_pct_24h >= 0 ? '▲' : '▼'}{' '}
              {Math.abs(coin.change_pct_24h).toFixed(2)}%
            </span>
          )}
        </div>
      ))}
      <div className="ml-auto flex items-center gap-1.5">
        <span className="h-1.5 w-1.5 rounded-full bg-green-400 animate-pulse" />
        <span className="text-gray-500 text-[10px]">10s</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Chạy tests PriceTickerBar — phải PASS**

```bash
cd web/frontend
npx jest PriceTickerBar --no-coverage
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/components/PriceTickerBar.tsx web/frontend/__tests__/components.test.tsx
git commit -m "feat(frontend): add PriceTickerBar component (10s price polling)"
```

---

## Task 6: NewsFeed component

**Files:**
- Create: `web/frontend/components/NewsFeed.tsx`
- (tests đã thêm vào `components.test.tsx` ở Task 5)

- [ ] **Step 1: Thêm failing tests cho NewsFeed — append vào cuối `__tests__/components.test.tsx`**

```typescript
// ────────────────────────────────────────────────────────────────────────────
describe('NewsFeed', () => {
  it('renders skeleton when loading', () => {
    (hooks.useMarketNews as jest.Mock).mockReturnValue({ data: null, isLoading: true, error: null });
    const { container } = render(<NewsFeed />);
    expect(container.querySelector('.animate-pulse')).toBeTruthy();
  });

  it('renders news items with title and source', () => {
    (hooks.useMarketNews as jest.Mock).mockReturnValue({
      data: [
        {
          title: 'Bitcoin ETF hits record inflows',
          url: 'https://example.com/1',
          source: 'CoinDesk',
          published_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
          category: 'crypto',
          importance: 'high',
        },
        {
          title: 'Fed holds rates steady',
          url: 'https://example.com/2',
          source: 'Yahoo Finance',
          published_at: new Date(Date.now() - 30 * 60 * 1000).toISOString(),
          category: 'macro',
          importance: 'normal',
        },
      ],
      isLoading: false,
      error: null,
    });
    render(<NewsFeed />);
    expect(screen.getByText('Bitcoin ETF hits record inflows')).toBeInTheDocument();
    expect(screen.getByText('Fed holds rates steady')).toBeInTheDocument();
    expect(screen.getByText(/CoinDesk/)).toBeInTheDocument();
  });

  it('shows error message when fetch fails', () => {
    (hooks.useMarketNews as jest.Mock).mockReturnValue({
      data: null, isLoading: false, error: new Error('fail'),
    });
    render(<NewsFeed />);
    expect(screen.getByText(/Không tải được tin tức/)).toBeInTheDocument();
  });

  it('filters to crypto tab correctly', async () => {
    (hooks.useMarketNews as jest.Mock).mockReturnValue({
      data: [
        { title: 'Crypto news', url: '', source: 'CP', published_at: '', category: 'crypto', importance: 'normal' },
        { title: 'Macro news',  url: '', source: 'YF', published_at: '', category: 'macro',  importance: 'normal' },
      ],
      isLoading: false, error: null,
    });
    render(<NewsFeed />);
    // Click Crypto tab
    const { fireEvent } = await import('@testing-library/react');
    fireEvent.click(screen.getByText('Crypto'));
    expect(screen.getByText('Crypto news')).toBeInTheDocument();
    expect(screen.queryByText('Macro news')).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 2: Chạy failing test**

```bash
cd web/frontend
npx jest NewsFeed --no-coverage 2>&1 | tail -5
```

Expected: `Cannot find module '../components/NewsFeed'`.

- [ ] **Step 3: Tạo `web/frontend/components/NewsFeed.tsx`**

```tsx
'use client';
import { useState } from 'react';
import { useMarketNews, type NewsItem } from '@/lib/hooks';

type Tab = 'all' | 'crypto' | 'macro';

function timeAgo(published: string): string {
  try {
    const diff = Math.floor((Date.now() - new Date(published).getTime()) / 1000);
    if (diff < 60) return `${diff}s trước`;
    if (diff < 3600) return `${Math.floor(diff / 60)} phút trước`;
    if (diff < 86400) return `${Math.floor(diff / 3600)} giờ trước`;
    return `${Math.floor(diff / 86400)} ngày trước`;
  } catch {
    return '';
  }
}

function newsIcon(item: NewsItem): string {
  if (item.importance === 'high') return '🚨';
  if (item.category === 'crypto') return '📈';
  return '📉';
}

export default function NewsFeed() {
  const { data, isLoading, error } = useMarketNews();
  const [tab, setTab] = useState<Tab>('all');

  const filtered = (data ?? []).filter(
    item => tab === 'all' || item.category === tab
  );

  return (
    <div className="card flex flex-col">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm text-gray-400 uppercase tracking-wide">Tin tức</h2>
        <div className="flex gap-1">
          {(['all', 'crypto', 'macro'] as Tab[]).map(t => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`text-[10px] px-2 py-0.5 rounded transition-colors ${
                tab === t
                  ? 'bg-blue-900 text-blue-300'
                  : 'bg-gray-800 text-gray-500 hover:text-gray-300'
              }`}
            >
              {t === 'all' ? 'Tất cả' : t === 'crypto' ? 'Crypto' : 'Macro'}
            </button>
          ))}
        </div>
      </div>

      {isLoading && (
        <div className="space-y-3">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="animate-pulse flex gap-2">
              <div className="h-3 w-3 bg-gray-700 rounded flex-shrink-0 mt-0.5" />
              <div className="flex-1 space-y-1">
                <div className="h-3 bg-gray-700 rounded w-full" />
                <div className="h-2 bg-gray-800 rounded w-1/3" />
              </div>
            </div>
          ))}
        </div>
      )}

      {!isLoading && error && !data && (
        <p className="text-gray-500 text-sm">Không tải được tin tức.</p>
      )}

      {!isLoading && !error && filtered.length === 0 && (
        <p className="text-gray-500 text-sm">Không có tin tức.</p>
      )}

      {!isLoading && filtered.length > 0 && (
        <ul className="space-y-0 overflow-y-auto max-h-72 text-xs">
          {filtered.map((item, i) => (
            <li key={i} className="border-b border-gray-800 py-2 last:border-0">
              <a
                href={item.url}
                target="_blank"
                rel="noopener noreferrer"
                className="flex gap-2 items-start hover:bg-gray-800/40 rounded px-1 -mx-1 transition-colors"
              >
                <span className="flex-shrink-0 mt-0.5">{newsIcon(item)}</span>
                <div className="flex-1 min-w-0">
                  <span
                    className={`break-words leading-snug ${
                      item.importance === 'high' ? 'text-red-300' : 'text-gray-200'
                    }`}
                  >
                    {item.title}
                  </span>
                  <span className="block text-gray-600 text-[10px] mt-0.5">
                    {item.source} · {timeAgo(item.published_at)}
                  </span>
                </div>
              </a>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Chạy tất cả frontend tests — phải PASS**

```bash
cd web/frontend
npx jest --no-coverage
```

Expected: tất cả PASSED (không có failed).

- [ ] **Step 5: Commit**

```bash
git add web/frontend/components/NewsFeed.tsx web/frontend/__tests__/components.test.tsx
git commit -m "feat(frontend): add NewsFeed component (CryptoPanic + macro, 5min poll, tab filter)"
```

---

## Task 7: Update page layout + Deploy

**Files:**
- Modify: `web/frontend/app/page.tsx`

- [ ] **Step 1: Cập nhật `web/frontend/app/page.tsx`**

Thay toàn bộ nội dung file:

```tsx
import BalanceCard from '@/components/BalanceCard';
import BotControls from '@/components/BotControls';
import StatsBar from '@/components/StatsBar';
import EquityChart from '@/components/EquityChart';
import PositionsList from '@/components/PositionsList';
import EventFeed from '@/components/EventFeed';
import PriceTickerBar from '@/components/PriceTickerBar';
import NewsFeed from '@/components/NewsFeed';

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>

      {/* Ticker giá real-time */}
      <PriceTickerBar />

      {/* Balance + Bot Controls */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <BalanceCard />
        <BotControls />
      </div>

      {/* PnL / win-rate stats */}
      <StatsBar />

      {/* Equity chart (2/3) + News Feed (1/3) */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <div className="lg:col-span-2">
          <EquityChart />
        </div>
        <NewsFeed />
      </div>

      {/* Open positions + live event feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <PositionsList />
        <EventFeed />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Chạy toàn bộ test suite lần cuối**

```bash
# Backend
cd web/backend && pytest tests/ -v

# Frontend
cd ../frontend && npx jest --no-coverage
```

Expected: tất cả PASSED.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/app/page.tsx
git commit -m "feat(frontend): update dashboard layout — PriceTickerBar top, NewsFeed beside chart"
```

- [ ] **Step 4: Push và deploy lên server**

```bash
git push

# Trên server:
cd ~/crypto-trading-bot
git pull
docker compose up -d --build web-backend web-frontend
```

- [ ] **Step 5: Smoke test trên browser**

Mở `http://<server-ip>:3000`:
- Ticker bar hiển thị giá BTC/ETH/BNB/SOL/ADA với màu xanh/đỏ ✓
- Dot xanh nhấp nháy ở góc phải ticker ✓
- News Feed xuất hiện bên phải Equity Chart ✓
- Tab Crypto/Macro/Tất cả hoạt động ✓
- Click vào tin tức mở link trong tab mới ✓
- F12 → Network: `/api/market/prices` được gọi mỗi ~10s ✓
