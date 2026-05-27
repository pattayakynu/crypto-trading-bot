# Short Brain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a dedicated SHORT signal engine with market regime detection and dual-LLM confirmation, replacing the broken rule-based short logic in main.py.

**Architecture:** `regime.py` detects BULL/BEAR/SIDEWAYS weekly; `short_brain.py` scores 4 bearish signals (alt weakness, funding reset, volume exhaustion, macro bearish) max 100pts with hard risk filters; `llm_advisor.py` gains `analyze_short()` mirror method; `main.py` replaces `is_bearish_short` with the new pipeline. SHORT now goes through the same LLM dual-confirm gate as LONG — disagreement skips the trade.

**Tech Stack:** Python 3.12, httpx (CoinGecko), yfinance (UUP/DXY), python-binance (funding rate + klines), pytest + unittest.mock.

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `engine/regime.py` | Create | BTC 7d trend + DXY 10d trend → BULL/BEAR/SIDEWAYS (1h cache) |
| `engine/short_brain.py` | Create | 4 signals scored 0-25 each; risk filters; returns ShortSignal |
| `engine/llm_advisor.py` | Modify | Add `_build_short_prompt`, `analyze_short`, `analyze_short_with_mock` |
| `engine/main.py` | Modify | Replace `is_bearish_short`; add LLM SHORT gate; fix size/leverage |
| `engine/tests/test_regime.py` | Create | 8 unit tests for RegimeDetector |
| `engine/tests/test_short_brain.py` | Create | 18 unit tests for ShortBrain signals + filters |
| `engine/tests/test_llm_advisor.py` | Modify | Add 4 tests for analyze_short |
| `verify.py` | Modify | Replace old btc_lead/ta/macro SHORT checks with new module checks |

---

## Task 1: regime.py — Market Regime Detector

**Files:**
- Create: `engine/regime.py`
- Create: `engine/tests/test_regime.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_regime.py
import pytest
from unittest.mock import patch
import regime as regime_module
from regime import RegimeDetector, MarketRegime


def setup_function():
    """Reset module-level cache before each test."""
    regime_module._regime_cache = {"value": None, "ts": 0.0}


def make_detector():
    return RegimeDetector(client=None)


def test_bull_regime_btc_up_dxy_flat():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=7.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == MarketRegime.BULL


def test_bear_regime_btc_down():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=-6.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.0):
        assert d.detect() == MarketRegime.BEAR


def test_bear_regime_dxy_strong_overrides_btc_up():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=8.0), \
         patch.object(d, "get_dxy_10d_change", return_value=2.0):
        assert d.detect() == MarketRegime.BEAR


def test_sideways_regime_btc_moderate_dxy_flat():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=2.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        assert d.detect() == MarketRegime.SIDEWAYS


def test_sideways_regime_btc_flat():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=0.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.0):
        assert d.detect() == MarketRegime.SIDEWAYS


def test_detect_returns_valid_regime_string():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=0.0), \
         patch.object(d, "get_dxy_10d_change", return_value=0.0):
        result = d.detect()
        assert result in (MarketRegime.BULL, MarketRegime.BEAR, MarketRegime.SIDEWAYS)


def test_cache_prevents_second_fetch():
    d = make_detector()
    with patch.object(d, "get_btc_7d_change", return_value=7.0) as mock_btc, \
         patch.object(d, "get_dxy_10d_change", return_value=0.5):
        d.detect()
        d.detect()
        assert mock_btc.call_count == 1   # Only called once — second hit uses cache


def test_btc_7d_change_returns_zero_on_network_error():
    d = make_detector()
    with patch("regime.httpx.get", side_effect=Exception("timeout")):
        assert d.get_btc_7d_change() == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd engine/tests && python -m pytest test_regime.py -v
```
Expected: `ImportError: No module named 'regime'`

- [ ] **Step 3: Implement regime.py**

