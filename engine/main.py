"""
Trading Bot Main Loop
=====================
Orchestrates the full signal pipeline every SCAN_INTERVAL_SECONDS:

  [Manipulation Filter (Tầng 0)]
       ↓ CLEAN
  [6-Layer Conviction Scorer]
       ↓ score >= 55
  [Dual LLM Advisor (Claude + DeepSeek)]
       ↓ both agree BUY
  [Risk Manager → position size, SL, TP]
       ↓
  [Trade Executor → Binance Spot/Futures]
       ↓
  [Redis Publisher → Telegram/Dashboard notified]

Position monitor runs every 60s (separate job):
  [Check SL / TP / Trailing Stop for open positions]
  [Close if triggered → record PnL → update adaptive weights]

Reports: 07:00 / 12:00 / 17:00 / 22:00 UTC
"""

import os
import json
import logging
from datetime import datetime, timezone

from dotenv import load_dotenv
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy.orm import sessionmaker

# Internal modules
from db import get_engine, init_db, Position, Trade, SignalLog
from manipulator import ManipulationFilter, ManipulationResult
from whale_tracker import WhaleTracker
from macro import MacroContext
from fiat_flow import FiatFlowTracker
from btc_lead import BtcLeadSignal
from strategy import TaStrategy
from social import SocialSignal
from scorer import ConvictionScorer, LayerScores
from llm_advisor import LlmAdvisor
from risk import RiskManager
from executor import TradeExecutor
from publisher import EventPublisher
from reporter import MarketReporter
from adaptive import AdaptiveLearner

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
SCAN_INTERVAL = int(os.getenv("SCAN_INTERVAL_SECONDS", "300"))
MIN_VOLUME_USDT = float(os.getenv("MIN_VOLUME_USDT", "1_000_000"))
INITIAL_CAPITAL = float(os.getenv("INITIAL_CAPITAL", "100"))
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "2"))

# Watchlist — top 5 vốn hóa lớn nhất, thanh khoản tốt nhất
WATCHLIST = [
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "ADAUSDT",
]

# Futures SHORT threshold: score ≤ 30 + bearish macro/BTC → mở short 2x
SHORT_CONVICTION_THRESHOLD = int(os.getenv("SHORT_CONVICTION_THRESHOLD", "30"))
# Max % equity cho futures short (nhỏ hơn spot vì dùng đòn bẩy)
MAX_SHORT_POSITION_PCT = 0.25


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── Bootstrap ─────────────────────────────────────────────────────────────────

def bootstrap():
    """Initialize all services. Returns (binance_client, session_factory, services_dict)."""
    from binance.client import Client as BinanceClient

    binance_key = os.getenv("BINANCE_API_KEY", "")
    binance_secret = os.getenv("BINANCE_SECRET_KEY", "")
    tld = os.getenv("BINANCE_TLD", "com")          # "us" for Binance.US servers
    testnet = os.getenv("BINANCE_TESTNET", "true").lower() == "true"
    proxy_url = os.getenv("BINANCE_PROXY", "")     # e.g. socks5h://user:pass@host:port
    # Binance.US has no testnet — force live mode
    if tld == "us":
        testnet = False

    client = None
    if binance_key:
        try:
            kwargs = {"tld": tld, "testnet": testnet}
            if proxy_url:
                kwargs["requests_params"] = {"proxies": {"http": proxy_url, "https": proxy_url}}
                log.info("Using proxy: %s", proxy_url.split("@")[-1])  # log host only, not credentials
            client = BinanceClient(binance_key, binance_secret, **kwargs)
            log.info("Binance client connected (tld=%s testnet=%s)", tld, testnet)
        except Exception as e:
            log.warning("Binance client unavailable — running in dry-run mode: %s", e)
    else:
        log.warning("No Binance API key — running in dry-run mode")

    engine = get_engine()
    init_db(engine)
    Session = sessionmaker(bind=engine)

    services = {
        "manipulator": ManipulationFilter(),
        "whale": WhaleTracker(client=client),
        "macro": MacroContext(),
        "fiat_flow": FiatFlowTracker(),
        "btc_lead": BtcLeadSignal(client=client),
        "strategy": TaStrategy(),
        "social": SocialSignal(),
        "llm": LlmAdvisor(),
        "executor": TradeExecutor(client=client),
        "publisher": EventPublisher(),
        "reporter": MarketReporter(),
    }

    return client, Session, services


