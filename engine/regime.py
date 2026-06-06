import logging
import time
import httpx
import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

log = logging.getLogger(__name__)

BTC_BULL_THRESHOLD = 5.0         # BTC 7d > +5% = enter BULL regime
BTC_BULL_EXIT_THRESHOLD = 2.0    # Once in BULL, stay until BTC 7d drops below 2%
                                  # (hysteresis prevents whipsawing near the 5% boundary)
BTC_BEAR_THRESHOLD = -5.0        # BTC 7d < -5% = weekly downtrend
DXY_BEAR_THRESHOLD = 1.5         # UUP 10d > +1.5% = strong dollar = crypto headwind

_regime_cache: dict = {"value": None, "ts": 0.0}
_REGIME_TTL = 3600  # Regime changes slowly — cache 1 hour


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
        """
        DXY 10-day % change qua Frankfurter FX basket (xem macro.dxy_change_pct).
        yfinance UUP/DX-Y.NYB bị Yahoo block khi chạy qua VPN.
        """
        try:
            from macro import dxy_change_pct
            return dxy_change_pct(days=10)
        except Exception as e:
            log.debug("get_dxy_10d_change failed: %s", e)
            return 0.0

    def detect(self) -> str:
        """
        Detect market regime with hysteresis to avoid whipsawing near the BULL boundary.

        Entry thresholds (fresh or SIDEWAYS/BEAR state):
          BULL:     BTC 7d >= +5% AND DXY 10d < +1.5%
          BEAR:     BTC 7d <= -5% OR DXY 10d >= +1.5%
          SIDEWAYS: everything else

        Hysteresis (once in BULL, use looser exit thresholds):
          Stay BULL:  BTC 7d >= +2% AND DXY 10d < +1.5%
          Exit BULL:  BTC 7d < +2% → SIDEWAYS/BEAR per normal rules

        Result cached for 1 hour.
        """
        global _regime_cache
        now = time.time()
        if _regime_cache["value"] is not None and now - _regime_cache["ts"] < _REGIME_TTL:
            return _regime_cache["value"]

        btc_7d = self.get_btc_7d_change()
        dxy_10d = self.get_dxy_10d_change()
        prev_regime = _regime_cache.get("value")

        if prev_regime == MarketRegime.BULL:
            # Hysteresis: once in BULL, stay until BTC 7d drops below 2%
            # This prevents flip-flopping when BTC hovers around the 5% threshold
            if btc_7d >= BTC_BULL_EXIT_THRESHOLD and dxy_10d < DXY_BEAR_THRESHOLD:
                regime = MarketRegime.BULL
            elif btc_7d <= BTC_BEAR_THRESHOLD or dxy_10d >= DXY_BEAR_THRESHOLD:
                regime = MarketRegime.BEAR
            else:
                regime = MarketRegime.SIDEWAYS
        else:
            # Normal entry thresholds
            if btc_7d >= BTC_BULL_THRESHOLD and dxy_10d < DXY_BEAR_THRESHOLD:
                regime = MarketRegime.BULL
            elif btc_7d <= BTC_BEAR_THRESHOLD or dxy_10d >= DXY_BEAR_THRESHOLD:
                regime = MarketRegime.BEAR
            else:
                regime = MarketRegime.SIDEWAYS

        log.info("Market regime: %s (BTC 7d=%.1f%%, DXY 10d=%.2f%%)", regime, btc_7d, dxy_10d)
        _regime_cache = {"value": regime, "ts": now}
        return regime
