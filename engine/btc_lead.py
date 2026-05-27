import os
import time
import httpx

# BTC move thresholds to qualify as a lead signal
BTC_MOVE_STRONG = 2.0       # BTC > 2% in 1h = strong move
BTC_MOVE_MODERATE = 1.0     # BTC > 1% in 1h = moderate move
BTC_MOVE_WEAK = 0.3         # BTC > 0.3% = minor move (not a lead signal)

# Spot/futures volume ratio thresholds
# Ratio = spot_volume / (spot_volume + futures_volume)
# On Binance, futures volume is typically 4-5× spot (ratio ≈ 0.15-0.20 in normal market).
# "Real" and "suspect" thresholds are calibrated to actual Binance market structure.
SPOT_RATIO_REAL = 0.25      # Spot > 25% of total = unusually organic (above-average spot demand)
SPOT_RATIO_SUSPECT = 0.08   # Spot < 8% of total = extreme futures dominance, likely manipulation

# Altcoin correlation: if BTC pumps but alts don't follow, suspect fake
ALT_FOLLOW_MIN = 0.4        # Altcoin move should be at least 40% of BTC move

BTC_LEAD_MAX_SCORE = 20

COINGECKO_BTC_URL = "https://api.coingecko.com/api/v3/simple/price"

# Module-level cache: avoid calling CoinGecko on every scan (5 pairs × every 5 min)
_btc_change_cache: dict = {"value": None, "ts": 0.0}
_BTC_CHANGE_TTL = 300  # 5 minutes


class BtcLeadSignal:
    def __init__(self, client=None):
        self.client = client

    def score_btc_move(self, btc_change_pct: float, spot_futures_ratio: float) -> int:
        """
        BTC dẫn đầu = altcoin sẽ theo sau.
        Nhưng phải là spot-driven, không phải futures-driven (dễ bị reverse).
        """
        abs_move = abs(btc_change_pct)

        if abs_move < BTC_MOVE_WEAK:
            return 0    # Không đủ mạnh để trigger

        if spot_futures_ratio < SPOT_RATIO_SUSPECT:
            return 0    # Futures-driven: nguy hiểm, bỏ qua

        if abs_move >= BTC_MOVE_STRONG and spot_futures_ratio >= SPOT_RATIO_REAL:
            return 15   # Strong organic BTC move — high conviction

        if abs_move >= BTC_MOVE_MODERATE and spot_futures_ratio >= SPOT_RATIO_REAL:
            return 10   # Moderate organic move

        if abs_move >= BTC_MOVE_MODERATE and spot_futures_ratio >= SPOT_RATIO_SUSPECT:
            return 5    # Moderate but mixed spot/futures

        return 5        # Weak but real spot move

    def score_alt_correlation(self, btc_change_pct: float, alt_change_pct: float) -> int:
        """
        Altcoin phải follow BTC để xác nhận tín hiệu.
        Nếu BTC pump nhưng alt không follow → alt đang yếu relative to BTC.
        Nếu BTC pump + alt pump mạnh hơn → alt outperforming = very bullish.
        """
        if abs(btc_change_pct) < BTC_MOVE_WEAK:
            return 0    # BTC không move đủ để xét correlation

        # Tính ratio alt/btc move
        if btc_change_pct == 0:
            return 0

        follow_ratio = alt_change_pct / btc_change_pct

        if follow_ratio >= 1.5:
            return 5    # Alt outperforming BTC = very bullish
        if follow_ratio >= ALT_FOLLOW_MIN:
            return 3    # Alt following BTC = confirmed
        if follow_ratio < 0:
            return 0    # Alt diverging from BTC = suspicious
        return 1        # Alt lagging

    def total_score(
        self,
        btc_change_pct: float,
        spot_futures_ratio: float,
        alt_change_pct: float = 0.0
    ) -> int:
        btc_score = self.score_btc_move(btc_change_pct, spot_futures_ratio)

        # If BTC move rejected due to futures-driven pump, alt correlation is meaningless
        # (alts following a fake pump are also suspect)
        if btc_score == 0 and spot_futures_ratio < SPOT_RATIO_SUSPECT:
            return 0

        score = btc_score + self.score_alt_correlation(btc_change_pct, alt_change_pct)
        return min(BTC_LEAD_MAX_SCORE, score)

    def get_btc_change_pct(self) -> float:
        """
        BTC 24h price change %.
        Tries Binance first; falls back to CoinGecko (no API key) with a 5-min cache.
        This is used by main.py instead of a raw get_ticker call so geo-blocking
        on Binance spot does not permanently zero out the BTC Lead layer.
        """
        global _btc_change_cache
        now = time.time()
        if _btc_change_cache["value"] is not None and now - _btc_change_cache["ts"] < _BTC_CHANGE_TTL:
            return _btc_change_cache["value"]

        # ── Try Binance ──────────────────────────────────────────────────────
        if self.client:
            try:
                ticker = self.client.get_ticker(symbol="BTCUSDT")
                value = float(ticker.get("priceChangePercent", 0))
                if abs(value) > 0.01:   # sanity check — testnet sometimes returns 0
                    _btc_change_cache = {"value": value, "ts": now}
                    return value
            except Exception:
                pass

        # ── CoinGecko fallback (no API key required) ─────────────────────────
        try:
            resp = httpx.get(
                COINGECKO_BTC_URL,
                params={
                    "ids": "bitcoin",
                    "vs_currencies": "usd",
                    "include_24hr_change": "true",
                },
                timeout=6.0,
            )
            if resp.status_code == 200:
                value = float(resp.json().get("bitcoin", {}).get("usd_24h_change", 0))
                _btc_change_cache = {"value": value, "ts": now}
                return value
        except Exception:
            pass

        # Return last good value if available, else 0
        return _btc_change_cache["value"] if _btc_change_cache["value"] is not None else 0.0

    def get_btc_1h_change(self) -> float:
        """Fetch BTC 1h price change from Binance (legacy method, unused in main loop)."""
        return self.get_btc_change_pct()

    def get_spot_futures_ratio(self, symbol: str = "BTCUSDT") -> float:
        """
        Estimate spot/futures volume ratio.
        spot_vol / (spot_vol + futures_vol)
        """
        if not self.client:
            return 0.5  # Assume neutral when no client
        try:
            spot = self.client.get_ticker(symbol=symbol)
            futures = self.client.futures_ticker(symbol=symbol)
            spot_vol = float(spot.get("quoteVolume", 0))
            futures_vol = float(futures.get("quoteVolume", 0))
            total = spot_vol + futures_vol
            return spot_vol / total if total > 0 else 0.5
        except Exception:
            return 0.5