# ── Signal pipeline ───────────────────────────────────────────────────────────

def run_signal_pipeline(pair: str, session, services: dict, client) -> dict:
    """
    Full pipeline for one pair. Returns result dict with action taken.
    """
    manipulator: ManipulationFilter = services["manipulator"]
    whale: WhaleTracker = services["whale"]
    macro: MacroContext = services["macro"]
    fiat: FiatFlowTracker = services["fiat_flow"]
    btc: BtcLeadSignal = services["btc_lead"]
    ta: TaStrategy = services["strategy"]
    social: SocialSignal = services["social"]
    llm: LlmAdvisor = services["llm"]
    executor: TradeExecutor = services["executor"]
    publisher: EventPublisher = services["publisher"]

    learner = AdaptiveLearner(session)
    if learner.is_blacklisted(pair):
        return {"pair": pair, "action": "BLACKLISTED"}

    # ── Tầng 0: Manipulation gate ──────────────────────────────────────────
    try:
        ticker = client.get_ticker(symbol=pair) if client else {}
    except Exception:
        ticker = {}
    price_change = float(ticker.get("priceChangePercent", 0))
    current_price = float(ticker.get("lastPrice", 0))

    # BTC 24h change: for BTCUSDT pair use its own ticker (already fetched above).
    # For other pairs use BtcLeadSignal.get_btc_change_pct() which tries Binance
    # then falls back to CoinGecko — so geo-blocking can't permanently zero this out.
    if pair == "BTCUSDT":
        btc_change = price_change
    else:
        btc_change = btc.get_btc_change_pct()
    spot_ratio = btc.get_spot_futures_ratio("BTCUSDT")

    manip_result = manipulator.check_btc_pump(btc_change, spot_ratio)
    if manip_result == ManipulationResult.FAKE_PUMP:
        log.info("[%s] SKIP — FAKE_PUMP detected (BTC futures-driven)", pair)
        return {"pair": pair, "action": "SKIP_FAKE_PUMP"}

    # ── Tầng 1: Whale ─────────────────────────────────────────────────────
    whale_score = 0
    try:
        funding = whale.get_funding_rate(pair)
        oi_change = whale.get_open_interest_change(pair)
        whale_score = whale.total_score(
            outflow_pct_24h=0.0,   # TODO: needs exchange flow API
            funding_rate=funding,
            price_change_pct=price_change,
            oi_change_pct=oi_change,
        )
    except Exception:
        pass

    # ── Tầng 2: Macro ─────────────────────────────────────────────────────
    macro_score = macro.get_macro_score(crypto_change_pct=price_change)

    # ── Tầng 3: Fiat Flow ──────────────────────────────────────────────────
    fiat_score = 0
    try:
        transfers = fiat.get_recent_whale_transfers()
        fiat_score = fiat.total_score(
            current_volume=float(ticker.get("quoteVolume", 0)),
            avg_volume_24h=MIN_VOLUME_USDT * 10,  # rough baseline
            transfers=transfers,
        )
    except Exception:
        pass

    # ── Tầng 4: BTC Lead ──────────────────────────────────────────────────
    btc_lead_score = btc.total_score(
        btc_change_pct=btc_change,
        spot_futures_ratio=spot_ratio,
        alt_change_pct=price_change if pair != "BTCUSDT" else 0.0,
    )

    # ── Tầng 5: TA ────────────────────────────────────────────────────────
    ta_score = 0
    try:
        import pandas as pd
        klines = client.get_klines(symbol=pair, interval="1h", limit=100) if client else []
        if klines:
            df = pd.DataFrame(klines, columns=[
                "open_time", "open", "high", "low", "close", "volume",
                "close_time", "quote_volume", "trades", "taker_buy_base",
                "taker_buy_quote", "ignore"
            ])
            for col in ["open", "high", "low", "close", "volume"]:
                df[col] = pd.to_numeric(df[col])
            ta_score = ta.get_score_from_df(df)
    except Exception:
        pass

    # ── Tầng 6: Social ────────────────────────────────────────────────────
    # Fear&Greed (alternative.me) + CoinGecko sentiment — không cần API key
    # CryptoPanic / LunarCrush là bonus nếu có key
    social_score = 0
    try:
        social_score = social.get_social_score(pair)
    except Exception:
        pass

    # ── Conviction Score ──────────────────────────────────────────────────
    weights = learner.get_weights()
    scorer = ConvictionScorer(layer_weights=weights)
    layer_scores = LayerScores(
        whale=whale_score,
        macro=macro_score,
        fiat_flow=fiat_score,
        btc_lead=btc_lead_score,
        ta=ta_score,
        social=social_score,
    )
    conviction = scorer.score(layer_scores)

    # Log signal
    session.add(SignalLog(
        pair=pair,
        total_score=conviction.total_score,
        layer_scores=json.dumps(layer_scores.as_dict()),
        action=conviction.action,
    ))
    session.commit()

    publisher.publish_signal(
        pair=pair,
        score=conviction.total_score,
        action=conviction.action,
        confidence=conviction.confidence,
        reasons=conviction.reasons,
    )

    log.info("[%s] Score=%d action=%s confidence=%s",
             pair, conviction.total_score, conviction.action, conviction.confidence)

    # ── Xác định hướng giao dịch ─────────────────────────────────────────
    # SHORT: score thấp + macro bearish + BTC dẫn xuống + TA bearish
    is_bearish_short = (
        conviction.total_score <= SHORT_CONVICTION_THRESHOLD
        and btc_lead_score <= 3    # BTC đang dẫn xuống (max 20)
        and macro_score <= 5       # Macro bearish: DXY tăng (max 20)
        and ta_score <= 3          # TA bearish: RSI cao, MACD giảm (max 10)
    )

    if not conviction.should_trade and not is_bearish_short:
        return {"pair": pair, "action": conviction.action, "score": conviction.total_score}

    trade_side = "LONG" if conviction.should_trade else "SHORT"

    # ── LLM Dual Analysis (chỉ cho LONG — SHORT dùng rule-based) ─────────
    if trade_side == "LONG":
        llm_result = llm.analyze(
            symbol=pair,
            conviction_score=conviction.total_score,
            layer_scores=layer_scores.as_dict(),
            price_change_pct=price_change,
            reasons=conviction.reasons,
        )
        if llm_result["disagreement_skipped"]:
            log.info("[%s] SKIP — LLM disagreement", pair)
            return {"pair": pair, "action": "SKIP_LLM_DISAGREEMENT", "score": conviction.total_score}

    # ── Position Limit ────────────────────────────────────────────────────
    equity = _get_equity(session)
    rm = RiskManager(equity=equity)

    open_count = session.query(Position).count()
    if not rm.is_position_allowed(open_count):
        log.info("[%s] SKIP — max positions (%d) reached", pair, MAX_POSITIONS)
        return {"pair": pair, "action": "SKIP_MAX_POSITIONS"}

    # ── Drawdown Guard ────────────────────────────────────────────────────
    drawdown = learner.check_drawdown(equity)
    if drawdown["halted"]:
        log.warning("DRAWDOWN GUARD triggered (%.1f%% from peak $%.2f)",
                    drawdown["drawdown_pct"] * 100, drawdown["peak"])
        publisher.publish_alert("CRITICAL", f"Drawdown guard triggered: {drawdown['drawdown_pct']*100:.1f}%", drawdown)
        return {"pair": pair, "action": "SKIP_DRAWDOWN_GUARD"}

    # ── Execute SPOT LONG ─────────────────────────────────────────────────
    if trade_side == "LONG":
        size = rm.calc_position_size(conviction.total_score, conviction.confidence)
        if size == 0:
            return {"pair": pair, "action": "SKIP_EQUITY_TOO_SMALL"}

        qty = rm.calc_qty(size, current_price)
        sl = rm.calc_stop_loss(current_price, side="LONG")
        tp = rm.calc_take_profit(current_price, conviction.confidence, side="LONG")

        result = services["executor"].buy_spot(pair, qty)
        if not result.success:
            log.error("[%s] BUY FAILED: %s", pair, result.error)
            return {"pair": pair, "action": "EXEC_FAILED", "error": result.error}

        fill_price = result.price or current_price
        position = Position(
            pair=pair, market_type="SPOT", side="LONG",
            entry_price=fill_price, qty=result.qty,
            usdt_value=fill_price * result.qty,
            stop_loss=rm.calc_stop_loss(fill_price, "LONG"),
            take_profit=rm.calc_take_profit(fill_price, conviction.confidence, "LONG"),
            trailing_stop_active=False, highest_price=fill_price,
            conviction_score=conviction.total_score,
        )
        session.add(position)
        session.commit()

        publisher.publish_trade_opened(
            pair=pair, side="LONG", market_type="SPOT",
            entry_price=fill_price, qty=result.qty,
            usdt_value=fill_price * result.qty,
            stop_loss=position.stop_loss, take_profit=position.take_profit,
            conviction_score=conviction.total_score,
        )
        log.info("[%s] LONG OPENED (SPOT): qty=%.6f @ %.4f | SL=%.4f TP=%.4f",
                 pair, result.qty, fill_price, position.stop_loss, position.take_profit)
        return {"pair": pair, "action": "BUY_OPENED", "price": fill_price, "qty": result.qty}

    # ── Execute FUTURES SHORT ─────────────────────────────────────────────
    else:
        # Futures short: tối đa 25% equity (nhỏ hơn spot vì có đòn bẩy 2x)
        size = max(10.0, min(equity * MAX_SHORT_POSITION_PCT, equity * MAX_SHORT_POSITION_PCT))
        qty = rm.calc_qty(size, current_price)

        sl = rm.calc_stop_loss(current_price, side="SHORT")   # 5% trên entry
        tp = rm.calc_take_profit(current_price, "MEDIUM", side="SHORT")  # 5% dưới entry

        result = services["executor"].short_futures(pair, qty, leverage=2)
        if not result.success:
            log.error("[%s] SHORT FAILED: %s", pair, result.error)
            return {"pair": pair, "action": "EXEC_FAILED", "error": result.error}

        fill_price = result.price or current_price
        position = Position(
            pair=pair, market_type="FUTURES", side="SHORT",
            entry_price=fill_price, qty=result.qty,
            usdt_value=fill_price * result.qty,
            stop_loss=rm.calc_stop_loss(fill_price, "SHORT"),
            take_profit=rm.calc_take_profit(fill_price, "MEDIUM", "SHORT"),
            trailing_stop_active=False, highest_price=fill_price,
            conviction_score=conviction.total_score,
        )
        session.add(position)
        session.commit()

        publisher.publish_trade_opened(
            pair=pair, side="SHORT", market_type="FUTURES",
            entry_price=fill_price, qty=result.qty,
            usdt_value=fill_price * result.qty,
            stop_loss=position.stop_loss, take_profit=position.take_profit,
            conviction_score=conviction.total_score,
        )
        log.info("[%s] SHORT OPENED (FUTURES 2x): qty=%.6f @ %.4f | SL=%.4f TP=%.4f",
                 pair, result.qty, fill_price, position.stop_loss, position.take_profit)
        return {"pair": pair, "action": "SHORT_OPENED", "price": fill_price, "qty": result.qty}


