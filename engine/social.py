import os
import time
import httpx

CRYPTOPANIC_BASE_URL = "https://cryptopanic.com/api/v1"
LUNARCRUSH_BASE_URL  = "https://lunarcrush.com/api4/public"
FEAR_GREED_URL       = "https://api.alternative.me/fng/?limit=1"
COINGECKO_BASE_URL   = "https://api.coingecko.com/api/v3"

# Sentiment thresholds (CryptoPanic)
SENTIMENT_BULLISH_RATIO = 0.65
SENTIMENT_BEARISH_RATIO = 0.35

# LunarCrush Galaxy Score thresholds (0-100)
GALAXY_HIGH = 65
GALAXY_MED  = 40

# Social volume spike
SOCIAL_SPIKE_HIGH = 3.0
SOCIAL_SPIKE_MED  = 1.5

# Fear & Greed thresholds
FEAR_GREED_EXTREME_GREED = 75
FEAR_GREED_GREED         = 55
FEAR_GREED_NEUTRAL_HIGH  = 55
FEAR_GREED_NEUTRAL_LOW   = 45
FEAR_GREED_FEAR          = 25

# CoinGecko sentiment
COINGECKO_BULLISH_PCT = 65.0   # > 65% up votes = bullish
COINGECKO_NEUTRAL_PCT = 50.0   # > 50% up votes = neutral

# CoinGecko coin ID mapping
COINGECKO_IDS = {
    "BTCUSDT": "bitcoin",
    "ETHUSDT": "ethereum",
    "BNBUSDT": "binancecoin",
    "SOLUSDT": "solana",
    "ADAUSDT": "cardano",
}

SOCIAL_MAX_SCORE = 10

# ── In-memory cache ───────────────────────────────────────────────────────────
_fg_cache:  dict = {"value": None, "ts": 0.0}  # Fear & Greed — cache 30 min
_cg_cache:  dict = {}                            # CoinGecko per-symbol — cache 30 min
_CACHE_TTL  = 1800  # 30 minutes


