from dataclasses import dataclass, field

# Layer max scores (must match individual module caps)
LAYER_MAX = {
    "manipulation": 0,   # Tầng 0 — not a scorer, it's a gate
    "whale":        25,  # Tầng 1 — outflow(10) + funding(10) + OI(5)
    "macro":        20,  # Tầng 2 — DXY(10) + gold(10)
    "fiat_flow":    15,  # Tầng 3 — USDT volume(10) + whale transfers(5)
    "btc_lead":     20,  # Tầng 4 — BTC move(15) + alt correlation(5)
    "ta":           10,  # Tầng 5 — RSI(4) + MACD(3) + BB(3) + EMA(3) capped at 10
    "social":       10,  # Tầng 6 — CryptoPanic(5) + LunarCrush(5)
}

TOTAL_MAX = sum(v for v in LAYER_MAX.values())  # 100
MIN_CONVICTION_SCORE = 55       # Must exceed to trigger a trade
HIGH_CONVICTION_SCORE = 75      # Strong signal — full position size


@dataclass
class LayerScores:
    whale: int = 0
    macro: int = 0
    fiat_flow: int = 0
    btc_lead: int = 0
    ta: int = 0
    social: int = 0

    def as_dict(self) -> dict:
        return {
            "whale": self.whale,
            "macro": self.macro,
            "fiat_flow": self.fiat_flow,
            "btc_lead": self.btc_lead,
            "ta": self.ta,
            "social": self.social,
        }


@dataclass
class ConvictionResult:
    total_score: int
    layer_scores: LayerScores
    action: str          # "BUY", "SKIP", "WATCH"
    confidence: str      # "HIGH", "MEDIUM", "LOW"
    reasons: list[str] = field(default_factory=list)

    @property
    def should_trade(self) -> bool:
        return self.action == "BUY"


class ConvictionScorer:
    def __init__(self, layer_weights: dict = None):
        """
        layer_weights: optional multipliers from adaptive learning.
        Default = 1.0 for all layers (flat weighting).
        """
        self.layer_weights = layer_weights or {
            "whale": 1.0,
            "macro": 1.0,
            "fiat_flow": 1.0,
            "btc_lead": 1.0,
            "ta": 1.0,
            "social": 1.0,
        }

    def apply_weights(self, layer_scores: LayerScores) -> int:
        """Apply adaptive weights to each layer score."""
        raw = layer_scores.as_dict()
        weighted_total = 0
        for layer, score in raw.items():
            weight = self.layer_weights.get(layer, 1.0)
            weighted_total += score * weight
        return round(weighted_total)

    def classify(self, score: int) -> tuple[str, str]:
        """Return (action, confidence) based on total score."""
        if score >= HIGH_CONVICTION_SCORE:
            return "BUY", "HIGH"
        if score >= MIN_CONVICTION_SCORE:
            return "BUY", "MEDIUM"
        if score >= MIN_CONVICTION_SCORE - 10:
            return "WATCH", "LOW"
        return "SKIP", "LOW"

    def build_reasons(self, layer_scores: LayerScores) -> list[str]:
        """Explain which layers contributed to the decision."""
        reasons = []
        raw = layer_scores.as_dict()
        maxes = {k: v for k, v in LAYER_MAX.items() if k != "manipulation"}

        for layer, score in raw.items():
            max_score = maxes.get(layer, 1)
            pct = (score / max_score * 100) if max_score > 0 else 0
            if pct >= 70:
                reasons.append(f"{layer}: STRONG ({score}/{max_score})")
            elif pct >= 40:
                reasons.append(f"{layer}: MODERATE ({score}/{max_score})")
            elif score > 0:
                reasons.append(f"{layer}: WEAK ({score}/{max_score})")
        return reasons

    def score(self, layer_scores: LayerScores) -> ConvictionResult:
        total = self.apply_weights(layer_scores)
        total = min(100, max(0, total))
        action, confidence = self.classify(total)
        reasons = self.build_reasons(layer_scores)
        return ConvictionResult(
            total_score=total,
            layer_scores=layer_scores,
            action=action,
            confidence=confidence,
            reasons=reasons,
        )

    def score_from_dict(self, scores: dict) -> ConvictionResult:
        """Convenience: accept a plain dict of layer scores."""
        ls = LayerScores(
            whale=scores.get("whale", 0),
            macro=scores.get("macro", 0),
            fiat_flow=scores.get("fiat_flow", 0),
            btc_lead=scores.get("btc_lead", 0),
            ta=scores.get("ta", 0),
            social=scores.get("social", 0),
        )
        return self.score(ls)
