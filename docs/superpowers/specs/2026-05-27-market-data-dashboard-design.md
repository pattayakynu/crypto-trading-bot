# Dashboard Market Data — Design Spec
**Date:** 2026-05-27  
**Status:** Approved

## Mục tiêu

Thêm vào dashboard 2 component mới:
1. **PriceTickerBar** — thanh giá real-time 5 coin watchlist (full width, đầu trang)
2. **NewsFeed** — tin tức crypto + macro tài chính (cạnh EquityChart, chiếm 1/3)

---

## Layout (Option B đã chọn)

```
┌─────────────────────────────────────────────┐
│  PriceTickerBar — BTC ETH BNB SOL ADA       │  ← MỚI (full width)
├──────────────────┬──────────────────────────┤
│  BalanceCard     │  BotControls             │
├──────────────────┴──────────────────────────┤
│  StatsBar                                   │
├────────────────────────────┬────────────────┤
│  EquityChart (2/3)         │  NewsFeed (1/3)│  ← NewsFeed MỚI
├──────────────────┬─────────┴────────────────┤
│  PositionsList   │  EventFeed               │
└──────────────────┴──────────────────────────┘
```

---

## Kiến trúc (Backend Proxy — Option B)

### Backend: 2 endpoint mới trong `web/backend/routers/market.py`

#### `GET /api/market/prices`
- Gọi Binance `GET /api/v3/ticker/24hr` với symbols: `BTCUSDT,ETHUSDT,BNBUSDT,SOLUSDT,ADAUSDT`
- Trả về: `[{ symbol, price, change_pct_24h }]`
- Cache in-memory: **30 giây** (tránh quá tải Binance API)
- Fallback: trả về giá trị cuối cùng nếu Binance lỗi

#### `GET /api/market/news`
- Nguồn 1: **CryptoPanic** — `GET https://cryptopanic.com/api/v1/posts/?auth_token=...&public=true`
- Nguồn 2: **Yahoo Finance RSS** — `https://feeds.finance.yahoo.com/rss/2.0/headline?s=^GSPC&region=US&lang=en-US`
- Merge, sort theo thời gian mới nhất, trả về 20 item đầu
- Mỗi item: `{ title, url, source, published_at, category: "crypto"|"macro", importance: "normal"|"high" }`
- Cache: **5 phút** (tin tức không cần real-time)
- `importance = "high"` khi title chứa keyword: Fed, FOMC, SEC, ETF, BTC, crash, ban, hack

### Frontend: 2 component mới

#### `components/PriceTickerBar.tsx`
- `use client` — poll `/api/market/prices` mỗi **10 giây** (setInterval)
- Hiển thị: `SYMBOL  $price  ▲/▼ ±X.XX%` cho 5 coin
- Màu: xanh nếu change_pct_24h > 0, đỏ nếu < 0
- Dot xanh nhấp nháy + text "cập nhật Xs" ở góc phải
- Skeleton loading khi chưa có data

#### `components/NewsFeed.tsx`
- `use client` — poll `/api/market/news` mỗi **5 phút**
- Tab filter: **Crypto** | **Macro** | **Tất cả** (state local)
- Mỗi item: icon theo importance/category + tiêu đề + source + "X phút trước"
- Icon mapping: 🚨 high importance, 📈 crypto tăng, 📉 macro bearish, ⚠️ warning, 📰 normal
- Click item → mở link trong tab mới
- Scroll nội bộ (max-height), không làm layout bị đẩy

---

## Data Flow

```
Browser (10s)          Browser (5min)
    │                       │
    ▼                       ▼
GET /api/market/prices   GET /api/market/news
    │                       │
    ▼  (cache 30s)          ▼  (cache 5min)
Binance API          CryptoPanic API
                     Yahoo Finance RSS
```

---

## Files thay đổi / tạo mới

| File | Thay đổi |
|------|----------|
| `web/backend/routers/market.py` | Tạo mới — `/prices` + `/news` endpoints |
| `web/backend/main.py` | Thêm `include_router(market_router)` |
| `web/backend/requirements.txt` | Thêm `feedparser==6.0.11` (parse RSS) |
| `web/frontend/components/PriceTickerBar.tsx` | Tạo mới |
| `web/frontend/components/NewsFeed.tsx` | Tạo mới |
| `web/frontend/app/page.tsx` | Thêm 2 component vào layout |

---

## Error Handling

- **Binance down**: trả về cache cũ nếu có, otherwise `{ price: null, change_pct_24h: null }`
- **CryptoPanic rate limit**: fallback về RSS only (không crash)
- **RSS parse fail**: bỏ qua nguồn đó, trả về từ nguồn còn lại
- **Frontend**: skeleton loader khi loading, "Không tải được tin tức" khi error sau 3 retry

## Không trong scope

- Biểu đồ giá mini (sparkline) cho từng coin — có thể làm sau
- Lưu news vào DB
- Push notification khi có tin quan trọng
- Tìm kiếm / lọc news theo keyword