# ── Position monitor ──────────────────────────────────────────────────────────

def monitor_positions(session, services: dict, client):
    """Check all open positions against SL/TP/trailing stop."""
    executor: TradeExecutor = services["executor"]
    publisher: EventPublisher = services["publisher"]
    learner = AdaptiveLearner(session)

    positions = session.query(Position).all()
    if not positions:
        return

    for pos in positions:
        try:
            price = executor.get_current_price(pos.pair)
            if price <= 0:
                continue

            rm = RiskManager(equity=_get_equity(session), stop_loss_pct=(pos.stop_loss / pos.entry_price))

            # Update trailing stop activation
            if not pos.trailing_stop_active:
                if rm.should_activate_trailing_stop(pos.entry_price, price, pos.side):
                    pos.trailing_stop_active = True
                    log.info("[%s] Trailing stop activated at %.4f", pos.pair, price)

            # Update highest price
            if pos.side == "LONG" and price > pos.highest_price:
                pos.highest_price = price
            elif pos.side == "SHORT" and price < pos.highest_price:
                pos.highest_price = price

            session.commit()

            # Determine exit reason
            exit_reason = None
            if rm.should_stop_loss(pos.entry_price, price, pos.stop_loss, pos.side):
                exit_reason = "stop_loss"
            elif rm.should_take_profit(price, pos.take_profit, pos.side):
                exit_reason = "take_profit"
            elif rm.should_trailing_stop(price, pos.highest_price, pos.trailing_stop_active, pos.side):
                exit_reason = "trailing_stop"

            if exit_reason:
                _close_position(pos, price, exit_reason, session, services, learner)

        except Exception as e:
            log.error("[%s] Monitor error: %s", pos.pair, e)


