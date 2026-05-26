import pytest
from unittest.mock import MagicMock, patch
from executor import TradeExecutor, ExecutionResult, OrderResult


def make_executor(client=None):
    return TradeExecutor(client=client)


def make_mock_client():
    return MagicMock()


def spot_buy_response(price=50000.0, qty=0.001):
    return {
        "orderId": 12345,
        "executedQty": str(qty),
        "fills": [{"price": str(price), "qty": str(qty)}],
        "status": "FILLED",
    }


def spot_sell_response(price=51000.0, qty=0.001):
    return {
        "orderId": 12346,
        "executedQty": str(qty),
        "fills": [{"price": str(price), "qty": str(qty)}],
        "status": "FILLED",
    }


def futures_response(price=50000.0, qty=0.001):
    return {
        "orderId": 99999,
        "executedQty": str(qty),
        "avgPrice": str(price),
        "status": "FILLED",
    }


# ── No client (testnet safety) ────────────────────────────────────────────────

def test_buy_spot_no_client_returns_skipped():
    ex = make_executor(client=None)
    result = ex.buy_spot("BTCUSDT", 0.001)
    assert result.status == OrderResult.SKIPPED
    assert not result.success


def test_sell_spot_no_client_returns_skipped():
    ex = make_executor(client=None)
    result = ex.sell_spot("BTCUSDT", 0.001)
    assert result.status == OrderResult.SKIPPED


def test_short_futures_no_client_returns_skipped():
    ex = make_executor(client=None)
    result = ex.short_futures("BTCUSDT", 0.001)
    assert result.status == OrderResult.SKIPPED


def test_close_futures_no_client_returns_skipped():
    ex = make_executor(client=None)
    result = ex.close_futures_short("BTCUSDT", 0.001)
    assert result.status == OrderResult.SKIPPED


# ── Spot BUY ─────────────────────────────────────────────────────────────────

def test_buy_spot_success():
    mock = make_mock_client()
    mock.order_market_buy.return_value = spot_buy_response(50000.0, 0.001)
    ex = make_executor(mock)
    result = ex.buy_spot("BTCUSDT", 0.001)
    assert result.success
    assert result.status == OrderResult.SUCCESS
    assert result.pair == "BTCUSDT"
    assert result.side == "BUY"
    assert result.market_type == "SPOT"
    assert result.price == 50000.0
    assert result.qty == 0.001


def test_buy_spot_failure():
    mock = make_mock_client()
    mock.order_market_buy.side_effect = Exception("Insufficient balance")
    ex = make_executor(mock)
    result = ex.buy_spot("BTCUSDT", 0.001)
    assert result.status == OrderResult.FAILED
    assert "Insufficient" in result.error


# ── Spot SELL ─────────────────────────────────────────────────────────────────

def test_sell_spot_success():
    mock = make_mock_client()
    mock.order_market_sell.return_value = spot_sell_response(51000.0, 0.001)
    ex = make_executor(mock)
    result = ex.sell_spot("BTCUSDT", 0.001)
    assert result.success
    assert result.side == "SELL"
    assert result.price == 51000.0


# ── Futures SHORT ─────────────────────────────────────────────────────────────

def test_short_futures_success():
    mock = make_mock_client()
    mock.futures_change_leverage.return_value = {}
    mock.futures_create_order.return_value = futures_response(50000.0, 0.001)
    ex = make_executor(mock)
    result = ex.short_futures("BTCUSDT", 0.001, leverage=2)
    assert result.success
    assert result.side == "SHORT"
    assert result.market_type == "FUTURES"
    mock.futures_change_leverage.assert_called_once_with(symbol="BTCUSDT", leverage=2)


def test_short_futures_failure():
    mock = make_mock_client()
    mock.futures_change_leverage.return_value = {}
    mock.futures_create_order.side_effect = Exception("Margin insufficient")
    ex = make_executor(mock)
    result = ex.short_futures("BTCUSDT", 0.001)
    assert result.status == OrderResult.FAILED


# ── Close SHORT ───────────────────────────────────────────────────────────────

def test_close_futures_short_success():
    mock = make_mock_client()
    mock.futures_create_order.return_value = futures_response(48000.0, 0.001)
    ex = make_executor(mock)
    result = ex.close_futures_short("BTCUSDT", 0.001)
    assert result.success
    assert result.side == "CLOSE_SHORT"
    # Verify reduceOnly=True was passed
    call_kwargs = mock.futures_create_order.call_args[1]
    assert call_kwargs.get("reduceOnly") is True


# ── Price fetch ───────────────────────────────────────────────────────────────

def test_get_price_with_client():
    mock = make_mock_client()
    mock.get_symbol_ticker.return_value = {"price": "50000.0"}
    ex = make_executor(mock)
    assert ex.get_current_price("BTCUSDT") == 50000.0


def test_get_price_no_client_returns_zero():
    ex = make_executor(client=None)
    assert ex.get_current_price("BTCUSDT") == 0.0


# ── ExecutionResult helpers ───────────────────────────────────────────────────

def test_execution_result_success_property():
    r = ExecutionResult(OrderResult.SUCCESS, pair="BTCUSDT", side="BUY", market_type="SPOT")
    assert r.success is True


def test_execution_result_repr():
    r = ExecutionResult(OrderResult.SUCCESS, pair="BTCUSDT", side="BUY", market_type="SPOT",
                        qty=0.001, price=50000.0)
    assert "SUCCESS" in repr(r)
    assert "BTCUSDT" in repr(r)
