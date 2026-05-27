# ShortBrain Dashboard Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Hiển thị SHORT brain scores và regime trực tiếp trong dashboard bên cạnh LONG conviction scores.

**Architecture:** Mở rộng `SignalLog` với 3 cột SHORT nullable, engine ghi sau khi ShortBrain evaluate, web backend expose qua `/signals/latest`, frontend mở rộng `ScanCard` thêm SHORT section màu đỏ/cam bên dưới LONG bars.

**Tech Stack:** SQLAlchemy (SQLite), FastAPI, Next.js/React/TypeScript, Tailwind CSS.

---

## File Map

| File | Action |
|------|--------|
| `engine/db.py` | Modify — +3 cột nullable + migration helper trong `init_db` |
| `web/backend/models.py` | Modify — mirror 3 cột mới |
| `engine/main.py` | Modify — di chuyển `session.add(SignalLog(...))` xuống sau ShortBrain, thêm 3 field |
| `web/backend/routers/signals.py` | Modify — SHORT_SIGNAL_MAX, SHORT_SIGNAL_LABELS, `short` field trong response |
| `web/backend/tests/test_signals.py` | Modify — cập nhật `_mock_row`, thêm SHORT tests |
| `web/frontend/lib/hooks.ts` | Modify — thêm `ShortSignal` type + `short` field trên `SignalScan` |
| `web/frontend/components/SignalInsight.tsx` | Modify — SHORT section trong `ScanCard` |

---

## Task 1: Mở rộng schema SignalLog

**Files:**
- Modify: `engine/db.py`
- Modify: `web/backend/models.py`

- [ ] **Step 1: Viết failing test — kiểm tra 3 cột mới trên model**

Tạo file `engine/tests/test_signal_log_schema.py`:

```python
"""Test: SignalLog model có 3 cột short mới, nullable, backward-compatible."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, inspect
from db import Base, SignalLog, init_db


def _fresh_engine():
    engine = create_engine("sqlite:///:memory:")
    init_db(engine)
    return engine


def test_signal_log_has_short_columns():
    engine = _fresh_engine()
    inspector = inspect(engine)
    cols = {c["name"] for c in inspector.get_columns("signal_log")}
    assert "short_total_score" in cols
    assert "short_regime" in cols
    assert "short_scores" in cols


def test_short_columns_are_nullable():
    engine = _fresh_engine()
    inspector = inspect(engine)
    col_map = {c["name"]: c for c in inspector.get_columns("signal_log")}
    assert col_map["short_total_score"]["nullable"] is True
    assert col_map["short_regime"]["nullable"] is True
    assert col_map["short_scores"]["nullable"] is True


def test_old_row_without_short_data():
    """Rows cũ không có short data — không crash khi đọc."""
    from sqlalchemy.orm import Session
    engine = _fresh_engine()
    with Session(engine) as s:
        s.add(SignalLog(pair="BTCUSDT", total_score=60, layer_scores="{}", action="BUY"))
        s.commit()
        row = s.query(SignalLog).first()
    assert row.short_total_score is None
    assert row.short_regime is None
    assert row.short_scores is None


def test_new_row_with_short_data():
    """Rows mới có đủ short data — ghi và đọc đúng."""
    import json
    from sqlalchemy.orm import Session
    engine = _fresh_engine()
    scores = {"alt_weakness": 0, "funding_reset": 15, "volume_exhaustion": 25, "macro_bearish": 0}
    with Session(engine) as s:
        s.add(SignalLog(
            pair="ETHUSDT", total_score=45, layer_scores="{}", action="SKIP",
            short_total_score=40, short_regime="SIDEWAYS",
            short_scores=json.dumps(scores),
        ))
        s.commit()
        row = s.query(SignalLog).first()
    assert row.short_total_score == 40
    assert row.short_regime == "SIDEWAYS"
    assert json.loads(row.short_scores)["funding_reset"] == 15
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

```
cd engine
python -m pytest tests/test_signal_log_schema.py -v
```

Expected: `AttributeError: type object 'SignalLog' has no attribute 'short_total_score'` hoặc `AssertionError: 'short_total_score' not in cols`

- [ ] **Step 3: Thêm 3 cột vào `engine/db.py`**

Mở `engine/db.py`, tìm class `SignalLog` và thêm 3 cột mới. Đồng thời thêm migration helper vào `init_db`:

```python
class SignalLog(Base):
    __tablename__ = "signal_log"
    id = Column(Integer, primary_key=True)
    pair = Column(String, nullable=False)
    total_score = Column(Integer, nullable=False)
    layer_scores = Column(String, nullable=True)
    action = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # ShortBrain fields — nullable for backward compatibility (old rows = NULL)
    short_total_score = Column(Integer, nullable=True)
    short_regime      = Column(String,  nullable=True)
    short_scores      = Column(String,  nullable=True)  # JSON string