```python
# engine/regime.py
import logging
import time
import httpx
import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

log = logging.getLogger(__name__)

BTC_BULL_THRESHOLD = 5.0    # BTC 7d > +5% = weekly uptrend
BTC_BEAR_THRESHOLD = -5.0   # BTC 7d < -5% = weekly downtrend
DXY_BEAR_THRESHOLD = 1.5    # UUP 10d > +1.5% = strong dollar = crypto headwind

_regime_cache: dict = {"value": None, "ts": 0.0}
_REGIME_TTL = 3600  # Regime doesn't change quickly — cache 1 hour


class MarketRegime:
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


class RegimeDetector:
    def __init__(self, client=None):
        self.client = client

    def get_btc_7d_change(self) -> float:
        """BTC 7-day price change % from CoinGecko (no API key needed)."""
        try:
            resp = httpx.get(
                "https://api.coingecko.com/api/v3/simple/price",
                params={
                    "ids": "bitcoin",
                    "vs_currencies": "usd",
                    "include_7d_change": "true",
                },
                timeout=6.0,
            )
            if resp.status_code == 200:
                return float(resp.json().get("bitcoin", {}).get("usd_7d_change", 0))
        except Exception as e:
            log.debug("CoinGecko 7d change failed: %s", e)
        return 0.0

    def get_dxy_10d_change(self) -> float:
        """UUP 10-day % change via yfinance (same source as macro.py)."""
        try:
            hist = yf.Ticker("UUP").history(period="15d")
            if len(hist) < 10:
                return 0.0
            prev = float(hist["Close"].iloc[-10])
            curr = float(hist["Close"].iloc[-1])
            return (curr - prev) / prev * 100 if prev != 0 else 0.0
        except Exception as e:
            log.debug("yfinance UUP 10d failed: %s", e)
        return 0.0

    def detect(self) -> str:
        """
        BULL:     BTC 7d >= +5% AND DXY 10d < +1.5%
        BEAR:     BTC 7d <= -5% OR DXY 10d >= +1.5%
        SIDEWAYS: everything else
        Result cached for 1 hour.
        """
        global _regime_cache
        now = time.time()
        if _regime_cache["value"] is not None and now - _regime_cache["ts"] < _REGIME_TTL:
            return _regime_cache["value"]

        btc_7d = self.get_btc_7d_change()
        dxy_10d = self.get_dxy_10d_change()

        if btc_7d >= BTC_BULL_THRESHOLD and dxy_10d < DXY_BEAR_THRESHOLD:
            regime = MarketRegime.BULL
        elif btc_7d <= BTC_BEAR_THRESHOLD or dxy_10d >= DXY_BEAR_THRESHOLD:
            regime = MarketRegime.BEAR
        else:
            regime = MarketRegime.SIDEWAYS

        log.info("Market regime: %s (BTC 7d=%.1f%%, DXY 10d=%.2f%%)", regime, btc_7d, dxy_10d)
        _regime_cache = {"value": regime, "ts": now}
        return regime
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd engine/tests && python -m pytest test_regime.py -v
```
Expected: `8 passed`

- [ ] **Step 5: Commit**

```bash
git add engine/regime.py engine/tests/test_regime.py
git commit -m "feat(short): add MarketRegime detector (BTC 7d + DXY 10d)"
```

---

## Task 2: short_brain.py — Signal Scoring + Risk Filters

**Files:**
- Create: `engine/short_brain.py`
- Create: `engine/tests/test_short_brain.py`

- [ ] **Step 1: Write failing tests**

