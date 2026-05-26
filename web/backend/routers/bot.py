import os
import json
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
    return {"ok": True, "action": "start"}


@router.post("/bot/stop")
def bot_stop():
    """Send stop command to the trading engine via Redis."""
    r = get_redis()
    r.set(f"{KEY_PREFIX}control", "stop")
    return {"ok": True, "action": "stop"}


@router.websocket("/ws/events")
async def websocket_events(websocket: WebSocket):
    """
    Stream Redis pub/sub events to the connected WebSocket client.
    Frontend connects here to receive real-time trade/signal events.
    """
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
    try:
        for message in pubsub.listen():
            if message["type"] == "message":
                await websocket.send_text(message["data"])
    except WebSocketDisconnect:
        pubsub.unsubscribe()
    except Exception:
        pubsub.unsubscribe()
