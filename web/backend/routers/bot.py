import os
import asyncio
import redis as redis_lib
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
KEY_PREFIX = os.getenv("REDIS_KEY_PREFIX", "bot:")


def get_redis():
    return redis_lib.from_url(REDIS_URL, decode_responses=False)


@router.get("/bot/status")
def bot_status():
    """Return whether the trading engine is running or stopped."""
    r = get_redis()
    raw = r.get(f"{KEY_PREFIX}running")
    return {"status": "running" if raw == b"running" else "stopped"}


@router.post("/bot/start")
def bot_start():
    """Send start command to the trading engine via Redis."""
    r = get_redis()
    r.set(f"{KEY_PREFIX}control", "start")
    r.set(f"{KEY_PREFIX}running", "running")
    return {"ok": True, "action": "start"}


@router.post("/bot/stop")
def bot_stop():
    """Send stop command to the trading engine via Redis."""
    r = get_redis()
    r.set(f"{KEY_PREFIX}control", "stop")
    r.set(f"{KEY_PREFIX}running", "stopped")
    return {"ok": True, "action": "stop"}


# Registered directly on app in main.py (no auth — browsers can't send
# custom headers on WebSocket upgrade requests).
async def websocket_events(websocket: WebSocket):
    """Stream Redis pub/sub events to the connected WebSocket client."""
    await websocket.accept()
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)
    pubsub = r.pubsub()
    channels = [
        f"{KEY_PREFIX}trade.opened",
        f"{KEY_PREFIX}trade.closed",
        f"{KEY_PREFIX}signal",
        f"{KEY_PREFIX}alert",
        f"{KEY_PREFIX}report",
    ]
    pubsub.subscribe(*channels)

    loop = asyncio.get_event_loop()
    try:
        while True:
            # Run blocking pubsub.get_message() in a thread so the event loop stays free
            message = await loop.run_in_executor(
                None, lambda: pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            )
            if message and message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pubsub.unsubscribe()
    except Exception:
        pubsub.unsubscribe()