```

Cập nhật `init_db` để migrate bảng hiện tại (SQLite không tự thêm cột vào bảng đã tồn tại):

```python
def init_db(engine):
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        if session.query(LayerWeight).count() == 0:
            for name in ["whale", "macro", "fiat_flow", "btc_lead", "ta", "social"]:
                session.add(LayerWeight(name=name, weight=1.0))
            session.commit()
    # Migrate existing signal_log table — add short columns if missing
    _migrate_signal_log(engine)


def _migrate_signal_log(engine):
    """Add short_* columns to signal_log if they don't exist yet (idempotent)."""
    from sqlalchemy import text, inspect as sa_inspect
    inspector = sa_inspect(engine)
    existing = {c["name"] for c in inspector.get_columns("signal_log")}
    migrations = [
        ("short_total_score", "INTEGER"),
        ("short_regime",      "TEXT"),
        ("short_scores",      "TEXT"),
    ]
    with engine.connect() as conn:
        for col_name, col_type in migrations:
            if col_name not in existing:
                conn.execute(text(f"ALTER TABLE signal_log ADD COLUMN {col_name} {col_type}"))
        conn.commit()
```

- [ ] **Step 4: Mirror 3 cột vào `web/backend/models.py`**

Tìm class `SignalLog` trong `web/backend/models.py`, thay thế:

```python
class SignalLog(Base):
    __tablename__ = "signal_log"
    id = Column(Integer, primary_key=True)
    pair = Column(String, nullable=False)
    total_score = Column(Integer, nullable=False)
    layer_scores = Column(String, nullable=True)
    action = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    # ShortBrain fields — nullable for backward compatibility (old rows = NULL)
    short_total_score = Column(Integer, nullable=True)
    short_regime      = Column(String,  nullable=True)
    short_scores      = Column(String,  nullable=True)  # JSON string
```

- [ ] **Step 5: Chạy test — xác nhận PASS**

```
cd engine
python -m pytest tests/test_signal_log_schema.py -v
```

Expected:
```
test_signal_log_has_short_columns PASSED
test_short_columns_are_nullable PASSED
test_old_row_without_short_data PASSED
test_new_row_with_short_data PASSED
```

- [ ] **Step 6: Commit**

```bash
git add engine/db.py web/backend/models.py engine/tests/test_signal_log_schema.py
git commit -m "feat: extend SignalLog schema with short_total_score, short_regime, short_scores"
```

---

## Task 2: Engine ghi ShortBrain result vào SignalLog

**Files:**
- Modify: `engine/main.py`

Hiện tại `session.add(SignalLog(...))` được gọi TRƯỚC khi ShortBrain evaluate (line 249-255). Cần di chuyển xuống sau ShortBrain để thêm short fields.

- [ ] **Step 1: Xác nhận vị trí hiện tại của `session.add(SignalLog(...))`**

Chạy:
```bash
grep -n "session.add(SignalLog" engine/main.py
```

Expected output: dòng ~249, trước block `# ── SHORT brain evaluation ──`.

