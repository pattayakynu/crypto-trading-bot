import os
from fastapi import APIRouter

router = APIRouter()


def _get_binance():
    from binance.client import Client
    return Client(
        os.getenv("BINANCE_API_KEY", ""),
        os.getenv("BINANCE_SECRET_KEY", ""),
        testnet=os.getenv("BINANCE_TESTNET", "true").lower() == "true",
    )


@router.get("/balance")
def get_balance():
    """Return current USDT balance from Binance."""
    try:
        client = _get_binance()
        account = client.get_account()
        usdt = next((a for a in account["balances"] if a["asset"] == "USDT"), None)
        return {
            "asset": "USDT",
            "free": float(usdt["free"]) if usdt else 0.0,
            "locked": float(usdt["locked"]) if usdt else 0.0,
        }
    except Exception as e:
        return {"asset": "USDT", "free": 0.0, "locked": 0.0, "error": str(e)}
