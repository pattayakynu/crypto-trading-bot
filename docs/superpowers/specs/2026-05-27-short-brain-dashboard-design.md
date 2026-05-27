# ShortBrain Dashboard Integration — Design Spec

**Goal:** Hiển thị SHORT brain scores và regime trực tiếp trong dashboard bên cạnh LONG conviction scores, giúp người dùng thấy cả 2 luồng suy nghĩ của bot cho mỗi coin.

**Architecture:** Mở rộng `SignalLog` với 3 cột SHORT, engine ghi sau khi ShortBrain evaluate, web backend expose qua `/signals/latest`, frontend mở rộng `ScanCard` thêm SHORT section.

**Tech Stack:** SQLAlchemy (SQLite), FastAPI, Next.js/React/TypeScript, Tailwind CSS.

---

## Data Flow

```
Engine (main.py)
  → ShortBrain.get_short_signal()
  → SignalLog(short_total_score, short_regime, short_scores)
  → SQLite /data/trading.db

Web Backend (signals.py)
  → SELECT signal_log ... ORDER BY id DESC LIMIT 3
  → Parse short_scores JSON
  → Return { ..., short: { score, regime, signals: {...} } }

Frontend (SignalInsight.tsx)
  → ScanCard renders SHORT section below LONG bars
```

---

## Schema Change — `signal_log`

Thêm 3 cột nullable vào bảng hiện tại (tương thích ngược — rows cũ có NULL):

| Cột | Kiểu | Mô tả |
|-----|------|-------|
| `short_total_score` | INTEGER nullable | Tổng điểm ShortBrain 0–100 |
| `short_regime` | TEXT nullable | `"BULL"` / `"BEAR"` / `"SIDEWAYS"` |
| `short_scores` | TEXT nullable | JSON: `{"alt_weakness":0,"funding_reset":0,"volume_exhaustion":15,"macro_bearish":0}` |

Không lưu `blocked_reason` vào DB — thông tin này suy ra được từ `short_regime` và `short_total_score=0`.

---

## Engine Changes — `engine/db.py` + `engine/main.py`

### engine/db.py
Thêm 3 cột vào `SignalLog`:
```python
short_total_score = Column(Integer,  nullable=True)
short_regime      = Column(String,   nullable=True)
short_scores      = Column(String,   nullable=True)  # JSON string
```

### engine/main.py
Di chuyển `session.add(SignalLog(...))` xuống sau khi ShortBrain evaluate xong, bổ sung 3 field mới:

```python
short_signal = short_brain.get_short_signal(...)

session.add(SignalLog(
    pair=pair,
    total_score=conviction.total_score,
    layer_scores=json.dumps(layer_scores.as_dict()),
    action=conviction.action,
    short_total_score=short_signal.score,
    short_regime=short_signal.regime,
    short_scores=json.dumps(short_signal.signal_scores),
))
session.commit()
```

---

## API Change — `web/backend/routers/signals.py`

Thêm constants:
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
```

Mỗi scan trong response thêm field `short`:
```json
{
  "short": {
    "score": 15,
    "regime": "SIDEWAYS",
    "signals": {
      "alt_weakness":      { "score": 0,  "max": 25, "pct": 0,  "label": "Alt yếu" },
      "funding_reset":     { "score": 0,  "max": 25, "pct": 0,  "label": "Funding reset" },
      "volume_exhaustion": { "score": 15, "max": 25, "pct": 60, "label": "Vol cạn kiệt" },
      "macro_bearish":     { "score": 0,  "max": 25, "pct": 0,  "label": "Vĩ mô giảm" }
    }
  }
}
```

Khi `short_scores` là NULL (rows cũ): trả về `short: null`.

---

## Frontend Change — `SignalInsight.tsx`

### Types (hooks.ts)
```typescript
export type ShortSignal = {
  score:   number;
  regime:  string;
  signals: Record<string, { score: number; max: number; pct: number; label: string }>;
};

export type SignalScan = {
  // ...existing fields...
  short: ShortSignal | null;
};
```

### ScanCard — SHORT section

Thêm vào cuối `ScanCard`, sau LONG bars:

```tsx
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

    {/* 4 signal bars — đỏ/cam thay vì xanh */}
    <div className="space-y-1">
      {SHORT_SIGNAL_ORDER.map(key => {
        const sig = scan.short!.signals[key];
        return (
          <div key={key} className="flex items-center gap-1.5">
            <span className="text-gray-500 text-[9px] w-14 flex-shrink-0 truncate">{sig.label}</span>
            <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
              <div className="h-full rounded-full bg-red-600" style={{ width: `${sig.pct}%` }} />
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

`short: null` (rows cũ) → không render SHORT section. Không crash.

---

## File Map

| File | Action |
|------|--------|
| `engine/db.py` | Modify — +3 cột `SignalLog` |
| `engine/main.py` | Modify — ghi `short_*` sau ShortBrain |
| `web/backend/models.py` | Modify — mirror 3 cột mới |
| `web/backend/routers/signals.py` | Modify — thêm `short` vào response |
| `web/frontend/lib/hooks.ts` | Modify — thêm `ShortSignal` type + `short` field |
| `web/frontend/components/SignalInsight.tsx` | Modify — SHORT section trong ScanCard |

Tests cần update:
- `web/backend/tests/test_positions.py` (nếu test SignalLog schema)
- `web/frontend/__tests__/api.test.ts` (nếu test signal response shape)

---

## Error Handling

- `short_scores` NULL → `short: null` trong API, frontend không render SHORT section
- ShortBrain throw exception → engine catch, ghi `short_total_score=0, short_regime=None, short_scores=None`
- Backend parse lỗi JSON → trả `short: null` thay vì crash