- [ ] **Step 2: Xóa SignalLog write cũ và di chuyển xuống sau ShortBrain**

Trong `engine/main.py`, tìm đoạn:

```python
    # Log signal
    session.add(SignalLog(
        pair=pair,
        total_score=conviction.total_score,
        layer_scores=json.dumps(layer_scores.as_dict()),
        action=conviction.action,
    ))
    session.commit()

    publisher.publish_signal(
```

Thay bằng (chỉ giữ `publisher.publish_signal`, bỏ SignalLog write):

```python
    publisher.publish_signal(
```

Sau đó, tìm đoạn:

```python
    short_signal = short_brain.get_short_signal(
        symbol=pair,
        btc_change=btc_change,
        alt_change=price_change,
        has_open_long=has_open_long,
    )

    if not conviction.should_trade and not short_signal.should_short:
        return {"pair": pair, "action": conviction.action, "score": conviction.total_score}
```

Thêm SignalLog write ngay SAU `short_signal = short_brain.get_short_signal(...)`:

```python
    short_signal = short_brain.get_short_signal(
        symbol=pair,
        btc_change=btc_change,
        alt_change=price_change,
        has_open_long=has_open_long,
    )

    # Log signal — ghi sau khi ShortBrain evaluate để có đủ short fields
    session.add(SignalLog(
        pair=pair,
        total_score=conviction.total_score,
        layer_scores=json.dumps(layer_scores.as_dict()),
        action=conviction.action,
        short_total_score=short_signal.score,
        short_regime=short_signal.regime if isinstance(short_signal.regime, str) else str(short_signal.regime),
        short_scores=json.dumps(short_signal.signal_scores) if short_signal.signal_scores else None,
    ))
    session.commit()

    if not conviction.should_trade and not short_signal.should_short:
        return {"pair": pair, "action": conviction.action, "score": conviction.total_score}
```

- [ ] **Step 3: Kiểm tra verify.py và toàn bộ engine tests**

```bash
cd engine
python -m pytest tests/ -v --tb=short
```

Expected: tất cả tests pass. Đặc biệt các test liên quan đến `main.py` mock SignalLog sẽ cần chú ý nếu có.

```bash
python verify.py
```

Expected: 36/36 (hoặc số hiện tại) — tất cả OK.

- [ ] **Step 4: Commit**

```bash
git add engine/main.py
git commit -m "feat: write ShortBrain result to SignalLog after evaluation"
```

---

## Task 3: Backend API expose SHORT data

**Files:**
- Modify: `web/backend/routers/signals.py`
- Modify: `web/backend/tests/test_signals.py`

- [ ] **Step 1: Viết failing tests**

Mở `web/backend/tests/test_signals.py`. Thực hiện 2 thay đổi:

**Thay đổi 1 — cập nhật `_mock_row` helper** để nhận `short_total_score`, `short_regime`, `short_scores` với default `None`:

```python
def _mock_row(
    id: int,
    pair: str,
    total_score: int,
    layer_scores: str,
    action: str,
    created_at=None,
    short_total_score=None,
    short_regime=None,
    short_scores=None,
):
    row = MagicMock()
    row.id = id
    row.pair = pair
    row.total_score = total_score
    row.layer_scores = layer_scores
    row.action = action
    row.created_at = created_at or datetime(2026, 5, 27, 10, 0, 0)
    row.short_total_score = short_total_score
    row.short_regime = short_regime
    row.short_scores = short_scores
    return row
```

**Thay đổi 2 — thêm 5 test mới** ở cuối file:

