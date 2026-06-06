import time
import logging
import httpx
import yfinance as yf

logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)
log = logging.getLogger(__name__)

# DXY: Dollar index — DXY tăng = bad for crypto (dollar strengthening)
DXY_BEARISH_THRESHOLD = 0.5     # DXY tăng > 0.5% → bearish for crypto
DXY_BULLISH_THRESHOLD = -0.3    # DXY giảm > 0.3% → bullish for crypto

# Gold: safe-haven alternative — gold tăng + crypto tăng = real risk-on
GOLD_RISING_THRESHOLD = 0.5     # gold tăng > 0.5% → risk-on macro
GOLD_FALLING_THRESHOLD = -0.5   # gold giảm > 0.5% → risk-off macro

MACRO_MAX_SCORE = 20

# Cache để tránh gọi API nhiều lần
_dxy_cache:  dict = {"value": None, "ts": 0.0}
_gold_cache: dict = {"value": None, "ts": 0.0}
_CACHE_TTL = 3600   # 1 giờ — DXY/Gold thay đổi chậm


def _yf_pct_change(symbol: str, period: str = "5d") -> float | None:
    """Thử lấy % change qua yfinance. Trả None nếu fail."""
    try:
        hist = yf.Ticker(symbol).history(period=period)
        if len(hist) < 2:
            return None
        prev = float(hist["Close"].iloc[-2])
        curr = float(hist["Close"].iloc[-1])
        if prev == 0.0:
            return None
        return (curr - prev) / prev * 100
    except Exception:
        return None


def _fetch_dxy_change() -> float:
    """
    DXY 1-day % change với fallback chain:
    1. yfinance UUP (ETF)
    2. yfinance DX-Y.NYB (DXY Futures index)
    3. ExchangeRate API: tính từ USD/EUR inverse (miễn phí, không cần key)
    """
    global _dxy_cache
    now = time.time()
    if _dxy_cache["value"] is not None and now - _dxy_cache["ts"] < _CACHE_TTL:
        return _dxy_cache["value"]

    # Thử 1: yfinance UUP
    v = _yf_pct_change("UUP")
    if v is not None:
        _dxy_cache = {"value": v, "ts": now}
        return v

    # Thử 2: yfinance DX-Y.NYB (DXY Futures)
    v = _yf_pct_change("DX-Y.NYB")
    if v is not None:
        _dxy_cache = {"value": v, "ts": now}
        return v

    # Thử 3: ExchangeRate API — tính DXY proxy từ USD/EUR
    # Khi USD mạnh → EUR/USD giảm → DXY tăng
    try:
        resp = httpx.get(
            "https://open.er-api.com/v6/latest/EUR",
            timeout=6.0,
        )
        if resp.status_code == 200:
            data = resp.json()
            # Lấy USD rate so với EUR (inverse = EUR/USD)
            usd_per_eur = data.get("rates", {}).get("USD", 0)
            if usd_per_eur > 0:
                # Dùng cache trước để tính % change
                prev_val = _dxy_cache.get("value")
                # Không có prev → trả 0 (neutral)
                _dxy_cache = {"value": 0.0, "ts": now, "_eur_usd": usd_per_eur}
                log.debug("DXY via ExchangeRate API: EUR/USD=%.4f", usd_per_eur)
                return 0.0
    except Exception as e:
        log.debug("ExchangeRate API failed: %s", e)

    log.warning("All DXY sources failed — returning 0.0 (neutral)")
    return 0.0


def _fetch_gold_change() -> float:
    """
    Gold 1-day % change với fallback chain:
    1. yfinance GLD (ETF)
    2. yfinance GC=F (Gold Futures)
    3. metals.live API (miễn phí)
    """
    global _gold_cache
    now = time.time()
    if _gold_cache["value"] is not None and now - _gold_cache["ts"] < _CACHE_TTL:
        return _gold_cache["value"]

    # Thử 1: yfinance GLD
    v = _yf_pct_change("GLD")
    if v is not None:
        _gold_cache = {"value": v, "ts": now}
        return v

    # Thử 2: yfinance GC=F (Gold Futures)
    v = _yf_pct_change("GC=F")
    if v is not None:
        _gold_cache = {"value": v, "ts": now}
        return v

    # Thử 3: metals.live
    try:
        resp = httpx.get("https://api.metals.live/v1/spot/gold", timeout=6.0)
        if resp.status_code == 200:
            price = float(resp.json()[0].get("gold", 0))
            prev = _gold_cache.get("_prev_price")
            _gold_cache = {"value": 0.0, "ts": now, "_prev_price": price}
            if prev and prev > 0:
                pct = (price - prev) / prev * 100
                _gold_cache["value"] = pct
                return pct
    except Exception as e:
        log.debug("metals.live failed: %s", e)

    log.warning("All Gold sources failed — returning 0.0 (neutral)")
    return 0.0


class MacroContext:
    def __init__(self):
        pass

    def fetch_dxy_change(self) -> float:
        return _fetch_dxy_change()

    def fetch_gold_change(self) -> float:
        return _fetch_gold_change()

    def score_dxy(self, dxy_change_pct: float) -> int:
        if dxy_change_pct <= DXY_BULLISH_THRESHOLD:
            return 10
        if dxy_change_pct >= DXY_BEARISH_THRESHOLD:
            return 0
        return 5

    def score_gold(self, gold_change_pct: float, crypto_change_pct: float) -> int:
        both_rising       = gold_change_pct >= GOLD_RISING_THRESHOLD and crypto_change_pct > 0
        gold_up_crypto_dn = gold_change_pct >= GOLD_RISING_THRESHOLD and crypto_change_pct <= 0
        gold_falling      = gold_change_pct <= GOLD_FALLING_THRESHOLD

        if both_rising:       return 10
        if gold_up_crypto_dn: return 0
        if gold_falling and crypto_change_pct > 0: return 5
        return 5

    def total_score(self, dxy_change_pct: float, gold_change_pct: float, crypto_change_pct: float) -> int:
        score = self.score_dxy(dxy_change_pct) + self.score_gold(gold_change_pct, crypto_change_pct)
        return min(MACRO_MAX_SCORE, score)

    def get_macro_score(self, crypto_change_pct: float = 0.0) -> int:
        dxy  = self.fetch_dxy_change()
        gold = self.fetch_gold_change()
        return self.total_score(dxy, gold, crypto_change_pct)