```python
# engine/tests/test_short_brain.py
import pytest
from unittest.mock import MagicMock, patch
import regime as regime_module
from regime import MarketRegime
from short_brain import ShortBrain, ShortSignal, SHORT_THRESHOLD


def setup_function():
    regime_module._regime_cache = {"value": None, "ts": 0.0}


def make_brain(client=None):
    return ShortBrain(client=client)


# ── Signal 1: Alt Weakness ─────────────────────────────────────────────────

def test_alt_falling_btc_stable_max_score():
    b = make_brain()
    assert b.score_alt_weakness(btc_change=0.2, alt_change=-1.5) == 25


def test_alt_falling_into_btc_strength():
    b = make_brain()
    assert b.score_alt_weakness(btc_change=1.0, alt_change=-0.8) == 20


def test_alt_not_following_btc_pump():
    b = make_brain()
    # BTC +2%, alt +0.3% = follow_ratio 0.15 < 0.30 = very weak
    assert b.score_alt_weakness(btc_change=2.0, alt_change=0.3) == 15


def test_alt_moderate_underperformance():
    b = make_brain()
    # BTC +2%, alt +0.8% = follow_ratio 0.40 < 0.60 = moderately weak
    assert b.score_alt_weakness(btc_change=2.0, alt_change=0.8) == 10


def test_alt_following_btc_no_weakness():
    b = make_brain()
    # BTC +2%, alt +1.8% = follow_ratio 0.90 = following fine
    assert b.score_alt_weakness(btc_change=2.0, alt_change=1.8) == 0


def test_both_flat_no_signal():
    b = make_brain()
    assert b.score_alt_weakness(btc_change=0.1, alt_change=0.1) == 0


# ── Signal 2: Funding Reset ────────────────────────────────────────────────

def test_funding_reset_detected():
    b = make_brain()
    # Was high, now near zero = squeeze done
    b.get_funding_history = MagicMock(return_value=[0.00015, 0.00012, 0.0001, 0.00008, 0.00002])
    assert b.score_funding_reset("ETHUSDT") == 25


def test_funding_partial_reset():
    b = make_brain()
    b.get_funding_history = MagicMock(return_value=[0.00008, 0.00007, 0.00006, 0.00005, 0.00005])
    assert b.score_funding_reset("ETHUSDT") == 15


def test_funding_still_high_no_reset():
    b = make_brain()
    b.get_funding_history = MagicMock(return_value=[0.00015, 0.00014, 0.00013, 0.00012, 0.00011])
    assert b.score_funding_reset("ETHUSDT") == 0


def test_funding_negative_returns_zero():
    b = make_brain()
    # Shorts already crowded — too late
    b.get_funding_history = MagicMock(return_value=[0.0001, 0.00005, 0.0, -0.00003, -0.0001])
    assert b.score_funding_reset("ETHUSDT") == 0


def test_funding_no_history_returns_zero():
    b = make_brain()
    b.get_funding_history = MagicMock(return_value=[])
    assert b.score_funding_reset("ETHUSDT") == 0


def test_funding_no_client_returns_empty_history():
    b = make_brain(client=None)
    assert b.get_funding_history("ETHUSDT") == []


# ── Signal 3: Volume Exhaustion ───────────────────────────────────────────

def _make_klines(closes, volumes):
    """Helper: build minimal klines list [ [*ignore*, *ignore*, *ignore*, *ignore*, close, volume, ...] ]"""
    rows = []
    for c, v in zip(closes, volumes):
        rows.append([0, "0", "0", "0", str(c), str(v), 0, "0", 0, "0", "0", "0"])
    return rows


def test_volume_exhaustion_strong():
    b = make_brain()
    # Price near high, volumes declining 50% over 3 candles
    closes = [100.0] * 17 + [105.0, 104.8, 105.1]
    volumes = [1000.0] * 17 + [900.0, 600.0, 450.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 25


def test_volume_exhaustion_moderate():
    b = make_brain()
    closes = [100.0] * 17 + [105.0, 104.8, 105.1]
    volumes = [1000.0] * 17 + [900.0, 750.0, 700.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 15


def test_no_exhaustion_volume_not_declining():
    b = make_brain()
    closes = [100.0] * 17 + [105.0, 104.8, 105.1]
    volumes = [1000.0] * 17 + [900.0, 950.0, 1100.0]  # Volume rising
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 0


def test_no_exhaustion_price_not_near_high():
    b = make_brain()
    closes = [105.0] * 10 + [90.0] * 10   # Price dropped away from high
    volumes = [1000.0] * 17 + [900.0, 700.0, 500.0]
    b.get_klines = MagicMock(return_value=_make_klines(closes, volumes))
    assert b.score_volume_exhaustion("ETHUSDT") == 0


def test_volume_no_client_returns_zero():
    b = make_brain(client=None)
    assert b.score_volume_exhaustion("ETHUSDT") == 0


# ── Signal 4: Macro Bearish ───────────────────────────────────────────────

def test_macro_bearish_strong_dxy():
    b = make_brain()
    with patch("short_brain.yf.Ticker") as mock_yf:
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [25.0] * 10 + [25.4]})
        mock_yf.return_value.history.return_value = mock_hist
        # (25.4 - 25.0) / 25.0 * 100 = 1.6% > DXY_STRONG_THRESHOLD(1.5)
        assert b.score_macro_bearish() == 25


def test_macro_bearish_moderate_dxy():
    b = make_brain()
    with patch("short_brain.yf.Ticker") as mock_yf:
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [25.0] * 10 + [25.28]})
        mock_yf.return_value.history.return_value = mock_hist
        # 1.12% — between 1.0 and 1.5
        assert b.score_macro_bearish() == 15


def test_macro_bullish_dxy_falling():
    b = make_brain()
    with patch("short_brain.yf.Ticker") as mock_yf:
        import pandas as pd
        mock_hist = pd.DataFrame({"Close": [25.5] * 10 + [25.0]})
        mock_yf.return_value.history.return_value = mock_hist
        assert b.score_macro_bearish() == 0


# ── get_short_signal: risk filters ────────────────────────────────────────

def test_blocked_in_bull_regime():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BULL):
        sig = b.get_short_signal("ETHUSDT", btc_change=2.0, alt_change=-1.0, has_open_long=False)
    assert sig.should_short is False
    assert sig.blocked_reason is not None
    assert "BULL" in sig.blocked_reason


def test_blocked_by_open_long():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(return_value=[0.0001])
        sig = b.get_short_signal("ETHUSDT", btc_change=0.0, alt_change=-1.5, has_open_long=True)
    assert sig.should_short is False
    assert "LONG" in sig.blocked_reason


def test_blocked_by_negative_funding():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(return_value=[-0.0002])
        sig = b.get_short_signal("ETHUSDT", btc_change=0.0, alt_change=-1.5, has_open_long=False)
    assert sig.should_short is False
    assert "negative" in sig.blocked_reason.lower()


def test_should_short_above_threshold():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.BEAR):
        b.get_funding_history = MagicMock(return_value=[0.00015, 0.0001, 0.00005, 0.00003, 0.00001])
        b.get_klines = MagicMock(return_value=_make_klines(
            [100.0] * 17 + [105.0, 104.8, 105.1],
            [1000.0] * 17 + [900.0, 600.0, 450.0],
        ))
        with patch("short_brain.yf.Ticker") as mock_yf:
            import pandas as pd
            mock_yf.return_value.history.return_value = pd.DataFrame(
                {"Close": [25.0] * 10 + [25.4]}
            )
            sig = b.get_short_signal(
                "ETHUSDT", btc_change=0.2, alt_change=-1.5, has_open_long=False
            )
    assert sig.score >= SHORT_THRESHOLD
    assert sig.should_short is True
    assert sig.regime == MarketRegime.BEAR


def test_signal_scores_populated_in_result():
    b = make_brain()
    with patch.object(b._regime, "detect", return_value=MarketRegime.SIDEWAYS):
        b.get_funding_history = MagicMock(return_value=[0.0])
        b.get_klines = MagicMock(return_value=[])
        with patch("short_brain.yf.Ticker") as mock_yf:
            import pandas as pd
            mock_yf.return_value.history.return_value = pd.DataFrame(
                {"Close": [25.0] * 10 + [25.0]}
            )
            sig = b.get_short_signal(
                "ETHUSDT", btc_change=0.2, alt_change=-1.5, has_open_long=False
            )
    assert "alt_weakness" in sig.signal_scores
    assert "funding_reset" in sig.signal_scores
    assert "volume_exhaustion" in sig.signal_scores
    assert "macro_bearish" in sig.signal_scores
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd engine/tests && python -m pytest test_short_brain.py -v
```
Expected: `ImportError: No module named 'short_brain'`