```python
# ── SHORT signal field ────────────────────────────────────────────────────────

def test_signals_short_null_when_no_short_data():
    """Rows cũ (short_scores=None) → short: null trong response."""
    row = _mock_row(10, "BTCUSDT", 60, '{}', "BUY",
                    short_total_score=None, short_regime=None, short_scores=None)
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    btc = next(d for d in resp.json() if d["pair"] == "BTCUSDT")
    assert btc["scans"][0]["short"] is None


def test_signals_short_populated_when_present():
    """Rows mới có short data → short field đúng cấu trúc."""
    import json
    scores_json = json.dumps({
        "alt_weakness": 0,
        "funding_reset": 0,
        "volume_exhaustion": 15,
        "macro_bearish": 0,
    })
    row = _mock_row(11, "SOLUSDT", 45, '{}', "SKIP",
                    short_total_score=15, short_regime="SIDEWAYS",
                    short_scores=scores_json)
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    sol = next(d for d in resp.json() if d["pair"] == "SOLUSDT")
    short = sol["scans"][0]["short"]
    assert short is not None
    assert short["score"] == 15
    assert short["regime"] == "SIDEWAYS"
    assert "signals" in short


def test_signals_short_signals_shape():
    """short.signals có đủ 4 keys, mỗi key có score/max/pct/label."""
    import json
    scores_json = json.dumps({
        "alt_weakness": 0,
        "funding_reset": 25,
        "volume_exhaustion": 15,
        "macro_bearish": 0,
    })
    row = _mock_row(12, "ETHUSDT", 50, '{}', "WATCH",
                    short_total_score=40, short_regime="BEAR",
                    short_scores=scores_json)
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    eth = next(d for d in resp.json() if d["pair"] == "ETHUSDT")
    signals = eth["scans"][0]["short"]["signals"]
    for key in ("alt_weakness", "funding_reset", "volume_exhaustion", "macro_bearish"):
        assert key in signals
        sig = signals[key]
        assert "score" in sig
        assert "max" in sig
        assert "pct" in sig
        assert "label" in sig

    assert signals["funding_reset"]["score"] == 25
    assert signals["funding_reset"]["max"] == 25
    assert signals["funding_reset"]["pct"] == 100


def test_signals_short_pct_calculation():
    """pct = round(score / max * 100)"""
    import json
    scores_json = json.dumps({
        "alt_weakness": 15,
        "funding_reset": 0,
        "volume_exhaustion": 0,
        "macro_bearish": 0,
    })
    row = _mock_row(13, "BNBUSDT", 40, '{}', "SKIP",
                    short_total_score=15, short_regime="SIDEWAYS",
                    short_scores=scores_json)
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    bnb = next(d for d in resp.json() if d["pair"] == "BNBUSDT")
    signals = bnb["scans"][0]["short"]["signals"]
    # 15/25 = 60%
    assert signals["alt_weakness"]["pct"] == 60


def test_signals_short_malformed_json_returns_null():
    """short_scores JSON bị corrupt → short: null, không crash."""
    row = _mock_row(14, "ADAUSDT", 35, '{}', "SKIP",
                    short_total_score=10, short_regime="SIDEWAYS",
                    short_scores="NOT_VALID_JSON{{{")
    client = _get_client()
    with patch("routers.signals.get_session") as mock_fn:
        session = MagicMock()
        mock_fn.return_value = session
        session.query.return_value.filter.return_value.order_by.return_value.limit.return_value.all.return_value = [row]
        resp = client.get("/api/signals/latest", headers=HEADERS)
    ada = next(d for d in resp.json() if d["pair"] == "ADAUSDT")
    assert ada["scans"][0]["short"] is None
```

- [ ] **Step 2: Chạy test — xác nhận FAIL**

```
cd web/backend
python -m pytest tests/test_signals.py -v -k "short"
```

Expected: tất cả 5 test mới FAIL với `KeyError: 'short'` hoặc `AssertionError`.

- [ ] **Step 3: Cập nhật `web/backend/routers/signals.py`**

Thêm constants SAU `LAYER_LABELS`:

```python
SHORT_SIGNAL_MAX = {
    "alt_weakness":      25,
    "funding_reset":     25,
    "volume_exhaustion": 25,
    "macro_bearish":     25,
}

SHORT_SIGNAL_LABELS = {
    "alt_weakness":      "Alt yếu",
    "funding_reset":     "Funding reset",
    "volume_exhaustion": "Vol cạn kiệt",
    "macro_bearish":     "Vĩ mô giảm",
}

SHORT_SIGNAL_ORDER = ["alt_weakness", "funding_reset", "volume_exhaustion", "macro_bearish"]
```

