import time
import logging
import httpx
import yfinance as yf
from datetime import date, timedelta

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

# ── DXY proxy via Frankfurter FX basket ─────────────────────────────────────────
# yfinance (UUP/DX-Y.NYB) bị Yahoo block khi chạy qua VPN/datacenter IP.
# Thay bằng Frankfurter (ECB data, miễn phí, không key, có lịch sử).
# Tính DXY proxy từ rổ tiền tệ chuẩn ICE US Dollar Index:
_DXY_WEIGHTS = {
    "EUR": 0.576,
    "JPY": 0.136,
    "GBP": 0.119,
    "CAD": 0.091,
    "SEK": 0.042,
    "CHF": 0.036,
}
_FRANKFURTER = "https://api.frankfurter.dev/v1"

# Cache theo số ngày để tránh gọi API nhiều lần (DXY thay đổi chậm)
_dxy_cache:  dict = {}              # {days: {"value": float, "ts": float}}
_gold_cache: dict = {"value": None, "ts": 0.0}
_CACHE_TTL = 3600   # 1 giờ


def _frankfurter_usd_rates(d: str | None = None) -> dict | None:
    """Lấy tỷ giá base=USD cho rổ DXY tại ngày d (hoặc mới nhất). None nếu lỗi."""
    symbols = ",".join(_DXY_WEIGHTS.keys())
    url = f"{_FRANKFURTER}/{d or 'latest'}?base=USD&symbols={symbols}"
    try:
        r = httpx.get(url, timeout=8.0, follow_redirects=True)
        if r.status_code == 200:
            return r.json().get("rates", {})
    except Exception as e:
        log.debug("Frankfurter fetch failed (%s): %s", d, e)
    return None


def dxy_change_pct(days: int = 1) -> float:
    """
    DXY % change qua `days` ngày, tính từ rổ FX Frankfurter.
    base=USD → tỷ giá cao hơn = USD mạnh hơn. Weighted theo ICE DXY weights.
    Trả 0.0 nếu không lấy được data (neutral).
    Kết quả cache 1 giờ theo từng `days`.
    """
    global _dxy_cache
    now_ts = time.time()
    cached = _dxy_cache.get(days)
    if cached and now_ts - cached["ts"] < _CACHE_TTL:
        return cached["value"]

    now_rates = _frankfurter_usd_rates()
    if not now_rates:
        log.warning("DXY: không lấy được tỷ giá hiện tại — trả 0.0")
        return 0.0

    past_date = (date.today() - timedelta(days=days)).isoformat()
    past_rates = _frankfurter_usd_rates(past_date)
    if not past_rates:
        log.warning("DXY: không lấy được tỷ giá %d ngày trước — trả 0.0", days)
        return 0.0

    total_w = 0.0
    weighted = 0.0
    for ccy, w in _DXY_WEIGHTS.items():
        n = now_rates.get(ccy)
        p = past_rates.get(ccy)
        if n and p and p != 0:
            weighted += w * (n - p) / p * 100
            total_w += w

    value = weighted / total_w if total_w > 0 else 0.0
    _dxy_cache[days] = {"value": value, "ts": now_ts}
    log.info("DXY %dd change: %.3f%% (Frankfurter basket)", days, value)
    return value


def _yf_pct_change(symbol: str, period: str = "5d") -> float | None:
    """Thử lấy % change qua yfinance. None nếu fail."""
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


def _fetch_gold_change() -> float:
    """
    Gold 1-day % change: yfinance GLD → GC=F → 0.0 (neutral).
    Gold là signal phụ — neutral không làm hỏng scoring (default = 5 pts).
    """
    global _gold_cache
    now = time.time()
    if _gold_cache["value"] is not None and now - _gold_cache["ts"] < _CACHE_TTL:
        return _gold_cache["value"]

    for ticker in ("GLD", "GC=F"):
        v = _yf_pct_change(ticker)
        if v is not None:
            _gold_cache = {"value": v, "ts": now}
            return v

    log.debug("Gold sources unavailable — returning 0.0 (neutral)")
    return 0.0


class MacroContext:
    def __init__(self):
        pass

    def fetch_dxy_change(self) -> float:
        """DXY 1-day % change via Frankfurter basket."""
        return dxy_change_pct(days=1)

    def fetch_gold_change(self) -> float:
        return _fetch_gold_change()

    def score_dxy(self, dxy_change_pct: float) -> int:
        if dxy_change_pct <= DXY_BULLISH_THRESHOLD:
            return 10   # Dollar yếu = dòng tiền chảy vào risk assets
        if dxy_change_pct >= DXY_BEARISH_THRESHOLD:
            return 0    # Dollar mạnh = risk-off
        return 5        # Trung tính

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