- [ ] **Step 3: Implement short_brain.py**

```python
# engine/short_brain.py
import logging
import yfinance as yf
from dataclasses import dataclass, field
from regime import RegimeDetector, MarketRegime

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

log = logging.getLogger(__name__)

ALT_WEAKNESS_STRONG = 0.3    # Alt follows BTC < 30% = very weak
ALT_WEAKNESS_MODERATE = 0.6  # Alt follows BTC < 60% = moderately weak

FUNDING_HIGH_THRESHOLD = 0.0001    # 0.01%/8h = crowded longs
FUNDING_RESET_THRESHOLD = 0.00003  # 0.003%/8h = near neutral

VOLUME_LOOKBACK = 3          # Consecutive declining candles required
PRICE_NEAR_HIGH_PCT = 0.02   # Within 2% of recent 10-bar high

DXY_BEARISH_THRESHOLD = 1.0  # UUP 10d > 1% = crypto headwind
DXY_STRONG_THRESHOLD = 1.5   # UUP 10d > 1.5% = strong headwind

SHORT_THRESHOLD = 65
SHORT_MAX_SCORE = 100


@dataclass
class ShortSignal:
    score: int
    should_short: bool
    regime: str
    reasons: list[str] = field(default_factory=list)
    blocked_reason: str | None = None
    signal_scores: dict = field(default_factory=dict)


class ShortBrain:
    def __init__(self, client=None):
        self.client = client
        self._regime = RegimeDetector(client=client)

    # ── Signal 1: Alt Relative Weakness (max 25) ──────────────────────────────

    def score_alt_weakness(self, btc_change: float, alt_change: float) -> int:
        """Alt weak vs BTC = capital rotating into BTC = good short setup."""
        if alt_change < -1.0 and btc_change >= -0.5:
            return 25
        if alt_change < -0.5 and btc_change >= 0:
            return 20
        if btc_change > 0.5:
            follow_ratio = alt_change / btc_change
            if follow_ratio < ALT_WEAKNESS_STRONG:
                return 15
            if follow_ratio < ALT_WEAKNESS_MODERATE:
                return 10
        if alt_change < -0.5 and btc_change < -0.5:
            if alt_change < btc_change * 1.2:
                return 10
        return 0

    # ── Signal 2: Funding Rate Reset (max 25) ─────────────────────────────────

    def get_funding_history(self, symbol: str, limit: int = 5) -> list[float]:
        """Last N funding rates. Returns [] when Binance unreachable."""
        if not self.client:
            return []
        try:
            data = self.client.futures_funding_rate(symbol=symbol, limit=limit)
            return [float(d["fundingRate"]) for d in data]
        except Exception as e:
            log.debug("Funding history failed for %s: %s", symbol, e)
            return []

    def score_funding_reset(self, symbol: str) -> int:
        """
        Funding was high (crowded longs), now neutral = squeeze done.
        Entry NOW is safer than when funding was high.
        Returns 0 when funding negative (shorts already crowded — too late).
        """
        rates = self.get_funding_history(symbol, limit=5)
        if len(rates) < 2:
            return 0
        current = rates[-1]
        prev_max = max(rates[:-1])
        if current < 0:
            return 0
        if prev_max >= FUNDING_HIGH_THRESHOLD and current <= FUNDING_RESET_THRESHOLD:
            return 25
        if prev_max >= FUNDING_HIGH_THRESHOLD * 0.7 and current <= FUNDING_RESET_THRESHOLD * 2:
            return 15
        return 0

    # ── Signal 3: Volume Exhaustion (max 25) ──────────────────────────────────

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 20) -> list:
        """Fetch 1h klines. Returns [] on failure."""
        if not self.client:
            return []
        try:
            return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        except Exception as e:
            log.debug("Klines failed for %s: %s", symbol, e)
            return []

    def score_volume_exhaustion(self, symbol: str) -> int:
        """
        Price near 10-bar high but volume declining 3 consecutive candles.
        Buyers drying up = distribution pattern.
        """
        klines = self.get_klines(symbol, interval="1h", limit=20)
        if len(klines) < 10:
            return 0
        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]
        recent_high = max(closes[-10:])
        current_close = closes[-1]
        if current_close < recent_high * (1 - PRICE_NEAR_HIGH_PCT):
            return 0
        recent_vols = volumes[-VOLUME_LOOKBACK:]
        vol_declining = all(
            recent_vols[i] > recent_vols[i + 1]
            for i in range(len(recent_vols) - 1)
        )
        if not vol_declining:
            return 0
        vol_drop_pct = (
            (recent_vols[0] - recent_vols[-1]) / recent_vols[0] * 100
            if recent_vols[0] > 0 else 0
        )
        if vol_drop_pct >= 40:
            return 25
        if vol_drop_pct >= 20:
            return 15
        return 8

    # ── Signal 4: Macro Bearish (max 25) ──────────────────────────────────────

    def score_macro_bearish(self) -> int:
        """UUP 10-day trend rising = strong dollar = crypto headwind."""
        try:
            hist = yf.Ticker("UUP").history(period="15d")
            if len(hist) < 10:
                return 0
            prev = float(hist["Close"].iloc[-10])
            curr = float(hist["Close"].iloc[-1])
            dxy_10d = (curr - prev) / prev * 100 if prev != 0 else 0.0
        except Exception:
            return 0
        if dxy_10d >= DXY_STRONG_THRESHOLD:
            return 25
        if dxy_10d >= DXY_BEARISH_THRESHOLD:
            return 15
        if dxy_10d >= 0.5:
            return 8
        return 0

    # ── Main entry point ───────────────────────────────────────────────────────

    def get_short_signal(
        self,
        pair: str,
        btc_change: float,
        alt_change: float,
        has_open_long: bool,
    ) -> ShortSignal:
        """
        Score short setup and apply hard risk filters.
        Regime gate → open long gate → negative funding gate → scoring.
        """
        regime = self._regime.detect()

        if regime == MarketRegime.BULL:
            return ShortSignal(
                score=0, should_short=False, regime=regime,
                blocked_reason="BULL regime — SHORT disabled",
            )

        if has_open_long:
            return ShortSignal(
                score=0, should_short=False, regime=regime,
                blocked_reason=f"Open LONG on {pair} — no opposing SHORT",
            )

        rates = self.get_funding_history(pair, limit=1)
        current_funding = rates[0] if rates else 0.0
        if current_funding < -0.00005:
            return ShortSignal(
                score=0, should_short=False, regime=regime,
                blocked_reason="Funding negative — shorts already crowded",
            )

        s1 = self.score_alt_weakness(btc_change, alt_change)
        s2 = self.score_funding_reset(pair)
        s3 = self.score_volume_exhaustion(pair)
        s4 = self.score_macro_bearish()
        total = min(SHORT_MAX_SCORE, s1 + s2 + s3 + s4)

        reasons = []
        if s1 > 0:
            reasons.append(f"alt_weakness: {s1}/25")
        if s2 > 0:
            reasons.append(f"funding_reset: {s2}/25")
        if s3 > 0:
            reasons.append(f"volume_exhaustion: {s3}/25")
        if s4 > 0:
            reasons.append(f"macro_bearish: {s4}/25")

        log.info("[%s] SHORT score=%d/100 regime=%s should_short=%s",
                 pair, total, regime, total >= SHORT_THRESHOLD)

        return ShortSignal(
            score=total,
            should_short=total >= SHORT_THRESHOLD,
            regime=regime,
            reasons=reasons,
            signal_scores={
                "alt_weakness": s1,
                "funding_reset": s2,
                "volume_exhaustion": s3,
                "macro_bearish": s4,
            },
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd engine/tests && python -m pytest test_short_brain.py -v
```
Expected: `18 passed`