Trong loop `for row in rows:`, sau khi build `layers = {}`, thêm block build `short`:

```python
                # Build short field
                short = None
                if row.short_scores is not None:
                    try:
                        short_raw = json.loads(row.short_scores)
                        short_signals = {}
                        for key in SHORT_SIGNAL_ORDER:
                            score = int(short_raw.get(key, 0))
                            max_s = SHORT_SIGNAL_MAX[key]
                            pct   = round(score / max_s * 100) if max_s else 0
                            short_signals[key] = {
                                "score": score,
                                "max":   max_s,
                                "pct":   pct,
                                "label": SHORT_SIGNAL_LABELS[key],
                            }
                        short = {
                            "score":   row.short_total_score or 0,
                            "regime":  row.short_regime or "",
                            "signals": short_signals,
                        }
                    except Exception:
                        short = None
```

Trong `scans.append({...})`, thêm `"short": short` vào cuối:

```python
                scans.append({
                    "id":          row.id,
                    "scanned_at":  scanned_at,
                    "total_score": row.total_score,
                    "action":      row.action or "SKIP",
                    "confidence":  _confidence(row.total_score),
                    "layers":      layers,
                    "short":       short,
                })
```

- [ ] **Step 4: Chạy toàn bộ test_signals.py — xác nhận tất cả PASS**

```
cd web/backend
python -m pytest tests/test_signals.py -v
```

Expected: 17/17 tests PASS (12 cũ + 5 mới).

- [ ] **Step 5: Commit**

```bash
git add web/backend/routers/signals.py web/backend/tests/test_signals.py
git commit -m "feat: expose ShortBrain scores in /signals/latest API response"
```

---

## Task 4: Frontend types — ShortSignal + SignalScan.short

**Files:**
- Modify: `web/frontend/lib/hooks.ts`

- [ ] **Step 1: Thêm `ShortSignal` type và cập nhật `SignalScan`**

Mở `web/frontend/lib/hooks.ts`. Tìm đoạn:

```typescript
export interface LayerInfo {
  score: number;
  max: number;
  pct: number;
  strength: 'STRONG' | 'MODERATE' | 'WEAK' | 'NONE';
  label: string;
}
```

Thêm interface `ShortSignalInfo` và `ShortSignal` SAU `LayerInfo`:

```typescript
export interface ShortSignalInfo {
  score: number;
  max: number;
  pct: number;
  label: string;
}

export interface ShortSignal {
  score: number;
  regime: string;
  signals: Record<string, ShortSignalInfo>;
}
```

Cập nhật `SignalScan` để thêm field `short`:

```typescript
export interface SignalScan {
  id: number;
  scanned_at: string | null;
  total_score: number;
  action: string;
  confidence: 'HIGH' | 'MEDIUM' | 'LOW';
  layers: Record<string, LayerInfo>;
  short: ShortSignal | null;
}
```

- [ ] **Step 2: Kiểm tra TypeScript compile**

```
cd web/frontend
npx tsc --noEmit
```

Expected: không có lỗi TypeScript.

- [ ] **Step 3: Commit**

```bash
git add web/frontend/lib/hooks.ts
git commit -m "feat: add ShortSignal type and short field to SignalScan"
```

---

## Task 5: Frontend ScanCard — SHORT section

**Files:**
- Modify: `web/frontend/components/SignalInsight.tsx`

- [ ] **Step 1: Cập nhật import và thêm helpers/constants**

Mở `web/frontend/components/SignalInsight.tsx`.

Thay đổi import ở dòng đầu:

```typescript
import { useSignals, type CoinSignal, type SignalScan, type ShortSignal } from '@/lib/hooks';
```