def _close_position(pos, exit_price: float, reason: str, session, services: dict, learner: AdaptiveLearner):
    """Close a position, record trade, update adaptive weights."""
    executor: TradeExecutor = services["executor"]
    publisher: EventPublisher = services["publisher"]
    rm = RiskManager(equity=_get_equity(session))

    # Execute close
    if pos.market_type == "SPOT":
        result = executor.sell_spot(pos.pair, pos.qty)
    else:
        result = executor.close_futures_short(pos.pair, pos.qty)

    if not result.success:
        log.error("[%s] CLOSE FAILED: %s", pos.pair, result.error)
        return

    actual_exit = result.price or exit_price
    pnl = rm.calc_pnl(pos.entry_price, actual_exit, pos.qty, pos.side)

    # Record closed trade
    trade = Trade(
        pair=pos.pair,
        side=pos.side,
        price=actual_exit,
        qty=pos.qty,
        usdt_value=actual_exit * pos.qty,
        pnl=pnl,
        conviction_score=pos.conviction_score,
        market_type=pos.market_type,
    )
    session.add(trade)
    session.delete(pos)
    session.commit()

    # Update adaptive weights
    try:
        from scorer import LayerScores
        import json
        log_entry = session.query(SignalLog).filter_by(pair=pos.pair).order_by(SignalLog.id.desc()).first()
        if log_entry:
            layer_scores = json.loads(log_entry.layer_scores)
            learner.update_weights_after_trade(layer_scores, pnl)
    except Exception:
        pass

    # Blacklist on loss
    if pnl < 0:
        learner.blacklist_pair(pos.pair, f"Loss {pnl:.2f} USDT on {reason}", hours=24)

    publisher.publish_trade_closed(
        pair=pos.pair, side=pos.side, market_type=pos.market_type,
        entry_price=pos.entry_price, exit_price=actual_exit,
        qty=pos.qty, pnl=pnl, reason=reason,
    )

    log.info("[%s] CLOSED (%s): pnl=%.4f USDT @ %.4f", pos.pair, reason, pnl, actual_exit)


