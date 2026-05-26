import os
import httpx

CRYPTOPANIC_BASE_URL = "https://cryptopanic.com/api/v1"
LUNARCRUSH_BASE_URL = "https://lunarcrush.com/api4/public"

# Sentiment thresholds
SENTIMENT_BULLISH_RATIO = 0.65   # > 65% positive votes = bullish
SENTIMENT_BEARISH_RATIO = 0.35   # < 35% positive votes = bearish

# LunarCrush Galaxy Score thresholds (0-100)
GALAXY_HIGH = 65    # > 65 = strong social momentum
GALAXY_MED = 40     # > 40 = moderate attention

# Social volume spike
SOCIAL_SPIKE_HIGH = 3.0     # Social volume > 3x 7d average = viral
SOCIAL_SPIKE_MED = 1.5      # Social volume > 1.5x = elevated

SOCIAL_MAX_SCORE = 10


class SocialSignal:
    def __init__(self, cryptopanic_key: str = None, lunarcrush_key: str = None):
        self.cryptopanic_key = cryptopanic_key or os.getenv("CRYPTOPANIC_API_KEY", "")
        self.lunarcrush_key = lunarcrush_key or os.getenv("LUNARCRUSH_API_KEY", "")

    def score_cryptopanic_sentiment(self, positive_count: int, negative_count: int, total_count: int) -> int:
        """
        CryptoPanic news sentiment: ratio of positive to total votes.
        High positive ratio + decent volume of news = social confidence.
        """
        if total_count < 3:
            return 0    # Not enough news to be meaningful

        positive_ratio = positive_count / total_count
        negative_ratio = negative_count / total_count

        if positive_ratio >= SENTIMENT_BULLISH_RATIO:
            return 5    # Strong bullish sentiment
        if negative_ratio >= (1 - SENTIMENT_BEARISH_RATIO):
            return 0    # Strong bearish sentiment
        return 2        # Mixed/neutral

    def score_lunarcrush(self, galaxy_score: float, social_volume_ratio: float) -> int:
        """
        Galaxy Score = overall social/market health score by LunarCrush (0-100).
        Social volume spike = trending on social media.
        """
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

    def total_score(
        self,
        positive_count: int,
        negative_count: int,
        total_news: int,
        galaxy_score: float,
        social_volume_ratio: float
    ) -> int:
        score = (
            self.score_cryptopanic_sentiment(positive_count, negative_count, total_news) +
            self.score_lunarcrush(galaxy_score, social_volume_ratio)
        )
        return min(SOCIAL_MAX_SCORE, score)

    def get_cryptopanic_news(self, symbol: str) -> dict:
        """
        Fetch news sentiment from CryptoPanic.
        Returns {positive: int, negative: int, total: int}
        """
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

            data = resp.json()
            results = data.get("results", [])
            positive = sum(1 for r in results if r.get("votes", {}).get("positive", 0) > r.get("votes", {}).get("negative", 0))
            negative = sum(1 for r in results if r.get("votes", {}).get("negative", 0) > r.get("votes", {}).get("positive", 0))
            return {"positive": positive, "negative": negative, "total": len(results)}
        except Exception:
            return {"positive": 0, "negative": 0, "total": 0}

    def get_lunarcrush_data(self, symbol: str) -> dict:
        """
        Fetch Galaxy Score and social volume from LunarCrush.
        Returns {galaxy_score: float, social_volume_ratio: float}
        """
        if not self.lunarcrush_key:
            return {"galaxy_score": 0.0, "social_volume_ratio": 1.0}
        try:
            coin = symbol.replace("USDT", "").lower()
            headers = {"Authorization": f"Bearer {self.lunarcrush_key}"}
            resp = httpx.get(
                f"{LUNARCRUSH_BASE_URL}/coins/{coin}/v1",
                headers=headers,
                timeout=5.0
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
