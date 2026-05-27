import json
import threading
import asyncio
import logging

log = logging.getLogger(__name__)


def format_alert(event: dict) -> str | None:
    """
    Convert a Redis event dict into a Telegram-formatted message.
    Returns None for unknown event types (no message sent).
    """
    e = event.get("type") or event.get("event")

    if e == "trade_opened":
        side = event.get("side", "BUY")
        icon = "📈" if side == "LONG" or side == "BUY" else "📉"
        return (
            f"{icon} *Trade Opened*\n"
            f"Pair: `{event.get('pair')}`\n"
            f"Side: `{side}`\n"
            f"Entry: `${float(event.get('entry_price', event.get('price', 0))):.4f}`\n"
            f"SL: `${float(event.get('stop_loss', event.get('sl', 0))):.4f}` | "
            f"TP: `${float(event.get('take_profit', event.get('tp', 0))):.4f}`\n"
            f"Conviction: `{event.get('conviction_score', '—')}/100`"
        )

    if e == "trade_closed":
        pnl = float(event.get("pnl", 0))
        icon = "✅" if pnl > 0 else "❌"
        sign = "+" if pnl >= 0 else ""
        reason = event.get("reason", "")
        reason_map = {
            "take_profit": "Take Profit 🎯",
            "stop_loss": "Stop Loss 🛑",
            "trailing_stop": "Trailing Stop 📎",
            "manual": "Manual ✋",
        }
        reason_label = reason_map.get(reason, reason)
        return (
            f"{icon} *Trade Closed* — {reason_label}\n"
            f"Pair: `{event.get('pair')}`\n"
            f"Exit: `${float(event.get('exit_price', event.get('price', 0))):.4f}`\n"
            f"P&L: `{sign}${pnl:.2f} USDT`"
        )

    if e == "signal":
        action = event.get("action", "SKIP")
        if action != "BUY":
            return None  # Only notify on actual BUY signals
        return (
            f"🔔 *Signal: {action}*\n"
            f"Pair: `{event.get('pair')}`\n"
            f"Score: `{event.get('score')}/100` ({event.get('confidence')})"
        )

    if e == "alert":
        level = event.get("level", "INFO")
        msg = event.get("message", "")
        icon = {"INFO": "ℹ️", "WARNING": "⚠️", "CRITICAL": "🚨"}.get(level, "📢")
        return f"{icon} *{level}*\n{msg}"

    if e == "report":
        return event.get("content", "")

    # Legacy event name support
    if e == "low_balance":
        return f"⚠️ *Low balance:* `${float(event.get('balance', 0)):.2f} USDT` — bot may pause."

    if e == "drawdown_guard":
        eq = float(event.get("equity", 0))
        dd = float(event.get("drawdown_pct", 0))
        return (
            f"🚨 *Drawdown Guard Triggered!*\n"
            f"Equity: `${eq:.2f}` | Drawdown: `{dd:.1f}%`\n"
            f"Bot stopped to protect capital."
        )

    if e == "bot_started":
        return "🟢 *Bot started.*"

    if e == "bot_stopped":
        return "🔴 *Bot stopped.*"

    return None


class AlertSubscriber:
    """
    Runs a background thread that subscribes to Redis pub/sub channels
    and forwards formatted messages to Telegram.
    """

    CHANNELS = [
        "bot:trade.opened",
        "bot:trade.closed",
        "bot:signal",
        "bot:alert",
        "bot:report",
    ]

    def __init__(self, redis_client, bot, allowed_ids: set[int], key_prefix: str = "bot:"):
        self.redis = redis_client
        self.bot = bot
        self.allowed_ids = allowed_ids
        self.key_prefix = key_prefix
        self._thread = None
        self._loop = None

    def start(self):
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(target=self._listen, daemon=True, name="alert-subscriber")
        self._thread.start()
        log.info("Alert subscriber started, listening on %d channels", len(self.CHANNELS))

    def _listen(self):
        asyncio.set_event_loop(self._loop)
        pubsub = self.redis.pubsub()
        pubsub.subscribe(*self.CHANNELS)
        log.info("Subscribed to Redis channels: %s", self.CHANNELS)

        for message in pubsub.listen():
            if message["type"] != "message":
                continue
            try:
                data = message["data"]
                if isinstance(data, bytes):
                    data = data.decode()
                event = json.loads(data)
                text = format_alert(event)
                if text:
                    self._send_to_all(text)
            except Exception as exc:
                log.error("Alert processing error: %s", exc)

    def _send_to_all(self, text: str):
        # httpx sync: gọi Telegram REST API trực tiếp từ background thread.
        import httpx
        url = f"https://api.telegram.org/bot{self.bot.token}/sendMessage"
        for uid in self.allowed_ids:
            try:
                httpx.post(
                    url,
                    json={"chat_id": uid, "text": text, "parse_mode": "Markdown"},
                    timeout=10,
                )
            except Exception as e:
                log.error("Failed to send Telegram message to %d: %s", uid, e)
