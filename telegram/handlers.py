import os
from datetime import datetime, timezone

from telegram import Update
from telegram.ext import ContextTypes
from sqlalchemy.orm import Session

from db import Trade, Position, LayerWeight


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE,
                    redis_client=None, **kwargs):
    """Start the trading engine."""
    if redis_client:
        redis_client.set("bot:control", "start")
    await update.message.reply_text(
        "🟢 *Bot started.*\n"
        "Use /status to see open positions.",
        parse_mode="Markdown"
    )


async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE,
                   redis_client=None, **kwargs):
    """Stop the trading engine gracefully."""
    if redis_client:
        redis_client.set("bot:control", "stop")
    await update.message.reply_text(
        "🔴 *Bot stopped.*\n"
        "No new trades will be opened. Open positions remain active.",
        parse_mode="Markdown"
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     redis_client=None, db_session: Session = None, **kwargs):
    """Show bot state and open positions."""
    raw = redis_client.get("bot:running") if redis_client else None
    state = "🟢 RUNNING" if raw == b"running" else "🔴 STOPPED"

    positions = db_session.query(Position).all() if db_session else []

    lines = [
        f"*Bot status:* {state}",
        f"*Open positions:* {len(positions)}",
    ]
    for p in positions:
        pnl_note = ""
        lines.append(
            f"  • `{p.pair}` {p.side} entry=${p.entry_price:.4f} "
            f"SL=${p.stop_loss:.4f} TP=${p.take_profit:.4f}"
        )

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_balance(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      binance_client=None, **kwargs):
    """Show current USDT balance from Binance."""
    if not binance_client:
        await update.message.reply_text("⚠️ Binance client not available.")
        return
    account = binance_client.get_account()
    usdt = next((a for a in account["balances"] if a["asset"] == "USDT"), None)
    free = float(usdt["free"]) if usdt else 0.0
    locked = float(usdt["locked"]) if usdt else 0.0
    await update.message.reply_text(
        f"💰 *USDT Balance*\n"
        f"Free: `${free:.2f}`\n"
        f"In orders: `${locked:.2f}`\n"
        f"Total: `${free + locked:.2f}`",
        parse_mode="Markdown"
    )


async def cmd_pnl(update: Update, context: ContextTypes.DEFAULT_TYPE,
                  db_session: Session = None, **kwargs):
    """Show today's P&L summary."""
    if not db_session:
        await update.message.reply_text("⚠️ DB not available.")
        return

    today = _now().replace(hour=0, minute=0, second=0, microsecond=0)
    trades = db_session.query(Trade).filter(
        Trade.created_at >= today,
        Trade.pnl.isnot(None)
    ).all()

    total_pnl = sum(t.pnl for t in trades)
    wins = sum(1 for t in trades if t.pnl > 0)
    losses = sum(1 for t in trades if t.pnl <= 0)
    win_rate = (wins / len(trades) * 100) if trades else 0

    sign = "+" if total_pnl >= 0 else ""
    icon = "📈" if total_pnl >= 0 else "📉"
    text = (
        f"{icon} *P&L Today*\n"
        f"Total: `{sign}${total_pnl:.2f}`\n"
        f"Trades: {len(trades)} (✅ {wins} / ❌ {losses})\n"
        f"Win rate: `{win_rate:.0f}%`"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_trades(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     db_session: Session = None, **kwargs):
    """Show last 5 closed trades."""
    if not db_session:
        await update.message.reply_text("⚠️ DB not available.")
        return

    trades = (
        db_session.query(Trade)
        .filter(Trade.pnl.isnot(None))
        .order_by(Trade.id.desc())
        .limit(5)
        .all()
    )

    if not trades:
        await update.message.reply_text("No closed trades yet.")
        return

    lines = ["*Last 5 trades:*"]
    for t in trades:
        sign = "+" if t.pnl > 0 else ""
        icon = "✅" if t.pnl > 0 else "❌"
        lines.append(f"{icon} `{t.pair}` {sign}${t.pnl:.2f}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_report(update: Update, context: ContextTypes.DEFAULT_TYPE,
                     redis_client=None, **kwargs):
    """Trigger an immediate market report."""
    if redis_client:
        redis_client.publish("bot:control", '{"action": "report_now"}')
    await update.message.reply_text(
        "📊 Report generation triggered. Will arrive shortly.",
    )


async def cmd_weights(update: Update, context: ContextTypes.DEFAULT_TYPE,
                      db_session: Session = None, **kwargs):
    """Show current adaptive layer weights."""
    if not db_session:
        await update.message.reply_text("⚠️ DB not available.")
        return

    rows = db_session.query(LayerWeight).all()
    if not rows:
        await update.message.reply_text("No weights found.")
        return

    lines = ["*Layer Weights:*"]
    for row in rows:
        bar = "█" * int(row.weight * 5)
        lines.append(f"`{row.name:<12}` {row.weight:.2f} {bar}")

    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")


async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE, **kwargs):
    """Show current bot settings."""
    keys = [
        "MAX_POSITIONS", "STOP_LOSS_PCT", "FUTURES_MAX_LEVERAGE",
        "MIN_CONVICTION_SCORE", "SCAN_INTERVAL_SECONDS", "INITIAL_CAPITAL",
    ]
    lines = ["*Bot Settings:*"]
    for k in keys:
        v = os.getenv(k, "—")
        lines.append(f"`{k}`: {v}")
    await update.message.reply_text("\n".join(lines), parse_mode="Markdown")