Thêm 2 constants và 1 helper SAU dòng `const LAYER_ORDER`:

```typescript
const SHORT_SIGNAL_ORDER = ['alt_weakness', 'funding_reset', 'volume_exhaustion', 'macro_bearish'];

function shortScoreColor(score: number): string {
  if (score >= 65) return 'text-red-400';
  if (score >= 40) return 'text-orange-400';
  return 'text-gray-500';
}
```

- [ ] **Step 2: Thêm SHORT section vào `ScanCard`**

Trong `ScanCard`, tìm dòng `</div>` cuối cùng trước khi đóng `return (...)`:

```tsx
      {/* Layer bars */}
      <div className="space-y-1">
        {LAYER_ORDER.map(key => {
          ...
        })}
      </div>
    </div>
  );
}
```

Thêm SHORT section ngay SAU `</div>` của "Layer bars" và TRƯỚC `</div>` đóng component:

```tsx
      {/* SHORT section — chỉ hiển thị khi có short data */}
      {scan.short && (
        <>
          {/* Divider + SHORT header */}
          <div className="flex items-center gap-2 pt-1 border-t border-gray-800">
            <span className="text-[9px] text-red-500 font-semibold">SHORT</span>
            <span className={`text-[10px] font-bold tabular-nums ${shortScoreColor(scan.short.score)}`}>
              {scan.short.score}/100
            </span>
            <span className="text-[9px] text-gray-600 ml-auto">{scan.short.regime}</span>
          </div>

          {/* 4 SHORT signal bars — đỏ thay vì xanh */}
          <div className="space-y-1">
            {SHORT_SIGNAL_ORDER.map(key => {
              const sig = scan.short!.signals[key];
              if (!sig) return null;
              return (
                <div key={key} className="flex items-center gap-1.5">
                  <span className="text-gray-500 text-[9px] w-14 flex-shrink-0 truncate">
                    {sig.label}
                  </span>
                  <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-red-600"
                      style={{ width: `${sig.pct}%` }}
                    />
                  </div>
                  <span className="text-gray-600 text-[9px] w-7 text-right flex-shrink-0 tabular-nums">
                    {sig.score}/{sig.max}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}
```

Kết quả `ScanCard` hoàn chỉnh sau khi sửa:

```tsx
function ScanCard({ scan, dim }: { scan: SignalScan; dim?: boolean }) {
  return (
    <div
      className={`border border-gray-800 rounded p-2.5 flex flex-col gap-2 ${dim ? 'opacity-40' : ''}`}
      data-testid="scan-card"
    >
      {/* Header: score + action + time */}
      <div className="flex items-center gap-2">
        <span className={`text-xl font-bold tabular-nums leading-none ${scoreColor(scan.total_score)}`}>
          {scan.total_score}
        </span>
        <div className="flex flex-col gap-0.5 min-w-0">
          <ActionBadge action={scan.action} confidence={scan.confidence} />
          <span className="text-gray-600 text-[9px]">{timeAgo(scan.scanned_at)}</span>
        </div>
      </div>

      {/* Layer bars */}
      <div className="space-y-1">
        {LAYER_ORDER.map(key => {
          const layer = scan.layers[key];
          if (!layer) return null;
          return (
            <div key={key} className="flex items-center gap-1.5">
              <span className="text-gray-500 text-[9px] w-14 flex-shrink-0 truncate">
                {layer.label}
              </span>
              <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                <div
                  className={`h-full rounded-full ${strengthBar(layer.strength)}`}
                  style={{ width: `${layer.pct}%` }}
                />
              </div>
              <span className="text-gray-600 text-[9px] w-7 text-right flex-shrink-0 tabular-nums">
                {layer.score}/{layer.max}
              </span>
            </div>
          );
        })}
      </div>

      {/* SHORT section — chỉ hiển thị khi có short data */}
      {scan.short && (
        <>
          {/* Divider + SHORT header */}
          <div className="flex items-center gap-2 pt-1 border-t border-gray-800">
            <span className="text-[9px] text-red-500 font-semibold">SHORT</span>
            <span className={`text-[10px] font-bold tabular-nums ${shortScoreColor(scan.short.score)}`}>
              {scan.short.score}/100
            </span>
            <span className="text-[9px] text-gray-600 ml-auto">{scan.short.regime}</span>
          </div>

          {/* 4 SHORT signal bars — đỏ thay vì xanh */}
          <div className="space-y-1">
            {SHORT_SIGNAL_ORDER.map(key => {
              const sig = scan.short!.signals[key];
              if (!sig) return null;
              return (
                <div key={key} className="flex items-center gap-1.5">
                  <span className="text-gray-500 text-[9px] w-14 flex-shrink-0 truncate">
                    {sig.label}
                  </span>
                  <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full rounded-full bg-red-600"
                      style={{ width: `${sig.pct}%` }}
                    />
                  </div>
                  <span className="text-gray-600 text-[9px] w-7 text-right flex-shrink-0 tabular-nums">
                    {sig.score}/{sig.max}
                  </span>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
```