- [ ] **Step 5: Commit**

```bash
git add engine/short_brain.py engine/tests/test_short_brain.py
git commit -m "feat(short): add ShortBrain with 4 signals + risk filters"
```

---

## Task 3: llm_advisor.py — analyze_short()

**Files:**
- Modify: `engine/llm_advisor.py` (add after line 44, and methods after line 149)
- Modify: `engine/tests/test_llm_advisor.py` (add 4 tests at end)

- [ ] **Step 1: Read the existing test file to find where to append**

```bash
tail -20 engine/tests/test_llm_advisor.py
```

- [ ] **Step 2: Write failing tests — append to test_llm_advisor.py**

```python
# Append to engine/tests/test_llm_advisor.py

# ── analyze_short ──────────────────────────────────────────────────────────

def test_analyze_short_both_agree_short():
    advisor = LlmAdvisor()
    result = advisor.analyze_short_with_mock(
        symbol="ETHUSDT",
        short_score=72,
        regime="BEAR",
        signal_breakdown={"alt_weakness": 25, "funding_reset": 25, "volume_exhaustion": 15, "macro_bearish": 8},
        btc_change=0.2,
        alt_change=-1.8,
        reasons=["alt_weakness: 25/25", "funding_reset: 25/25"],
        mock_claude={"signal": "SHORT", "confidence": "HIGH", "key_reason": "clear dist", "risk_flag": None},
        mock_deepseek={"signal": "SHORT", "confidence": "HIGH", "key_reason": "confirmed", "risk_flag": None},
    )
    assert result["final_signal"] == "SHORT"
    assert result["agreement"] is True
    assert result["disagreement_skipped"] is False


def test_analyze_short_disagreement_skips():
    advisor = LlmAdvisor()
    result = advisor.analyze_short_with_mock(
        symbol="ETHUSDT",
        short_score=68,
        regime="SIDEWAYS",
        signal_breakdown={"alt_weakness": 20, "funding_reset": 25, "volume_exhaustion": 0, "macro_bearish": 8},
        btc_change=0.5,
        alt_change=-0.8,
        reasons=["alt_weakness: 20/25"],
        mock_claude={"signal": "SHORT", "confidence": "MEDIUM", "key_reason": "ok", "risk_flag": None},
        mock_deepseek={"signal": "SKIP", "confidence": "LOW", "key_reason": "risky", "risk_flag": "low volume"},
    )
    assert result["final_signal"] == "SKIP"
    assert result["disagreement_skipped"] is True


def test_analyze_short_both_skip():
    advisor = LlmAdvisor()
    result = advisor.analyze_short_with_mock(
        symbol="BNBUSDT",
        short_score=50,
        regime="SIDEWAYS",
        signal_breakdown={"alt_weakness": 15, "funding_reset": 0, "volume_exhaustion": 15, "macro_bearish": 0},
        btc_change=1.0,
        alt_change=0.4,
        reasons=[],
        mock_claude={"signal": "SKIP", "confidence": "LOW", "key_reason": "weak", "risk_flag": None},
        mock_deepseek={"signal": "SKIP", "confidence": "LOW", "key_reason": "weak", "risk_flag": None},
    )
    assert result["final_signal"] == "SKIP"
    assert result["agreement"] is True
    assert result["disagreement_skipped"] is False


def test_analyze_short_returns_expected_keys():
    advisor = LlmAdvisor()
    result = advisor.analyze_short_with_mock(
        symbol="SOLUSDT",
        short_score=65,
        regime="BEAR",
        signal_breakdown={"alt_weakness": 25, "funding_reset": 25, "volume_exhaustion": 0, "macro_bearish": 15},
        btc_change=-0.3,
        alt_change=-1.2,
        reasons=["alt_weakness: 25/25"],
        mock_claude={"signal": "SHORT", "confidence": "HIGH", "key_reason": "r", "risk_flag": None},
        mock_deepseek={"signal": "SHORT", "confidence": "HIGH", "key_reason": "r", "risk_flag": None},
    )
    assert set(result.keys()) == {"final_signal", "agreement", "disagreement_skipped", "claude", "deepseek"}
```