# ── Scheduled report ──────────────────────────────────────────────────────────

def send_scheduled_report(session, services: dict, client, force: bool = False):
    """Build and publish the 4x daily market report."""
    reporter: MarketReporter = services["reporter"]
    publisher: EventPublisher = services["publisher"]

    now = _now()
    if not force and not reporter.should_send_report(now.hour, now.minute):
        return

    try:
        btc_ticker = client.get_ticker(symbol="BTCUSDT") if client else {}
        eth_ticker = client.get_ticker(symbol="ETHUSDT") if client else {}
        # Lấy balance thực từ Binance, fallback về DB equity
        equity = _get_equity(session)
        if client:
            try:
                account = client.get_account()
                usdt = next((a for a in account["balances"] if a["asset"] == "USDT"), None)
                if usdt:
                    equity = float(usdt["free"]) + float(usdt["locked"])
            except Exception:
                pass
        open_positions = session.query(Position).count()

        from sqlalchemy import func
        from db import Trade
        from datetime import date
        today_pnl = session.query(func.sum(Trade.pnl)).filter(
            Trade.created_at >= datetime.combine(date.today(), datetime.min.time())
        ).scalar() or 0.0

        # Lấy market cap + BTC dominance từ CoinGecko (free, no key)
        total_mcap_b = 0.0
        btc_dominance = 0.0
        try:
            import httpx as _httpx
            cg = _httpx.get(
                "https://api.coingecko.com/api/v3/global",
                timeout=8,
            )
            cg_data = cg.json().get("data", {})
            total_mcap_b = cg_data.get("total_market_cap", {}).get("usd", 0) / 1e9
            btc_dominance = cg_data.get("market_cap_percentage", {}).get("btc", 0)
        except Exception as cg_err:
            log.warning("CoinGecko fetch failed: %s", cg_err)

        market_data = {
            "btc_price": float(btc_ticker.get("lastPrice", 0)),
            "btc_change_24h": float(btc_ticker.get("priceChangePercent", 0)),
            "eth_change_24h": float(eth_ticker.get("priceChangePercent", 0)),
            "total_market_cap_b": total_mcap_b,
            "btc_dominance": btc_dominance,
            "open_positions": open_positions,
            "total_pnl": today_pnl,
            "equity": equity,
        }

        report = reporter.build_report(market_data)
        publisher.publish_report(report)
        log.info("Market report sent at %s", now.strftime("%H:%M UTC"))
    except Exception as e:
        log.error("Report failed: %s", e)


