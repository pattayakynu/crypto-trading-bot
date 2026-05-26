import os

OUTFLOW_HIGH_THRESHOLD = 2.0
OUTFLOW_MED_THRESHOLD = 1.0
FUNDING_BULLISH_THRESHOLD = -0.00005
FUNDING_NEUTRAL_THRESHOLD = 0.0001
FUNDING_CROWDED_THRESHOLD = 0.0002


class WhaleTracker:
    def __init__(self, client=None):
        self.client = client

    def score_exchange_outflow(self, outflow_pct_24h: float) -> int:
        """Coins rời sàn = đang accumulate, không bán."""
        if outflow_pct_24h >= OUTFLOW_HIGH_THRESHOLD:
            return 10
        if outflow_pct_24h >= OUTFLOW_MED_THRESHOLD:
            return 5
        return 0

    def score_funding_rate(self, funding_rate: float, price_change_pct: float) -> int:
        """
        Funding âm + giá tăng = organic spot buying, không phải leverage.
        Funding cao + giá tăng mạnh = crowded longs = risky.
        """
        if funding_rate <= FUNDING_BULLISH_THRESHOLD and price_change_pct > 0:
            return 10  # Bullish divergence — bears đang trả phí
        if funding_rate <= FUNDING_NEUTRAL_THRESHOLD and 0 < price_change_pct < 1.0:
            return 5   # Neutral — healthy
        if funding_rate > FUNDING_CROWDED_THRESHOLD and price_change_pct > 1.5:
            return 0   # Quá nhiều longs = nguy hiểm
        return 3

    def score_open_interest(self, oi_change_pct: float, price_change_pct: float) -> int:
        """OI giảm + giá tăng = short squeeze = organic bullish."""
        if oi_change_pct < -1.0 and price_change_pct > 0:
            return 5
        return 0

    def total_score(
        self,
        outflow_pct_24h: float,
        funding_rate: float,
        price_change_pct: float,
        oi_change_pct: float
    ) -> int:
        score = (
            self.score_exchange_outflow(outflow_pct_24h) +
            self.score_funding_rate(funding_rate, price_change_pct) +
            self.score_open_interest(oi_change_pct, price_change_pct)
        )
        return min(25, score)

    def get_funding_rate(self, symbol: str) -> float:
        if not self.client:
            return 0.0
        try:
            data = self.client.futures_funding_rate(symbol=symbol, limit=1)
            return float(data[0]["fundingRate"]) if data else 0.0
        except Exception:
            return 0.0

    def get_open_interest_change(self, symbol: str) -> float:
        if not self.client:
            return 0.0
        try:
            hist = self.client.futures_open_interest_hist(
                symbol=symbol, period="5m", limit=12
            )
            if len(hist) < 2:
                return 0.0
            first = float(hist[0]["sumOpenInterest"])
            last = float(hist[-1]["sumOpenInterest"])
            return (last - first) / first * 100 if first > 0 else 0.0
        except Exception:
            return 0.0