- [ ] **Step 3: Run new tests to verify they fail**

```bash
cd engine/tests && python -m pytest test_llm_advisor.py -k "short" -v
```
Expected: `AttributeError: 'LlmAdvisor' object has no attribute 'analyze_short_with_mock'`

- [ ] **Step 4: Add _build_short_prompt and methods to llm_advisor.py**

Add after line 44 (after `_build_analysis_prompt` function):

```python
def _build_short_prompt(
    symbol: str,
    short_score: int,
    regime: str,
    signal_breakdown: dict,
    btc_change: float,
    alt_change: float,
    reasons: list[str],
) -> str:
    return f"""You are a crypto trading risk analyst evaluating a SHORT futures position.

Symbol: {symbol}
Market Regime: {regime}
Short Score: {short_score}/100 (threshold: 65)
BTC 24h Change: {btc_change:+.2f}%
Alt 24h Change: {alt_change:+.2f}%

Signal Breakdown (each max 25):
{json.dumps(signal_breakdown, indent=2)}

Bearish Evidence:
{chr(10).join(f"- {r}" for r in reasons)}

Should we SHORT {symbol} with 1x leverage, 5% equity, SL 5% above entry?

Respond in JSON only:
{{
  "signal": "SHORT" | "SKIP",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "key_reason": "<one sentence>",
  "risk_flag": "<main risk or null>"
}}"""
```

Add after `analyze_with_mock` method (after line 178):

```python
    def _parse_short_signal(self, response: dict) -> str:
        """Extract normalized SHORT signal from LLM response."""
        raw = response.get("signal", "SKIP").upper()
        return "SHORT" if raw == "SHORT" else "SKIP"

    def analyze_short(
        self,
        symbol: str,
        short_score: int,
        regime: str,
        signal_breakdown: dict,
        btc_change: float,
        alt_change: float,
        reasons: list[str],
    ) -> dict:
        """
        Dual LLM analysis for SHORT signals.
        Both Claude and DeepSeek must output "SHORT" — disagreement skips.
        Same Disagreement Protocol as analyze().
        """
        prompt = _build_short_prompt(
            symbol, short_score, regime, signal_breakdown, btc_change, alt_change, reasons
        )
        claude_result = self._query_claude(prompt)
        deepseek_result = self._query_deepseek(prompt)

        claude_signal = self._parse_short_signal(claude_result)
        deepseek_signal = self._parse_short_signal(deepseek_result)

        agreement = claude_signal == deepseek_signal
        disagreement_skipped = not agreement
        final_signal = "SKIP" if disagreement_skipped else claude_signal

        return {
            "final_signal": final_signal,
            "agreement": agreement,
            "disagreement_skipped": disagreement_skipped,
            "claude": claude_result,
            "deepseek": deepseek_result,
        }

    def analyze_short_with_mock(
        self,
        symbol: str,
        short_score: int,
        regime: str,
        signal_breakdown: dict,
        btc_change: float,
        alt_change: float,
        reasons: list[str],
        mock_claude: dict = None,
        mock_deepseek: dict = None,
    ) -> dict:
        """Test-friendly version for SHORT analysis with pre-canned responses."""
        claude_result = mock_claude or {
            "signal": "SKIP", "confidence": "LOW", "key_reason": "mock", "risk_flag": None
        }
        deepseek_result = mock_deepseek or {
            "signal": "SKIP", "confidence": "LOW", "key_reason": "mock", "risk_flag": None
        }
        claude_signal = self._parse_short_signal(claude_result)
        deepseek_signal = self._parse_short_signal(deepseek_result)

        agreement = claude_signal == deepseek_signal
        disagreement_skipped = not agreement
        final_signal = "SKIP" if disagreement_skipped else claude_signal

        return {
            "final_signal": final_signal,
            "agreement": agreement,
            "disagreement_skipped": disagreement_skipped,
            "claude": claude_result,
            "deepseek": deepseek_result,
        }
```