def _get_equity(session) -> float:
    """Get latest equity from performance log, fallback to INITIAL_CAPITAL."""
    from db import Performance
    latest = session.query(Performance).order_by(Performance.id.desc()).first()
    return latest.equity if latest else INITIAL_CAPITAL


# ── Main entry point ──────────────────────────────────────────────────────────

def main():
    log.info("🚀 Trading Bot starting...")
    client, Session, services = bootstrap()
    session = Session()

    learner = AdaptiveLearner(session)
    learner.record_equity(INITIAL_CAPITAL)

    # Mark bot as running in Redis so dashboard shows correct status
    import redis as _redis
    KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "bot:")
    try:
        _r = _redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379"))
        _r.set(f"{KEY_PREFIX}running", "running")
    except Exception:
        _r = None

    scheduler = BlockingScheduler(timezone="UTC")

    # Full scan every SCAN_INTERVAL seconds
    def scan_job():
        log.info("── Scan cycle started ──")
        for pair in WATCHLIST:
            try:
                result = run_signal_pipeline(pair, session, services, client)
                if result.get("action") == "BUY_OPENED":
                    break  # One trade per scan cycle
            except Exception as e:
                log.error("[%s] Pipeline error: %s", pair, e)

    # Position monitor every 60s
    def monitor_job():
        monitor_positions(session, services, client)

    # Report check every minute (sends on schedule OR when /report command sets flag)
    def report_job():
        forced = False
        if _r:
            try:
                forced = bool(_r.getdel(f"{KEY_PREFIX}force_report"))
            except Exception:
                pass
        send_scheduled_report(session, services, client, force=forced)

    scheduler.add_job(scan_job, "interval", seconds=SCAN_INTERVAL, id="scan")
    scheduler.add_job(monitor_job, "interval", seconds=60, id="monitor")
    scheduler.add_job(report_job, "interval", seconds=60, id="report")

    log.info("Scheduler started: scan every %ds, monitor every 60s, reports at %s",
             SCAN_INTERVAL, ", ".join(services["reporter"].REPORT_TIMES if hasattr(services["reporter"], "REPORT_TIMES") else []))

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        log.info("Bot stopped.")
    finally:
        session.close()


if __name__ == "__main__":
    main()
