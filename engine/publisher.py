import json
import os
import redis

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
REDIS_KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "bot:")

# Channel names (prefixed)
CHANNEL_SIGNAL = f"{REDIS_KEY_PREFIX}signal"           # New conviction signal
CHANNEL_TRADE_OPENED = f"{REDIS_KEY_PREFIX}trade.opened"
CHANNEL_TRADE_CLOSED = f"{REDIS_KEY_PREFIX}trade.closed"
CHANNEL_POSITION_UPDATE = f"{REDIS_KEY_PREFIX}position.update"
CHANNEL_REPORT = f"{REDIS_KEY_PREFIX}report"            # Market report (4x/day)
CHANNEL_ALERT = f"{REDIS_KEY_PREFIX}alert"              # Critical alerts


class EventPublisher:
    def __init__(self, redis_client=None):
        self._client = redis_client

    @property
    def client(self):
        if self._client is None:
            self._client = redis.from_url(REDIS_URL, decode_responses=True)
        return self._client

    def _publish(self, channel: str, payload: dict) -> int:
        """Publish a JSON payload to a Redis channel. Returns subscriber count."""
        try:
            message = json.dumps(payload, default=str)
            return self.client.publish(channel, message)
        except Exception:
            return 0

    def publish_signal(self, pair: str, score: int, action: str, confidence: str, reasons: list[str]) -> int:
        return self._publish(CHANNEL_SIGNAL, {
            "type": "signal",
            "pair": pair,
            "score": score,
            "action": action,
            "confidence": confidence,
            "reasons": reasons,
        })

    def publish_trade_opened(
        self,
        pair: str,
        side: str,
        market_type: str,
        entry_price: float,
        qty: float,
        usdt_value: float,
        stop_loss: float,
        take_profit: float,
        conviction_score: int,
    ) -> int:
        return self._publish(CHANNEL_TRADE_OPENED, {
            "type": "trade_opened",
            "pair": pair,
            "side": side,
            "market_type": market_type,
            "entry_price": entry_price,
            "qty": qty,
            "usdt_value": usdt_value,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "conviction_score": conviction_score,
        })

    def publish_trade_closed(
        self,
        pair: str,
        side: str,
        market_type: str,
        entry_price: float,
        exit_price: float,
        qty: float,
        pnl: float,
        reason: str,   # "stop_loss" | "take_profit" | "trailing_stop" | "manual"
    ) -> int:
        return self._publish(CHANNEL_TRADE_CLOSED, {
            "type": "trade_closed",
            "pair": pair,
            "side": side,
            "market_type": market_type,
            "entry_price": entry_price,
            "exit_price": exit_price,
            "qty": qty,
            "pnl": pnl,
            "reason": reason,
        })

    def publish_position_update(self, pair: str, current_price: float, pnl_unrealized: float, trailing_stop_active: bool) -> int:
        return self._publish(CHANNEL_POSITION_UPDATE, {
            "type": "position_update",
            "pair": pair,
            "current_price": current_price,
            "pnl_unrealized": pnl_unrealized,
            "trailing_stop_active": trailing_stop_active,
        })

    def publish_report(self, report_text: str, report_type: str = "market") -> int:
        return self._publish(CHANNEL_REPORT, {
            "type": "report",
            "report_type": report_type,
            "content": report_text,
        })

    def publish_alert(self, level: str, message: str, data: dict = None) -> int:
        """level: INFO | WARNING | CRITICAL"""
        return self._publish(CHANNEL_ALERT, {
            "type": "alert",
            "level": level,
            "message": message,
            "data": data or {},
        })
