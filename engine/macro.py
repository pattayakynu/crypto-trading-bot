import logging
import yfinance as yf

# Tắt yfinance logger để tránh spam lỗi khi ticker không có data
logging.getLogger("yfinance").setLevel(logging.CRITICAL)
logging.getLogger("peewee").setLevel(logging.CRITICAL)

# DXY: Dollar index — DXY tăng = bad for crypto (dollar strengthening)
DXY_BEARISH_THRESHOLD = 0.5     # DXY tăng > 0.5% → bearish for crypto
DXY_BULLISH_THRESHOLD = -0.3    # DXY giảm > 0.3% → bullish for crypto

# Gold: safe-haven alternative — gold tăng + crypto tăng = real risk-on
GOLD_RISING_THRESHOLD = 0.5     # gold tăng > 0.5% → risk-on macro
GOLD_FALLING_THRESHOLD = -0.5   # gold giảm > 0.5% → risk-off macro

# BTC correlation bonus: BTC leading + macro aligned = strong signal
MACRO_MAX_SCORE = 20


class MacroContext:
    def __init__(self):
        self._dxy_cache = None
        self._gold_cache = None

    def _fetch_pct_change(self, symbol: str) -> float:
        """Fetch 1-day % change for a ticker. Returns 0.0 on any error (silent)."""
        try:
            hist = yf.Ticker(symbol).history(period="5d")
            if len(hist) < 2:
                return 0.0
            prev = float(hist["Close"].iloc[-2])
            curr = float(hist["Close"].iloc[-1])
            if prev == 0.0:
                return 0.0
            return (curr - prev) / prev * 100
        except Exception:
            return 0.0

    def fetch_dxy_change(self) -> float:
        """Fetch DXY 1-day % change — dùng UUP ETF (Invesco DB US Dollar Index Bullish Fund)."""
        # UUP bám sát DXY, liquid hơn và ticker ổn định hơn DX-Y.NYB
        return self._fetch_pct_change("UUP")

    def fetch_gold_change(self) -> float:
        """Fetch Gold 1-day % change — dùng GLD ETF (SPDR Gold Shares)."""
        # GLD bám sát giá vàng spot, ổn định hơn GC=F futures (tránh lỗi rollover)
        return self._fetch_pct_change("GLD")

    def score_dxy(self, dxy_change_pct: float) -> int:
        """
        DXY giảm → dollar yếu → crypto được lợi → bullish.
        DXY tăng → dollar mạnh → dòng tiền rút khỏi crypto → bearish.
        """
        if dxy_change_pct <= DXY_BULLISH_THRESHOLD:
            return 10   # Dollar yếu = dòng tiền chảy vào risk assets
        if dxy_change_pct >= DXY_BEARISH_THRESHOLD:
            return 0    # Dollar mạnh = risk-off
        return 5        # Trung tính

    def score_gold(self, gold_change_pct: float, crypto_change_pct: float) -> int:
        """
        Gold tăng + crypto tăng = real risk-on sentiment.
        Gold tăng + crypto giảm = flight to safety (bad for crypto).
        Gold giảm + crypto tăng = pure crypto speculation (risky).
        """
        both_rising = gold_change_pct >= GOLD_RISING_THRESHOLD and crypto_change_pct > 0
        gold_up_crypto_down = gold_change_pct >= GOLD_RISING_THRESHOLD and crypto_change_pct <= 0
        gold_falling = gold_change_pct <= GOLD_FALLING_THRESHOLD

        if both_rising:
            return 10   # Risk-on across all assets = strong macro tailwind
        if gold_up_crypto_down:
            return 0    # Flight to safety — crypto outflow
        if gold_falling and crypto_change_pct > 0:
            return 5    # Crypto-specific move — neutral macro
        return 5        # Default neutral

    def total_score(self, dxy_change_pct: float, gold_change_pct: float, crypto_change_pct: float) -> int:
        score = self.score_dxy(dxy_change_pct) + self.score_gold(gold_change_pct, crypto_change_pct)
        return min(MACRO_MAX_SCORE, score)

    def get_macro_score(self, crypto_change_pct: float = 0.0) -> int:
        """Fetch live data and return macro score."""
        dxy = self.fetch_dxy_change()
        gold = self.fetch_gold_change()
        return self.total_score(dxy, gold, crypto_change_pct)
