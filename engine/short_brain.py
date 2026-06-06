"""
ShortBrain — dedicated short-selling signal engine.

Game-theory principle: avoid the signals that market-makers already know retail
uses (raw funding HIGH, RSI overbought, etc.). Instead target the aftermath:
  • funding RESET      — squeeze already happened, now funding normalised
  • volume EXHAUSTION  — buyers running out of steam at resistance
  • alt RELATIVE WEAKNESS — smart money rotating out while BTC holds
  • macro DXY TREND    — structural headwind that overrides intraday noise
  • trend BREAKDOWN    — dead cat bounce in downtrend (weak recovery = continuation)

Five signals, 25 pts each → 125 max.  Threshold ≥ 65 to fire.
Hard risk filters applied first (regime, open-long, very-negative-funding).
"""

import logging
import yfinance as yf
from dataclasses import dataclass, field
from typing import Optional

from regime import RegimeDetector, MarketRegime

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
log = logging.getLogger(__name__)

# ── Thresholds ────────────────────────────────────────────────────────────────

SHORT_THRESHOLD = 65
SHORT_MAX_SCORE = 125   # 5 signals × 25 pts

# score_alt_weakness
_BTC_STABLE_THRESHOLD = 0.5       # |btc_change| < 0.5% = BTC stable
_ALT_FOLLOW_MIN_VERY_WEAK = 0.30  # follow_ratio < 30% = very weak
_ALT_FOLLOW_MIN_MODERATE = 0.60   # follow_ratio < 60% = moderately weak
_BTC_MOVE_MIN_FOR_RATIO = 1.5     # Need BTC ≥1.5% move to compute follow ratio

# score_funding_reset
_FUNDING_ELEVATED_MIN = 0.00005   # 5 bps — funding was elevated
_FUNDING_STRONG_DECLINE = 0.70    # ≥70% decline from peak = strong reset
_FUNDING_PARTIAL_DECLINE = 0.30   # ≥30% decline from peak = partial reset

# score_volume_exhaustion
_NEAR_HIGH_THRESHOLD = 0.97       # current price ≥ 97% of period high
_VOL_STRONG_DECLINE = 0.55        # recent 3-candle avg ≤ 55% of baseline = strong exhaustion
_VOL_MODERATE_DECLINE = 0.85      # recent 3-candle avg ≤ 85% of baseline = moderate exhaustion
_KLINES_NEEDED = 20               # Need all 20 candles to establish a reliable baseline

# score_macro_bearish (UUP ETF as DXY proxy)
_DXY_STRONG_THRESHOLD = 1.5       # UUP ≥1.5% change = strong crypto headwind
_DXY_MODERATE_THRESHOLD = 1.0     # UUP ≥1.0% change = moderate headwind

# score_trend_breakdown (dead cat bounce in downtrend)
_TREND_DECLINE_MODERATE = 0.05    # price ≥5% below 20-period high = downtrend confirmed
_TREND_DECLINE_STRONG   = 0.10    # price ≥10% below high = strong downtrend
_BOUNCE_MIN             = 0.005   # need ≥0.5% bounce from recent low to qualify
_BOUNCE_MAX             = 0.05    # bounce >5% = might be real recovery, skip
_TREND_VOL_WEAK         = 0.80    # bounce volume < 80% of baseline = weak (no conviction)

# hard filter: very negative funding = strong short squeeze risk
# Slightly negative funding (-0.01%) is normal in bear market → allow SHORT
# Very negative (< -0.02%) = longs aggressively being paid → block
_FUNDING_VERY_NEGATIVE = -0.0002  # -0.02% per 8h = strong squeeze risk threshold


# ── Data classes ─────────────────────────────────────────────────────────────

@dataclass
class ShortSignal:
    score: int
    should_short: bool
    regime: str
    reasons: list
    blocked_reason: Optional[str]
    signal_scores: dict


# ── ShortBrain ────────────────────────────────────────────────────────────────

