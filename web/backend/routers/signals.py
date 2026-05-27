import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from fastapi import APIRouter
from db import get_session
from models import SignalLog

router = APIRouter()

WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
    "XRPUSDT", "DOGEUSDT", "AVAXUSDT", "LINKUSDT", "LTCUSDT",
]

# Must mirror engine/scorer.py LAYER_MAX
LAYER_MAX = {
    "whale":     25,
    "macro":     20,
    "fiat_flow": 15,
    "btc_lead":  20,
    "ta":        10,
    "social":    10,
}

LAYER_LABELS = {
    "whale":     "Cá voi",
    "macro":     "Vĩ mô",
    "fiat_flow": "Dòng tiền",
    "btc_lead":  "BTC dẫn",
    "ta":        "Kỹ thuật",
    "social":    "Cộng đồng",
}

SHORT_SIGNAL_MAX = {
    "alt_weakness":      25,
    "funding_reset":     25,
    "volume_exhaustion": 25,
    "macro_bearish":     25,
}

SHORT_SIGNAL_LABELS = {
    "alt_weakness":      "Alt yếu",
    "funding_reset":     "Funding reset",
    "volume_exhaustion": "Vol cạn kiệt",
    "macro_bearish":     "Vĩ mô giảm",
}

SHORT_SIGNAL_ORDER = ["alt_weakness", "funding_reset", "volume_exhaustion", "macro_bearish"]

MIN_CONVICTION  = 55
HIGH_CONVICTION = 75


def _strength(score: int, max_score: int) -> str:
    """Classify layer strength from raw score."""
    pct = score / max_score * 100 if max_score else 0
    if pct >= 70:
        return "STRONG"
    if pct >= 40:
        return "MODERATE"
    if score > 0:
        return "WEAK"
    return "NONE"


def _confidence(score: int) -> str:
    """Map total conviction score to confidence label."""
    if score >= HIGH_CONVICTION:
        return "HIGH"
    if score >= MIN_CONVICTION:
        return "MEDIUM"
    return "LOW"


@router.get("/signals/latest")
def get_latest_signals():
    """
    Return the last 3 scan results per coin from SignalLog.
    Each entry contains per-layer scores with strength labels and percentages.
    Used by the Bot Thought Stream dashboard component.
    """
    session = get_session()
    try:
        result = []
        for pair in WATCHLIST:
            rows = (
                session.query(SignalLog)
                .filter(SignalLog.pair == pair)
                .order_by(SignalLog.id.desc())
                .limit(3)
                .all()
            )

            scans = []
            for row in rows:
                try:
                    layers_raw = json.loads(row.layer_scores or "{}")
                except Exception:
                    layers_raw = {}

                layers = {}
                for layer, max_s in LAYER_MAX.items():
                    score = int(layers_raw.get(layer, 0))
                    pct   = round(score / max_s * 100) if max_s else 0
                    layers[layer] = {
                        "score":    score,
                        "max":      max_s,
                        "pct":      pct,
                        "strength": _strength(score, max_s),
                        "label":    LAYER_LABELS.get(layer, layer),
                    }

                scanned_at = None
                if row.created_at:
                    scanned_at = row.created_at.isoformat() + "Z"

                # Build short field — null for old rows without ShortBrain data
                short = None
                if row.short_scores is not None:
                    try:
                        short_raw = json.loads(row.short_scores)
                        short_signals = {}
                        for key in SHORT_SIGNAL_ORDER:
                            score = int(short_raw.get(key, 0))
                            max_s = SHORT_SIGNAL_MAX[key]
                            pct   = round(score / max_s * 100) if max_s else 0
                            short_signals[key] = {
                                "score": score,
                                "max":   max_s,
                                "pct":   pct,
                                "label": SHORT_SIGNAL_LABELS[key],
                            }
                        short = {
                            "score":   row.short_total_score or 0,
                            "regime":  row.short_regime or "",
                            "signals": short_signals,
                        }
                    except Exception:
                        short = None

                scans.append({
                    "id":          row.id,
                    "scanned_at":  scanned_at,
                    "total_score": row.total_score,
                    "action":      row.action or "SKIP",
                    "confidence":  _confidence(row.total_score),
                    "layers":      layers,
                    "short":       short,
                })

            result.append({"pair": pair, "scans": scans})
        return result
    finally:
        session.close()