- [ ] **Step 5: Run all llm_advisor tests to verify they pass**

```bash
cd engine/tests && python -m pytest test_llm_advisor.py -v
```
Expected: all pass (existing + 4 new)

- [ ] **Step 6: Commit**

```bash
git add engine/llm_advisor.py engine/tests/test_llm_advisor.py
git commit -m "feat(short): add analyze_short() to LlmAdvisor — same disagree protocol as LONG"
```

---

## Task 4: main.py — Wire Everything Together

**Files:**
- Modify: `engine/main.py`

Changes: (1) import ShortBrain, (2) add to services dict, (3) replace `is_bearish_short` with `short_brain.get_short_signal()`, (4) add LLM SHORT gate, (5) fix size + leverage constants.

- [ ] **Step 1: Update imports at top of main.py**

Find the line `from btc_lead import BtcLeadSignal` and add after it:

```python
from short_brain import ShortBrain
```

- [ ] **Step 2: Update constants — change MAX_SHORT_POSITION_PCT**

Find:
```python
MAX_SHORT_POSITION_PCT = 0.25
```
Replace with:
```python
MAX_SHORT_POSITION_PCT = 0.05   # 5% equity max — SHORT is secondary to LONG
```

- [ ] **Step 3: Add ShortBrain to bootstrap services dict**

Find:
```python
        "btc_lead": BtcLeadSignal(client=client),
```
Add after it:
```python
        "short_brain": ShortBrain(client=client),
```

- [ ] **Step 4: Replace is_bearish_short in run_signal_pipeline**

Find and replace this entire block (lines 266–278 approximately):
```python
    # ── Xác định hướng giao dịch ─────────────────────────────────────────
    # SHORT: score thấp + macro bearish + BTC dẫn xuống + TA bearish
    is_bearish_short = (
        conviction.total_score <= SHORT_CONVICTION_THRESHOLD
        and btc_lead_score <= 3    # BTC đang dẫn xuống (max 20)
        and macro_score <= 5       # Macro bearish: DXY tăng (max 20)
        and ta_score <= 3          # TA bearish: RSI cao, MACD giảm (max 10)
    )

    if not conviction.should_trade and not is_bearish_short:
        return {"pair": pair, "action": conviction.action, "score": conviction.total_score}

    trade_side = "LONG" if conviction.should_trade else "SHORT"
```

With:
```python
    # ── SHORT brain evaluation ────────────────────────────────────────────
    short_brain: ShortBrain = services["short_brain"]
    has_open_long = (
        session.query(Position).filter_by(pair=pair, side="LONG").count() > 0
    )
    short_signal = short_brain.get_short_signal(
        pair=pair,
        btc_change=btc_change,
        alt_change=price_change,
        has_open_long=has_open_long,
    )

    if not conviction.should_trade and not short_signal.should_short:
        return {"pair": pair, "action": conviction.action, "score": conviction.total_score}

    trade_side = "LONG" if conviction.should_trade else "SHORT"
```

- [ ] **Step 5: Replace LLM gate to cover both LONG and SHORT**

Find:
```python
    # ── LLM Dual Analysis (chỉ cho LONG — SHORT dùng rule-based) ─────────
    if trade_side == "LONG":
        llm_result = llm.analyze(
            symbol=pair,
            conviction_score=conviction.total_score,
            layer_scores=layer_scores.as_dict(),
            price_change_pct=price_change,
            reasons=conviction.reasons,
        )
        if llm_result["disagreement_skipped"]:
            log.info("[%s] SKIP — LLM disagreement", pair)
            return {"pair": pair, "action": "SKIP_LLM_DISAGREEMENT", "score": conviction.total_score}
```