class ShortBrain:
    def __init__(self, client=None):
        self.client = client
        self._regime = RegimeDetector(client=client)

    # ── Data helpers ──────────────────────────────────────────────────────────

    def get_funding_history(self, symbol: str) -> list:
        """
        Return a list of recent funding rates for *symbol*, oldest first.
        Returns [] when no client is available or on any error.
        """
        if not self.client:
            return []
        try:
            records = self.client.futures_funding_rate(symbol=symbol, limit=5)
            return [float(r["fundingRate"]) for r in records]
        except Exception as e:
            log.debug("get_funding_history failed for %s: %s", symbol, e)
            return []

    def get_klines(self, symbol: str, interval: str = "1h", limit: int = 20) -> list:
        """Return klines list; each row is [open_time, open, high, low, close, volume, ...]."""
        if not self.client:
            return []
        try:
            return self.client.get_klines(symbol=symbol, interval=interval, limit=limit)
        except Exception as e:
            log.debug("get_klines failed for %s: %s", symbol, e)
            return []

    # ── Signal 1: Alt Relative Weakness ───────────────────────────────────────

    def score_alt_weakness(self, btc_change: float, alt_change: float) -> int:
        """
        Alt failing to follow BTC = capital rotating out of alts.
        Scored by severity of underperformance.
        Max 25 pts.
        """
        # Case 1: BTC is stable (< ±0.5%) but alt is falling — pure alt weakness
        if abs(btc_change) < _BTC_STABLE_THRESHOLD and alt_change < 0:
            return 25

        # Case 2: BTC is rising but alt is falling — alt very weak relative to BTC
        if btc_change > 0 and alt_change < 0:
            return 20

        # Cases 3-4: Both positive, but alt following weakly
        if btc_change >= _BTC_MOVE_MIN_FOR_RATIO:
            follow_ratio = alt_change / btc_change
            if follow_ratio < _ALT_FOLLOW_MIN_VERY_WEAK:
                return 15
            if follow_ratio < _ALT_FOLLOW_MIN_MODERATE:
                return 10

        return 0

    # ── Signal 2: Funding Rate Reset ──────────────────────────────────────────

    def score_funding_reset(self, symbol: str) -> int:
        """
        Funding was elevated (longs overpaying) and has now reset toward zero.
        This means the squeeze already happened — safe to short again.
        Negative funding = market already bearish, no edge → 0.
        Max 25 pts.
        """
        history = self.get_funding_history(symbol)
        if not history:
            return 0

        # Negative funding = market pricing in a drop; no short edge here
        if any(f < 0 for f in history):
            return 0

        oldest = history[0]
        latest = history[-1]

        # Funding was never elevated — no reset to measure
        if oldest < _FUNDING_ELEVATED_MIN:
            return 0

        decline_ratio = (oldest - latest) / oldest if oldest > 0 else 0.0

        if decline_ratio >= _FUNDING_STRONG_DECLINE:
            return 25
        if decline_ratio >= _FUNDING_PARTIAL_DECLINE:
            return 15
        return 0

    # ── Signal 3: Volume Exhaustion at Resistance ──────────────────────────────

    def score_volume_exhaustion(self, symbol: str) -> int:
        """
        Price near recent high but the last 3 candles average well below the
        20-period baseline average — buyers running out of steam at resistance.

        Compares recent 3-candle avg vs the preceding 17-candle baseline avg.
        This avoids false signals from single-candle spikes (v3/v1 approach was
        too noisy when one of the 3 candles happened to be unusually large).

        Max 25 pts.
        """
        klines = self.get_klines(symbol)
        if len(klines) < _KLINES_NEEDED:
            return 0

        closes = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        # Price must be near the period high
        period_high = max(closes)
        current_price = closes[-1]
        if current_price < period_high * _NEAR_HIGH_THRESHOLD:
            return 0

        # Recent 3-candle average vs 20-period baseline average
        recent_vols   = volumes[-3:]    # last 3 candles  (most recent)
        baseline_vols = volumes[:-3]    # first 17 candles (baseline)

        recent_avg   = sum(recent_vols) / len(recent_vols)
        baseline_avg = sum(baseline_vols) / len(baseline_vols)

        if baseline_avg <= 0 or recent_avg >= baseline_avg:
            return 0  # Volume not declining relative to baseline

        decline_ratio = recent_avg / baseline_avg

        if decline_ratio <= _VOL_STRONG_DECLINE:    # recent ≤ 55% of baseline
            return 25
        if decline_ratio <= _VOL_MODERATE_DECLINE:  # recent ≤ 85% of baseline
            return 15
        return 0

    # ── Signal 4: Macro Bearish (DXY trending up) ────────────────────────────

    def score_macro_bearish(self) -> int:
        """
        DXY rising = strong dollar = structural headwind for crypto.
        Measures change over ~15-day window.
        Fallback chain: UUP → DX-Y.NYB → 0 pts.
        Max 25 pts.
        """
        for ticker in ("UUP", "DX-Y.NYB"):
            try:
                hist = yf.Ticker(ticker).history(period="15d")
                if len(hist) < 10:
                    continue
                prev = float(hist["Close"].iloc[0])
                curr = float(hist["Close"].iloc[-1])
                change_pct = (curr - prev) / prev * 100 if prev != 0 else 0.0

                if change_pct >= _DXY_STRONG_THRESHOLD:
                    return 25
                if change_pct >= _DXY_MODERATE_THRESHOLD:
                    return 15
                return 0
            except Exception as e:
                log.debug("score_macro_bearish %s failed: %s", ticker, e)

        log.warning("All DXY sources failed for macro_bearish — returning 0")
        return 0

    # ── Signal 5: Trend Breakdown (dead cat bounce in downtrend) ─────────────

    def score_trend_breakdown(self, symbol: str) -> int:
        """
        Phát hiện dead cat bounce trong downtrend để short continuation.
        Khác với volume_exhaustion (short tại đỉnh), signal này short khi
        giá đang ở ĐÁYSÂU nhưng bounce yếu → xu hướng giảm tiếp diễn.

        Điều kiện:
          1. Giá đang thấp hơn đỉnh 20-nến ≥5% (downtrend xác nhận)
          2. Có bounce nhẹ từ đáy gần nhất (0.5%–5%) — dead cat
          3. Volume bounce yếu hơn baseline (<80%) — không có conviction

        Max 25 pts.
        """
        klines = self.get_klines(symbol)
        if len(klines) < _KLINES_NEEDED:
            return 0

        closes  = [float(k[4]) for k in klines]
        volumes = [float(k[5]) for k in klines]

        period_high   = max(closes)
        current_price = closes[-1]

        # 1. Giá phải thấp hơn đỉnh đáng kể → downtrend confirmed
        decline_from_high = (period_high - current_price) / period_high if period_high > 0 else 0
        if decline_from_high < _TREND_DECLINE_MODERATE:
            return 0  # Giá còn gần đỉnh → đây là volume_exhaustion territory, không phải đây

        # 2. Phải có bounce từ đáy gần nhất (không phải đang free-fall)
        recent_low = min(closes[-7:-1]) if len(closes) >= 7 else min(closes[:-1])
        bounce_pct = (current_price - recent_low) / recent_low if recent_low > 0 else 0
        if bounce_pct < _BOUNCE_MIN:
            return 0  # Chưa có bounce = không có dead cat để short
        if bounce_pct > _BOUNCE_MAX:
            return 0  # Bounce > 5% = có thể là recovery thật, rủi ro cao

        # 3. Volume bounce yếu hơn baseline (không có conviction trong recovery)
        recent_vol_avg   = sum(volumes[-3:]) / 3
        baseline_vol_avg = sum(volumes[:-3]) / len(volumes[:-3]) if len(volumes) > 3 else 0
        if baseline_vol_avg <= 0 or recent_vol_avg >= baseline_vol_avg * _TREND_VOL_WEAK:
            return 0  # Volume mạnh = recovery có thể thật, bỏ qua

        # Score dựa trên mức độ downtrend
        if decline_from_high >= _TREND_DECLINE_STRONG:   # ≥10% below high
            return 25
        return 15  # 5–10% below high

    # ── Main entry point ──────────────────────────────────────────────────────

    def get_short_signal(
        self,
        symbol: str,
        btc_change: float,
        alt_change: float,
        has_open_long: bool,
    ) -> ShortSignal:
        """
        Evaluate all 4 signals and apply risk filters.
        Returns ShortSignal with should_short=True only when score ≥ SHORT_THRESHOLD
        and no hard filter blocks the trade.
        """
        regime = self._regime.detect()

        # ── Hard filter 1: Never short in a BULL market ────────────────────────
        if regime == MarketRegime.BULL:
            log.info("[ShortBrain] %s BLOCKED — BULL regime", symbol)
            return ShortSignal(
                score=0,
                should_short=False,
                regime=regime,
                reasons=[],
                blocked_reason=f"Blocked: BULL regime — shorting into uptrend is low-EV",
                signal_scores={},
            )

        # ── Hard filter 2: Don't short if LONG already open on same pair ───────
        if has_open_long:
            return ShortSignal(
                score=0,
                should_short=False,
                regime=regime,
                reasons=[],
                blocked_reason="Blocked: open LONG position on same pair",
                signal_scores={},
            )

        # ── Hard filter 3: Block only VERY negative funding ────────────────────
        # Slightly negative funding is normal in bear markets — don't block.
        # Only block when funding is very negative (< -0.02% per 8h) which signals
        # the market is already aggressively positioned short → squeeze risk high.
        funding_history = self.get_funding_history(symbol)
        if funding_history and funding_history[-1] < _FUNDING_VERY_NEGATIVE:
            return ShortSignal(
                score=0,
                should_short=False,
                regime=regime,
                reasons=[],
                blocked_reason=f"Blocked: funding very negative ({funding_history[-1]:.5f}) — high squeeze risk",
                signal_scores={},
            )

        # ── Score all 5 signals ────────────────────────────────────────────────
        s_alt   = self.score_alt_weakness(btc_change, alt_change)
        s_fund  = self.score_funding_reset(symbol)
        s_vol   = self.score_volume_exhaustion(symbol)
        s_macro = self.score_macro_bearish()
        s_trend = self.score_trend_breakdown(symbol)

        total = s_alt + s_fund + s_vol + s_macro + s_trend
        signal_scores = {
            "alt_weakness":      s_alt,
            "funding_reset":     s_fund,
            "volume_exhaustion": s_vol,
            "macro_bearish":     s_macro,
            "trend_breakdown":   s_trend,
        }

        reasons = []
        if s_alt   > 0: reasons.append(f"alt_weakness={s_alt}")
        if s_fund  > 0: reasons.append(f"funding_reset={s_fund}")
        if s_vol   > 0: reasons.append(f"volume_exhaustion={s_vol}")
        if s_macro > 0: reasons.append(f"macro_bearish={s_macro}")
        if s_trend > 0: reasons.append(f"trend_breakdown={s_trend}")

        sig = ShortSignal(
            score=total,
            should_short=total >= SHORT_THRESHOLD,
            regime=regime,
            reasons=reasons,
            blocked_reason=None,
            signal_scores=signal_scores,
        )
        log.info(
            "[ShortBrain] %s score=%d/125 regime=%s alt=%d fund=%d vol=%d macro=%d trend=%d %s",
            symbol, total, regime, s_alt, s_fund, s_vol, s_macro, s_trend,
            "→ SHORT" if sig.should_short else "→ SKIP",
        )
        return sig
