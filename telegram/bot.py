"""
Telegram Bot — Entry Point
==========================
Commands:
  /start    — Resume bot trading
  /stop     — Pause bot trading (open positions stay active)
  /status   — Show bot state and open positions
  /balance  — Show USDT balance from Binance
  /pnl      — Show today's P&L summary
  /trades   — Show last 5 closed trades
  /report   — Request an immediate market report
  /weights  — Show adaptive layer weights
  /settings — Show current configuration

Alerts: automatically forwarded from Redis pub/sub channels.
"""

import os
import logging
from functools import wraps

import redis
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from telegram.ext import Application, CommandHandler

from auth import require_auth
from handlers import (
    cmd_start, cmd_stop, cmd_status,
    cmd_balance, cmd_pnl, cmd_trades,
    cmd_report, cmd_weights, cmd_settings,
)
from alerts import AlertSubscriber

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required")

    allowed_ids: set[int] = {
        int(uid.strip())
        for uid in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",")
        if uid.strip()
    }
    if not allowed_ids:
        log.warning("TELEGRAM_ALLOWED_USER_IDS is empty — all users will be blocked!")

    # Services
    redis_client = redis.from_url(
        os.getenv("REDIS_URL", "redis://localhost:6379"),
        decode_responses=False,
    )

    db_url = os.getenv("DATABASE_URL", "sqlite:///trading.db")
    db_engine = create_engine(db_url)
    db_session = Session(db_engine)

    # Binance client (optional — graceful fallback if no key)
    binance_client = None
    try:
        from binance.client import Client as BinanceClient
        binance_key = os.getenv("BINANCE_API_KEY", "")
        binance_secret = os.getenv("BINANCE_SECRET_KEY", "")
        tld = os.getenv("BINANCE_TLD", "com")
        testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
        if tld == "us":
            testnet = False
        if binance_key:
            binance_client = BinanceClient(binance_key, binance_secret, tld=tld, testnet=testnet)
            log.info("Binance client connected (tld=%s testnet=%s)", tld, testnet)
    except Exception as e:
        log.warning("Binance client unavailable: %s", e)

    # Build Telegram app
    app = Application.builder().token(token).build()

    def make(handler_fn):
        """Wrap a handler with auth + dependency injection."""
        @require_auth(allowed_ids)
        @wraps(handler_fn)
        async def wrapper(update, context):
            return await handler_fn(
                update, context,
                redis_client=redis_client,
                db_session=db_session,
                binance_client=binance_client,
            )
        return wrapper

    # Register command handlers
    commands = [
        ("start",    cmd_start),
        ("stop",     cmd_stop),
        ("status",   cmd_status),
        ("balance",  cmd_balance),
        ("pnl",      cmd_pnl),
        ("trades",   cmd_trades),
        ("report",   cmd_report),
        ("weights",  cmd_weights),
        ("settings", cmd_settings),
    ]
    for cmd_name, handler_fn in commands:
        app.add_handler(CommandHandler(cmd_name, make(handler_fn)))

    log.info("Registered %d command handlers", len(commands))

    # Start Redis alert subscriber (background thread)
    subscriber = AlertSubscriber(redis_client, app.bot, allowed_ids)
    subscriber.start()

    log.info("🤖 Telegram bot starting (polling)...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
