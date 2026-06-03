#!/usr/bin/env python3
"""
Health check script — chạy mỗi 2 giờ qua cron.
Kiểm tra: WireGuard VPN, engine container, Binance API, scan gần nhất.
Gửi Telegram alert nếu phát hiện vấn đề.

Cron setup:
    0 */2 * * * /usr/bin/python3 /root/crypto-trading-bot/scripts/health_check.py >> /var/log/health_check.log 2>&1
"""
import os
import sys
import subprocess
import time
from datetime import datetime
from pathlib import Path

# Load .env từ project root
_ENV = Path(__file__).parent.parent / ".env"
if _ENV.exists():
    for line in _ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

TELEGRAM_TOKEN    = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_USER_IDS = [u.strip() for u in os.getenv("TELEGRAM_ALLOWED_USER_IDS", "").split(",") if u.strip()]
ENGINE_CONTAINER  = "crypto-trading-bot-engine-1"
WG_INTERFACE      = "wg0"
MAX_HANDSHAKE_AGE = 300   # 5 phút — WireGuard coi như mất kết nối
MAX_SCAN_AGE      = 600   # 10 phút — nếu không có scan mới coi như engine treo


# ── Telegram ──────────────────────────────────────────────────────────────────

def send_telegram(text: str) -> None:
    try:
        import urllib.request, json
        for chat_id in TELEGRAM_USER_IDS:
            data = json.dumps({"chat_id": chat_id, "text": text}).encode()
            req  = urllib.request.Request(
                f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                data=data,
                headers={"Content-Type": "application/json"},
            )
            urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        print(f"[health_check] Telegram send failed: {e}")


# ── Checks ────────────────────────────────────────────────────────────────────

def check_wireguard() -> tuple[bool, str]:
    """WireGuard handshake còn mới không."""
    try:
        out = subprocess.check_output(
            ["wg", "show", WG_INTERFACE, "latest-handshakes"],
            stderr=subprocess.DEVNULL, timeout=5, text=True,
        )
        for line in out.strip().splitlines():
            parts = line.split()
            if len(parts) >= 2:
                ts  = int(parts[-1])
                age = int(time.time()) - ts
                if ts == 0:
                    return False, "Chưa có handshake — tunnel chưa kết nối"
                if age > MAX_HANDSHAKE_AGE:
                    return False, f"Handshake cũ {age}s — VPN có thể đã ngắt"
                return True, f"OK (handshake {age}s trước)"
        return False, "Không đọc được handshake"
    except FileNotFoundError:
        return False, "wg command không tìm thấy"
    except subprocess.CalledProcessError:
        return False, f"Interface {WG_INTERFACE} không tồn tại"
    except Exception as e:
        return False, str(e)


def check_engine() -> tuple[bool, str]:
    """Engine container đang chạy không."""
    try:
        out = subprocess.check_output(
            ["docker", "ps", "--filter", f"name={ENGINE_CONTAINER}", "--format", "{{.Status}}"],
            stderr=subprocess.DEVNULL, timeout=5, text=True,
        ).strip()
        if out.startswith("Up"):
            return True, out
        return False, f"Container không Up: '{out}'"
    except Exception as e:
        return False, str(e)


def check_binance() -> tuple[bool, str]:
    """Binance API có kết nối được và balance > 0 không."""
    script = """
import os; from dotenv import load_dotenv; load_dotenv(override=True)
from binance.client import Client
try:
    c = Client(os.getenv('BINANCE_API_KEY'), os.getenv('BINANCE_SECRET_KEY'), testnet=False)
    acc = c.get_account()
    usdt = next((a for a in acc['balances'] if a['asset'] == 'USDT'), None)
    bal = float(usdt['free']) + float(usdt['locked']) if usdt else 0.0
    print(f'OK:{bal:.2f}')
except Exception as e:
    print(f'FAIL:{str(e)[:120]}')
"""
    try:
        out = subprocess.check_output(
            ["docker", "exec", ENGINE_CONTAINER, "python", "-c", script],
            stderr=subprocess.DEVNULL, timeout=30, text=True,
        ).strip()
        if out.startswith("OK:"):
            bal = float(out[3:])
            if bal == 0.0:
                return False, "Balance = 0 USDT — API bị block hoặc tài khoản trống"
            return True, f"{bal:.2f} USDT"
        return False, out.replace("FAIL:", "")
    except subprocess.TimeoutExpired:
        return False, "Timeout — Binance API không phản hồi"
    except Exception as e:
        return False, str(e)


def check_last_scan() -> tuple[bool, str]:
    """Lần scan gần nhất có trong 10 phút không."""
    script = """
from db import get_engine, SignalLog
from sqlalchemy.orm import sessionmaker
from datetime import datetime
sess = sessionmaker(get_engine())()
last = sess.query(SignalLog).order_by(SignalLog.id.desc()).first()
if last and last.created_at:
    diff = (datetime.utcnow() - last.created_at).total_seconds()
    print(int(diff))
else:
    print(99999)
"""
    try:
        out = subprocess.check_output(
            ["docker", "exec", ENGINE_CONTAINER, "python", "-c", script],
            stderr=subprocess.DEVNULL, timeout=15, text=True,
        ).strip()
        age = int(out)
        if age > MAX_SCAN_AGE:
            mins = age // 60
            return False, f"Không có scan trong {mins} phút — engine có thể treo"
        return True, f"Scan gần nhất {age}s trước"
    except subprocess.TimeoutExpired:
        return False, "Timeout khi truy vấn DB"
    except Exception as e:
        return False, str(e)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
    print(f"\n{'='*50}")
    print(f"Health Check — {now}")
    print('='*50)

    checks = [
        ("🔒 WireGuard VPN",    check_wireguard),
        ("⚙️  Engine container", check_engine),
        ("💰 Binance API",      check_binance),
        ("📊 Scan gần nhất",    check_last_scan),
    ]

    results  = []
    failures = []

    for name, fn in checks:
        ok, msg = fn()
        icon = "✅" if ok else "❌"
        line = f"{icon} {name}: {msg}"
        results.append(line)
        print(line)
        if not ok:
            failures.append(f"{name}: {msg}")

    if failures:
        alert = (
            f"🚨 CRYPTO BOT — CẦN KIỂM TRA NGAY\n"
            f"⏰ {now}\n\n"
            + "\n".join(results)
            + "\n\n⚠️ Phát hiện " + str(len(failures)) + " vấn đề!"
        )
        send_telegram(alert)
        print("\n→ Đã gửi Telegram alert")
        sys.exit(1)
    else:
        print("\n✓ Tất cả bình thường")
        sys.exit(0)


if __name__ == "__main__":
    main()