Replace with:
```python
    # ── LLM Dual Analysis — cả LONG lẫn SHORT đều cần confirm ────────────
    if trade_side == "LONG":
        llm_result = llm.analyze(
            symbol=pair,
            conviction_score=conviction.total_score,
            layer_scores=layer_scores.as_dict(),
            price_change_pct=price_change,
            reasons=conviction.reasons,
        )
        if llm_result["disagreement_skipped"]:
            log.info("[%s] SKIP — LLM disagreement (LONG)", pair)
            return {"pair": pair, "action": "SKIP_LLM_DISAGREEMENT", "score": conviction.total_score}
    else:
        llm_result = llm.analyze_short(
            symbol=pair,
            short_score=short_signal.score,
            regime=short_signal.regime,
            signal_breakdown=short_signal.signal_scores,
            btc_change=btc_change,
            alt_change=price_change,
            reasons=short_signal.reasons,
        )
        if llm_result["disagreement_skipped"] or llm_result["final_signal"] != "SHORT":
            log.info("[%s] SKIP — LLM disagreement (SHORT)", pair)
            return {"pair": pair, "action": "SKIP_LLM_DISAGREEMENT_SHORT", "score": short_signal.score}
```

- [ ] **Step 6: Fix SHORT execution — size bug + leverage**

Find in the FUTURES SHORT section:
```python
        size = max(10.0, min(equity * MAX_SHORT_POSITION_PCT, equity * MAX_SHORT_POSITION_PCT))
```
Replace with:
```python
        size = max(10.0, equity * MAX_SHORT_POSITION_PCT)
```

Find:
```python
        result = services["executor"].short_futures(pair, qty, leverage=2)
```
Replace with:
```python
        result = services["executor"].short_futures(pair, qty, leverage=1)
```

- [ ] **Step 7: Run the engine tests to confirm nothing broke**

```bash
cd engine/tests && python -m pytest . -v --tb=short
```
Expected: all existing tests pass

- [ ] **Step 8: Commit**

```bash
git add engine/main.py
git commit -m "feat(short): wire ShortBrain + LLM dual-confirm into main pipeline; fix size bug; leverage 1x"
```

---

## Task 5: verify.py — Update Checks

**Files:**
- Modify: `verify.py`

- [ ] **Step 1: Add SHORT brain checks to verify.py**

Find the `── Tính năng ───` section at the bottom of verify.py:
```python
print("\n── Tính năng ───────────────────────────────────────────")
check("SHORT_CONVICTION_THRESHOLD có mặt",
      "engine/main.py", must_have=r"SHORT_CONVICTION_THRESHOLD")
```

Replace with:
```python
print("\n── Tính năng ───────────────────────────────────────────")
check("SHORT_CONVICTION_THRESHOLD có mặt",
      "engine/main.py", must_have=r"SHORT_CONVICTION_THRESHOLD")
check("regime.py tồn tại với MarketRegime",
      "engine/regime.py", must_have=r"class MarketRegime")
check("short_brain.py tồn tại với ShortBrain",
      "engine/short_brain.py", must_have=r"class ShortBrain")
check("ShortBrain được import trong main.py",
      "engine/main.py", must_have=r"from short_brain import ShortBrain")
check("LLM SHORT gate có trong main.py",
      "engine/main.py", must_have=r"analyze_short")
check("SHORT leverage là 1x",
      "engine/main.py", must_have=r"leverage=1")
check("MAX_SHORT_POSITION_PCT = 0.05",
      "engine/main.py", must_have=r"MAX_SHORT_POSITION_PCT = 0.05")
check("analyze_short method có trong llm_advisor",
      "engine/llm_advisor.py", must_have=r"def analyze_short")
check("Funding reset signal có trong short_brain",
      "engine/short_brain.py", must_have=r"def score_funding_reset")
check("Volume exhaustion signal có trong short_brain",
      "engine/short_brain.py", must_have=r"def score_volume_exhaustion")
```

- [ ] **Step 2: Run verify.py to confirm all pass**

```bash
python verify.py
```
Expected: `36/36 kiểm tra đạt — Tất cả OK`

- [ ] **Step 3: Run full test suite one final time**

```bash
cd engine/tests && python -m pytest . -v --tb=short
```
Expected: all tests pass

- [ ] **Step 4: Final commit**

```bash
git add verify.py
git commit -m "feat(short): update verify.py with 9 new SHORT brain checks (36 total)"
```

---

## Self-Review

**Spec coverage:**
- ✅ regime.py — BULL/BEAR/SIDEWAYS detection
- ✅ short_brain.py — 4 signals (alt weakness, funding reset, volume exhaustion, macro bearish)
- ✅ Risk filters (regime gate, open long gate, negative funding gate)
- ✅ LLM dual-confirm for SHORT (analyze_short + disagreement protocol)
- ✅ SHORT size 5% equity, leverage 1x
- ✅ main.py integration replacing is_bearish_short
- ✅ verify.py updated

**Placeholder scan:** No TBDs, no "similar to Task N", all code complete.

**Type consistency:**
- `ShortSignal.signal_scores: dict` used in Task 2 and passed to `analyze_short(signal_breakdown=short_signal.signal_scores)` in Task 4 ✓
- `ShortBrain.get_short_signal()` signature consistent across tasks ✓
- `LlmAdvisor.analyze_short()` parameters match `_build_short_prompt()` ✓