class SocialSignal:
    def __init__(self, cryptopanic_key: str = None, lunarcrush_key: str = None):
        self.cryptopanic_key = cryptopanic_key or os.getenv("CRYPTOPANIC_API_KEY", "")
        self.lunarcrush_key  = lunarcrush_key  or os.getenv("LUNARCRUSH_API_KEY", "")

    # ── Fear & Greed ──────────────────────────────────────────────────────────

    def score_fear_greed(self, value: int) -> int:
        """
        Fear & Greed Index (0-100) từ alternative.me.
        Extreme Greed = thị trường phấn khích = 5 pts.
        Extreme Fear  = panic selling  = 0 pts (nguy hiểm khi mua vào đám đông).
        """
        if value >= FEAR_GREED_EXTREME_GREED:
            return 5   # Extreme Greed — momentum mạnh
        if value >= FEAR_GREED_GREED:
            return 4   # Greed — tích cực
        if value >= FEAR_GREED_NEUTRAL_LOW:
            return 2   # Neutral
        if value >= FEAR_GREED_FEAR:
            return 1   # Fear — thận trọng
        return 0       # Extreme Fear — tránh

    def get_fear_greed_index(self) -> int:
        """Fetch Fear & Greed Index từ alternative.me. Cache 30 phút."""
        now = time.time()
        if _fg_cache["value"] is not None and now - _fg_cache["ts"] < _CACHE_TTL:
            return _fg_cache["value"]
        try:
            resp = httpx.get(FEAR_GREED_URL, timeout=5.0)
            if resp.status_code == 200:
                value = int(resp.json()["data"][0]["value"])
                _fg_cache["value"] = value
                _fg_cache["ts"]    = now
                return value
        except Exception:
            pass
        return _fg_cache["value"] if _fg_cache["value"] is not None else 50  # default neutral

    # ── CoinGecko Sentiment ───────────────────────────────────────────────────

    def score_coingecko_sentiment(self, up_pct: float) -> int:
        """
        sentiment_votes_up_percentage từ CoinGecko community data.
        > 65% up votes = cộng đồng bullish → 3 pts.
        > 50% up votes = tạm ổn → 1 pt.
        """
        if up_pct >= COINGECKO_BULLISH_PCT:
            return 3
        if up_pct >= COINGECKO_NEUTRAL_PCT:
            return 1
        return 0

    def get_coingecko_sentiment(self, symbol: str) -> float:
        """
        Fetch sentiment_votes_up_percentage từ CoinGecko (không cần API key).
        Cache 30 phút per symbol.
        """
        now = time.time()
        cached = _cg_cache.get(symbol)
        if cached and now - cached["ts"] < _CACHE_TTL:
            return cached["value"]

        coin_id = COINGECKO_IDS.get(symbol)
        if not coin_id:
            return 50.0  # unknown coin — neutral

        try:
            resp = httpx.get(
                f"{COINGECKO_BASE_URL}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "false",
                    "community_data": "true",
                    "developer_data": "false",
                },
                timeout=6.0,
            )
            if resp.status_code == 200:
                data = resp.json()
                up_pct = float(data.get("sentiment_votes_up_percentage") or 50.0)
                _cg_cache[symbol] = {"value": up_pct, "ts": now}
                return up_pct
        except Exception:
            pass
        return 50.0  # default neutral

    # ── CryptoPanic (optional bonus) ──────────────────────────────────────────

    def score_cryptopanic_sentiment(
        self, positive_count: int, negative_count: int, total_count: int
    ) -> int:
        """CryptoPanic news sentiment — max 5 pts (capped to 2 khi dùng làm bonus)."""
        if total_count < 3:
            return 0
        positive_ratio = positive_count / total_count
        negative_ratio = negative_count / total_count
        if positive_ratio >= SENTIMENT_BULLISH_RATIO:
            return 5
        if negative_ratio >= (1 - SENTIMENT_BEARISH_RATIO):
            return 0
        return 2

    def get_cryptopanic_news(self, symbol: str) -> dict:
        if not self.cryptopanic_key:
            return {"positive": 0, "negative": 0, "total": 0}
        try:
            params = {
                "auth_token": self.cryptopanic_key,
                "currencies": symbol.replace("USDT", ""),
                "filter": "all",
                "public": "true",
            }
            resp = httpx.get(f"{CRYPTOPANIC_BASE_URL}/posts/", params=params, timeout=5.0)
            if resp.status_code != 200:
                return {"positive": 0, "negative": 0, "total": 0}
            results = resp.json().get("results", [])
            positive = sum(1 for r in results if r.get("votes", {}).get("positive", 0) > r.get("votes", {}).get("negative", 0))
            negative = sum(1 for r in results if r.get("votes", {}).get("negative", 0) > r.get("votes", {}).get("positive", 0))
            return {"positive": positive, "negative": negative, "total": len(results)}
        except Exception:
            return {"positive": 0, "negative": 0, "total": 0}

    # ── LunarCrush (optional bonus) ───────────────────────────────────────────

    def score_lunarcrush(self, galaxy_score: float, social_volume_ratio: float) -> int:
        """LunarCrush Galaxy Score + social volume spike — max 5 pts."""
        galaxy_pts = 0
        if galaxy_score >= GALAXY_HIGH:
            galaxy_pts = 3
        elif galaxy_score >= GALAXY_MED:
            galaxy_pts = 1

        volume_pts = 0
        if social_volume_ratio >= SOCIAL_SPIKE_HIGH:
            volume_pts = 2
        elif social_volume_ratio >= SOCIAL_SPIKE_MED:
            volume_pts = 1

        return min(5, galaxy_pts + volume_pts)

    def get_lunarcrush_data(self, symbol: str) -> dict:
        if not self.lunarcrush_key:
            return {"galaxy_score": 0.0, "social_volume_ratio": 1.0}
        try:
            coin = symbol.replace("USDT", "").lower()
            headers = {"Authorization": f"Bearer {self.lunarcrush_key}"}
            resp = httpx.get(
                f"{LUNARCRUSH_BASE_URL}/coins/{coin}/v1",
                headers=headers,
                timeout=5.0,
            )
            if resp.status_code != 200:
                return {"galaxy_score": 0.0, "social_volume_ratio": 1.0}
            data = resp.json().get("data", {})
            galaxy_score = float(data.get("galaxy_score", 0))
            social_volume = float(data.get("social_volume_24h", 0))
            social_volume_7d_avg = float(data.get("social_volume_7d_average", social_volume or 1))
            ratio = social_volume / social_volume_7d_avg if social_volume_7d_avg > 0 else 1.0
            return {"galaxy_score": galaxy_score, "social_volume_ratio": ratio}
        except Exception:
            return {"galaxy_score": 0.0, "social_volume_ratio": 1.0}

    # ── Orchestrator ──────────────────────────────────────────────────────────

    def get_social_score(self, symbol: str) -> int:
        """
        Tính điểm social tổng hợp từ tất cả nguồn.
        Luôn có điểm từ Fear&Greed (0-5) + CoinGecko (0-3) = 0-8 pts.
        CryptoPanic/LunarCrush là bonus tối đa +2 pts mỗi cái.
        """
        # ── Primary (không cần key) ───────────────────────────────────────────
        fg_value  = self.get_fear_greed_index()
        cg_up_pct = self.get_coingecko_sentiment(symbol)

        fg_score = self.score_fear_greed(fg_value)
        cg_score = self.score_coingecko_sentiment(cg_up_pct)

        # ── Bonus (cần key, capped ở 2 pts mỗi nguồn) ────────────────────────
        cp_bonus = 0
        if self.cryptopanic_key:
            news = self.get_cryptopanic_news(symbol)
            raw  = self.score_cryptopanic_sentiment(
                news["positive"], news["negative"], news["total"]
            )
            cp_bonus = min(2, raw // 2)  # scale 0-5 → 0-2

        lc_bonus = 0
        if self.lunarcrush_key:
            lc   = self.get_lunarcrush_data(symbol)
            raw  = self.score_lunarcrush(lc["galaxy_score"], lc["social_volume_ratio"])
            lc_bonus = min(2, raw // 2)  # scale 0-5 → 0-2

        total = fg_score + cg_score + cp_bonus + lc_bonus
        return min(SOCIAL_MAX_SCORE, total)

    def total_score(
        self,
        positive_count: int,
        negative_count: int,
        total_news: int,
        galaxy_score: float,
        social_volume_ratio: float,
    ) -> int:
        """Legacy interface — giữ để backward compat với tests cũ."""
        score = (
            self.score_cryptopanic_sentiment(positive_count, negative_count, total_news)
            + self.score_lunarcrush(galaxy_score, social_volume_ratio)
        )
        return min(SOCIAL_MAX_SCORE, score)
