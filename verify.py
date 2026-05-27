#!/usr/bin/env python3
"""
Kiểm tra toàn diện codebase — chạy từ thư mục gốc project.
Dùng: python verify.py
"""
import re
from pathlib import Path

ROOT = Path(__file__).parent

import sys
import io
# Force UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PASS = "\033[92m✅\033[0m"
FAIL = "\033[91m❌\033[0m"
passed = failed = 0


def check(desc: str, path: str, must_have: str | None = None, must_not: str | None = None):
    global passed, failed
    content = (ROOT / path).read_text(encoding="utf-8", errors="ignore") if (ROOT / path).exists() else None
    ok = True
    reason = ""
    if content is None:
        ok, reason = False, f"file not found: {path}"
    elif must_have and not re.search(must_have, content):
        ok, reason = False, f"missing pattern: {must_have!r}"
    elif must_not and re.search(must_not, content):
        # Narrow: ignore matches that are purely in a single-line comment
        # (lines starting with optional whitespace + #)
        lines_with_pattern = [
            ln for ln in content.splitlines()
            if re.search(must_not, ln) and not re.match(r"^\s*#", ln)
        ]
        if lines_with_pattern:
            ok, reason = False, f"forbidden pattern in non-comment code: {must_not!r}"

    sym = PASS if ok else FAIL
    suffix = f" \033[90m({reason})\033[0m" if not ok else ""
    print(f"  {sym}  {desc}{suffix}")
    if ok:
        passed += 1
    else:
        failed += 1


print("═" * 56)
print("  KIỂM TRA CODEBASE — crypto-trading-bot")
print("═" * 56)

# ── Macro layer ───────────────────────────────────────────
print("\n── Macro (Tầng 2) ──────────────────────────────────────")
check("Dùng UUP ETF thay DX-Y.NYB",
      "engine/macro.py", must_have=r'"UUP"', must_not=r"DX-Y\.NYB")
check("Dùng GLD ETF thay GC=F",
      "engine/macro.py", must_have=r'"GLD"', must_not=r"GC=F")

# ── Social layer ──────────────────────────────────────────
print("\n── Social (Tầng 6) ─────────────────────────────────────")
check("Gọi get_social_score trong main.py",
      "engine/main.py", must_have=r"get_social_score")
check("Fear&Greed URL có mặt",
      "engine/social.py", must_have=r"alternative\.me")
check("CoinGecko URL có mặt",
      "engine/social.py", must_have=r"coingecko\.com")
check("score_fear_greed method tồn tại",
      "engine/social.py", must_have=r"def score_fear_greed")
check("score_coingecko_sentiment method tồn tại",
      "engine/social.py", must_have=r"def score_coingecko_sentiment")

# ── BTC Lead layer ────────────────────────────────────────
print("\n── BTC Lead (Tầng 4) ───────────────────────────────────")
check("get_btc_change_pct method tồn tại",
      "engine/btc_lead.py", must_have=r"def get_btc_change_pct")
check("CoinGecko fallback có trong btc_lead",
      "engine/btc_lead.py", must_have=r"coingecko\.com")
check("main.py gọi get_btc_change_pct thay vì raw ticker",
      "engine/main.py", must_have=r"get_btc_change_pct")
check("btc_change dùng get_btc_change_pct cho mọi pair (không hardcode price_change)",
      "engine/main.py", must_have=r"btc_change = btc\.get_btc_change_pct\(\)")

# ── Web backend ───────────────────────────────────────────
print("\n── Web backend ─────────────────────────────────────────")
check("Proxy dùng đúng cú pháp proxy= (không phải proxies=)",
      "web/backend/routers/market.py", must_have=r"proxy=_build_proxy", must_not=r"proxies=")
check("_build_proxy xử lý URL http://",
      "web/backend/routers/market.py", must_have=r"startswith")
check("CoinDesk RSS có mặt",
      "web/backend/routers/market.py", must_have=r"coindesk\.com")
check("Cointelegraph RSS có mặt",
      "web/backend/routers/market.py", must_have=r"cointelegraph\.com")
check("Endpoint /signals/latest tồn tại",
      "web/backend/routers/signals.py", must_have=r"/signals/latest")
check("Signals router đã được đăng ký trong main.py",
      "web/backend/main.py", must_have=r"signals_router")

# ── Frontend ──────────────────────────────────────────────
print("\n── Frontend ────────────────────────────────────────────")
check("SignalInsight component tồn tại",
      "web/frontend/components/SignalInsight.tsx", must_have=r"Luồng suy nghĩ Bot")
check("useSignals hook có trong hooks.ts",
      "web/frontend/lib/hooks.ts", must_have=r"useSignals")
check("PriceTickerBar tồn tại",
      "web/frontend/components/PriceTickerBar.tsx", must_have=r"useMarketPrices")
check("page.tsx có SignalInsight",
      "web/frontend/app/page.tsx", must_have=r"SignalInsight")
check("Watchlist đúng 5 coin",
      "engine/main.py", must_have=r"BTCUSDT.*ETHUSDT.*BNBUSDT.*SOLUSDT.*ADAUSDT")

# ── Telegram ──────────────────────────────────────────────
print("\n── Telegram ────────────────────────────────────────────")
check("AlertSubscriber dùng httpx để gửi tin nhắn",
      "telegram/alerts.py", must_have=r"httpx\.post")
check("/report dùng bot:force_report key",
      "telegram/handlers.py", must_have=r"bot:force_report")
check("/start gửi lệnh qua bot:control",
      "telegram/handlers.py", must_have=r'set\("bot:control"')
check("CoinGecko global fetch trong reporter",
      "engine/main.py", must_have=r"coingecko\.com/api/v3/global")

# ── SHORT trading ─────────────────────────────────────────
print("\n── Tính năng ───────────────────────────────────────────")
check("SHORT_CONVICTION_THRESHOLD có mặt",
      "engine/main.py", must_have=r"SHORT_CONVICTION_THRESHOLD")

print(f"\n{'═'*56}")
total = passed + failed
print(f"  Kết quả: {passed}/{total} kiểm tra đạt", end="")
if failed == 0:
    print(f" \033[92m— Tất cả OK\033[0m")
else:
    print(f" \033[91m— {failed} lỗi\033[0m")
print("═" * 56)
sys.exit(0 if failed == 0 else 1)
