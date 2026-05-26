import os
from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

WEB_API_KEY = os.getenv("WEB_API_KEY", "change-me-secret")

app = FastAPI(
    title="Crypto Trading Bot API",
    description="REST API for the crypto trading bot dashboard",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def verify_api_key(x_api_key: str = Header(None)):
    if x_api_key != WEB_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# Import and register routers
from routers import balance, trades, positions, performance, config as config_router
from routers import bot as bot_router

_protected = {"dependencies": [Depends(verify_api_key)]}

app.include_router(balance.router,       prefix="/api", **_protected)
app.include_router(trades.router,        prefix="/api", **_protected)
app.include_router(positions.router,     prefix="/api", **_protected)
app.include_router(performance.router,   prefix="/api", **_protected)
app.include_router(bot_router.router,    prefix="/api", **_protected)
app.include_router(config_router.router, prefix="/api", **_protected)


@app.get("/health")
def health():
    return {"status": "ok"}
