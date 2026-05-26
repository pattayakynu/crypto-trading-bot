import os
import httpx

# USDT volume anomaly thresholds
USDT_VOLUME_SPIKE_HIGH = 3.0    # USDT volume > 3x 24h average = strong fiat inflow
USDT_VOLUME_SPIKE_MED = 1.8     # USDT volume > 1.8x = moderate inflow

# Whale Alert thresholds (in USD)
WHALE_TRANSFER_LARGE = 10_000_000   # $10M+ transfer = significant
WHALE_TRANSFER_MEDIUM = 1_000_000   # $1M+ transfer = notable

FIAT_FLOW_MAX_SCORE = 15

WHALE_ALERT_BASE_URL = "https://api.whale-alert.io/v1"


class FiatFlowTracker:
    def __init__(self, whale_alert_api_key: str = None):
        self.api_key = whale_alert_api_key or os.getenv("WHALE_ALERT_API_KEY", "")

    def score_usdt_volume(self, current_volume: float, avg_volume_24h: float) -> int:
        """
        USDT/USD volume spike = fiat inflow vào crypto = bullish.
        So sánh volume hiện tại với average 24h của pair USDT.
        """
        if avg_volume_24h <= 0:
            return 0
        ratio = current_volume / avg_volume_24h
        if ratio >= USDT_VOLUME_SPIKE_HIGH:
            return 10
        if ratio >= USDT_VOLUME_SPIKE_MED:
            return 5
        return 0

    def score_whale_transfers(self, transfers: list[dict]) -> int:
        """
        Whale transfer vào sàn (exchange) = có thể bán.
        Whale transfer ra khỏi sàn = accumulate, bullish.

        transfers: list of {"amount_usd": float, "to_type": "exchange"|"wallet"|"unknown"}
        """
        net_score = 0
        for t in transfers:
            amount = t.get("amount_usd", 0)
            to_type = t.get("to_type", "unknown")

            if to_type == "wallet":
                # Rút ra khỏi sàn = accumulate = bullish
                if amount >= WHALE_TRANSFER_LARGE:
                    net_score += 5
                elif amount >= WHALE_TRANSFER_MEDIUM:
                    net_score += 2
            elif to_type == "exchange":
                # Nạp vào sàn = có thể bán = bearish signal
                if amount >= WHALE_TRANSFER_LARGE:
                    net_score -= 3
                elif amount >= WHALE_TRANSFER_MEDIUM:
                    net_score -= 1

        # Clamp to [0, 5]
        return max(0, min(5, net_score))

    def total_score(self, current_volume: float, avg_volume_24h: float, transfers: list[dict]) -> int:
        score = (
            self.score_usdt_volume(current_volume, avg_volume_24h) +
            self.score_whale_transfers(transfers)
        )
        return min(FIAT_FLOW_MAX_SCORE, score)

    def get_recent_whale_transfers(self, min_value_usd: int = 1_000_000) -> list[dict]:
        """Fetch recent large transfers from Whale Alert API."""
        if not self.api_key:
            return []
        try:
            params = {
                "api_key": self.api_key,
                "min_value": min_value_usd,
                "limit": 10,
                "currency": "usdt,btc,eth",
            }
            resp = httpx.get(f"{WHALE_ALERT_BASE_URL}/transactions", params=params, timeout=5.0)
            if resp.status_code != 200:
                return []
            data = resp.json()
            results = []
            for tx in data.get("transactions", []):
                results.append({
                    "amount_usd": tx.get("amount_usd", 0),
                    "to_type": tx.get("to", {}).get("owner_type", "unknown"),
                    "from_type": tx.get("from", {}).get("owner_type", "unknown"),
                    "symbol": tx.get("symbol", ""),
                })
            return results
        except Exception:
            return []