- [ ] **Step 3: TypeScript compile check**

```
cd web/frontend
npx tsc --noEmit
```

Expected: không có lỗi TypeScript.

- [ ] **Step 4: Build check**

```
cd web/frontend
npm run build
```

Expected: build thành công, không có lỗi.

- [ ] **Step 5: Commit**

```bash
git add web/frontend/components/SignalInsight.tsx
git commit -m "feat: add SHORT brain section to ScanCard in dashboard"
```

---

## Task 6: Deploy và verify end-to-end

- [ ] **Step 1: Chạy toàn bộ test suite**

```bash
# Engine tests
cd engine && python -m pytest tests/ -v --tb=short

# Web backend tests
cd web/backend && python -m pytest tests/ -v --tb=short

# verify.py
cd .. && python verify.py
```

Expected: tất cả pass, verify.py 36+/36 OK.

- [ ] **Step 2: Deploy lên server**

```bash
git stash 2>/dev/null || true
git pull
docker compose up -d --build engine web
```

Note: cần rebuild cả `web` (backend) vì `models.py` thay đổi. Frontend được serve qua Docker nên cũng cần rebuild.

- [ ] **Step 3: Kiểm tra engine log có short fields**

SSH vào server, chạy:

```bash
docker logs crypto-trading-bot-engine-1 --tail 50 2>&1 | grep ShortBrain
```

Expected: log format `[ShortBrain] BTCUSDT score=XX/100 regime=SIDEWAYS alt=X fund=X vol=X macro=X → SKIP`

- [ ] **Step 4: Kiểm tra API response có `short` field**

```bash
curl -s -H "X-API-Key: $WEB_API_KEY" http://localhost:8000/api/signals/latest | python3 -c "
import json, sys
data = json.load(sys.stdin)
for coin in data:
    scan = coin['scans'][0] if coin['scans'] else None
    if scan:
        print(f\"{coin['pair']}: short={scan.get('short')}\")
"
```

Expected: mỗi coin có `short=None` (rows cũ) hoặc `short={'score': X, 'regime': '...', 'signals': {...}}` (rows mới sau lần scan đầu tiên).

- [ ] **Step 5: Mở dashboard, xác nhận SHORT section hiển thị**

Mở `http://server-ip:3000` (hoặc port dashboard). Sau lần scan tiếp theo (~5 phút), ScanCard của mỗi coin phải hiển thị:
- Divider với nhãn "SHORT" màu đỏ
- Score `/100` màu đỏ/cam/xám tùy theo threshold
- Regime label (SIDEWAYS/BEAR/BULL)
- 4 bars màu đỏ: Alt yếu, Funding reset, Vol cạn kiệt, Vĩ mô giảm

- [ ] **Step 6: Commit final**

```bash
git add -A
git commit -m "feat: ShortBrain dashboard integration complete — schema + API + frontend"
```
