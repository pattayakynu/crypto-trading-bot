import os
from enum import Enum

FUTURES_MAX_LEVERAGE = int(os.getenv("FUTURES_MAX_LEVERAGE", "2"))
BINANCE_TESTNET = os.getenv("BINANCE_TESTNET", "true").lower() == "true"


class OrderResult(Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ExecutionResult:
    def __init__(
        self,
        status: OrderResult,
        order_id: str = None,
        pair: str = None,
        side: str = None,
        market_type: str = None,
        price: float = 0.0,
        qty: float = 0.0,
        usdt_value: float = 0.0,
        error: str = None,
        raw: dict = None,
    ):
        self.status = status
        self.order_id = order_id
        self.pair = pair
        self.side = side
        self.market_type = market_type
        self.price = price
        self.qty = qty
        self.usdt_value = usdt_value
        self.error = error
        self.raw = raw or {}

    @property
    def success(self) -> bool:
        return self.status == OrderResult.SUCCESS

    def __repr__(self):
        return f"ExecutionResult({self.status.value} {self.side} {self.pair} qty={self.qty} @ {self.price})"


class TradeExecutor:
    def __init__(self, client=None):
        self.client = client  # python-binance Client

    # ── Spot ──────────────────────────────────────────────────────────────────

    def buy_spot(self, pair: str, qty: float) -> ExecutionResult:
        """Place a spot market BUY order."""
        if not self.client:
            return ExecutionResult(OrderResult.SKIPPED, pair=pair, side="BUY", market_type="SPOT",
                                   error="No Binance client")
        try:
            order = self.client.order_market_buy(symbol=pair, quantity=qty)
            fill_price = float(order.get("fills", [{}])[0].get("price", 0)) if order.get("fills") else 0.0
            fill_qty = float(order.get("executedQty", qty))
            return ExecutionResult(
                status=OrderResult.SUCCESS,
                order_id=str(order.get("orderId", "")),
                pair=pair,
                side="BUY",
                market_type="SPOT",
                price=fill_price,
                qty=fill_qty,
                usdt_value=fill_price * fill_qty,
                raw=order,
            )
        except Exception as e:
            return ExecutionResult(OrderResult.FAILED, pair=pair, side="BUY", market_type="SPOT", error=str(e))

    def sell_spot(self, pair: str, qty: float) -> ExecutionResult:
        """Place a spot market SELL order to close a LONG position."""
        if not self.client:
            return ExecutionResult(OrderResult.SKIPPED, pair=pair, side="SELL", market_type="SPOT",
                                   error="No Binance client")
        try:
            order = self.client.order_market_sell(symbol=pair, quantity=qty)
            fill_price = float(order.get("fills", [{}])[0].get("price", 0)) if order.get("fills") else 0.0
            fill_qty = float(order.get("executedQty", qty))
            return ExecutionResult(
                status=OrderResult.SUCCESS,
                order_id=str(order.get("orderId", "")),
                pair=pair,
                side="SELL",
                market_type="SPOT",
                price=fill_price,
                qty=fill_qty,
                usdt_value=fill_price * fill_qty,
                raw=order,
            )
        except Exception as e:
            return ExecutionResult(OrderResult.FAILED, pair=pair, side="SELL", market_type="SPOT", error=str(e))

    # ── Futures ───────────────────────────────────────────────────────────────

    def set_leverage(self, pair: str, leverage: int = FUTURES_MAX_LEVERAGE) -> bool:
        """Set leverage for a futures pair."""
        if not self.client:
            return False
        try:
            self.client.futures_change_leverage(symbol=pair, leverage=leverage)
            return True
        except Exception:
            return False

    def short_futures(self, pair: str, qty: float, leverage: int = FUTURES_MAX_LEVERAGE) -> ExecutionResult:
        """Open a futures SHORT position (SELL side)."""
        if not self.client:
            return ExecutionResult(OrderResult.SKIPPED, pair=pair, side="SHORT", market_type="FUTURES",
                                   error="No Binance client")
        try:
            self.set_leverage(pair, leverage)
            order = self.client.futures_create_order(
                symbol=pair,
                side="SELL",
                type="MARKET",
                quantity=qty,
                positionSide="SHORT",
            )
            fill_price = float(order.get("avgPrice", 0))
            fill_qty = float(order.get("executedQty", qty))
            return ExecutionResult(
                status=OrderResult.SUCCESS,
                order_id=str(order.get("orderId", "")),
                pair=pair,
                side="SHORT",
                market_type="FUTURES",
                price=fill_price,
                qty=fill_qty,
                usdt_value=fill_price * fill_qty,
                raw=order,
            )
        except Exception as e:
            return ExecutionResult(OrderResult.FAILED, pair=pair, side="SHORT", market_type="FUTURES", error=str(e))

    def close_futures_short(self, pair: str, qty: float) -> ExecutionResult:
        """Close a futures SHORT position (BUY to cover)."""
        if not self.client:
            return ExecutionResult(OrderResult.SKIPPED, pair=pair, side="CLOSE_SHORT", market_type="FUTURES",
                                   error="No Binance client")
        try:
            order = self.client.futures_create_order(
                symbol=pair,
                side="BUY",
                type="MARKET",
                quantity=qty,
                positionSide="SHORT",
                reduceOnly=True,
            )
            fill_price = float(order.get("avgPrice", 0))
            fill_qty = float(order.get("executedQty", qty))
            return ExecutionResult(
                status=OrderResult.SUCCESS,
                order_id=str(order.get("orderId", "")),
                pair=pair,
                side="CLOSE_SHORT",
                market_type="FUTURES",
                price=fill_price,
                qty=fill_qty,
                usdt_value=fill_price * fill_qty,
                raw=order,
            )
        except Exception as e:
            return ExecutionResult(OrderResult.FAILED, pair=pair, side="CLOSE_SHORT", market_type="FUTURES", error=str(e))

    # ── Price fetcher ─────────────────────────────────────────────────────────

    def get_current_price(self, pair: str) -> float:
        """Get latest price for a symbol."""
        if not self.client:
            return 0.0
        try:
            ticker = self.client.get_symbol_ticker(symbol=pair)
            return float(ticker.get("price", 0))
        except Exception:
            return 0.0
