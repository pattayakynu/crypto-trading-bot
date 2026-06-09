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


# ── VPN routing auto-heal ────────────────────────────────────────────────────
# Sau khi server reboot, iptables MARK rule còn (đã netfilter-persistent save)
# nhưng `ip rule` cho fwmark thường bị mất → Docker traffic đi thẳng (bị block).
# WireGuard PostUp lẽ ra thêm lại rule này, nhưng nếu wg0 up trước khi rule mất
# do nguyên nhân khác, ta tự thêm lại ở đây.
_FWMARK = "51821"          # 0xca6d — mark do iptables mangle gán cho Docker traffic
_WG_TABLE = "51820"        # routing table trỏ qua wg0


def _fwmark_rule_present() -> bool:
    try:
        out = subprocess.check_output(["ip", "rule", "show"], timeout=5, text=True)
        return _FWMARK in out or "0xca6d" in out
    except Exception:
        return False


def _heal_routing() -> bool:
    """Thêm lại ip rule fwmark → bảng wg0. Trả True nếu đã thêm."""
    try:
        subprocess.run(
            ["ip", "rule", "add", "fwmark", _FWMARK, "lookup", _WG_TABLE, "priority", "200"],
            timeout=5, check=True,
        )
        return True
    except Exception as e:
        print(f"[health_check] heal_routing failed: {e}")
        return False


def _test_binance() -> tuple[bool, str]:
    """Gọi Binance qua container engine. (ok, message)."""
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


def check_binance() -> tuple[bool, str]:
    """
    Binance API có kết nối được không. Tự khắc phục (auto-heal) nếu phát hiện
    traffic không qua VPN: thêm lại ip rule fwmark rồi thử lại 1 lần.
    """
    ok, msg = _test_binance()
    if ok:
        return True, msg

    # Fail — thử auto-heal nếu là lỗi định tuyến (restricted location)
    looks_like_routing = "restricted" in msg.lower() or "balance = 0" in msg.lower() or "timeout" in msg.lower()
    if looks_like_routing and not _fwmark_rule_present():
        print("[health_check] Binance blocked + fwmark rule missing → auto-heal")
        if _heal_routing():
            ok2, msg2 = _test_binance()
            if ok2:
                send_telegram(
                    "🔧 CRYPTO BOT — TỰ KHẮC PHỤC\n"
                    "Phát hiện routing VPN mất sau reboot → đã thêm lại ip rule fwmark.\n"
                    f"Binance OK trở lại: {msg2}"
                )
                return True, f"{msg2} (đã auto-heal routing)"
            return False, f"Auto-heal thất bại — vẫn lỗi: {msg2}"
    return False, msg


def check_last_scan() -> tuple[bool, str]:
    """
    Kiểm tra heartbeat từ Redis (bot:last_scan_ts).
    Dùng Redis thay vì SignalLog vì FAKE_PUMP block không ghi SignalLog
    nhưng scan_job vẫn chạy bình thường.
    """
    script = """
import os, time
from dotenv import load_dotenv; load_dotenv(override=True)
try:
    import redis
    r = redis.from_url(os.getenv('REDIS_URL', 'redis://localhost:6379'))
    prefix = os.getenv('REDIS_KEY_PREFIX', 'bot:')
    ts = r.get(f'{prefix}last_scan_ts')
    if ts:
        age = int(time.time()) - int(ts)
        print(f'REDIS:{age}')
    else:
        print('REDIS:99999')
except Exception as e:
    print(f'ERR:{e}')
"""
    try:
        out = subprocess.check_output(
            ["docker", "exec", ENGINE_CONTAINER, "python", "-c", script],
            stderr=subprocess.DEVNULL, timeout=15, text=True,
        ).strip()

        if out.startswith("REDIS:"):
            age = int(out[6:])
            if age > MAX_SCAN_AGE:
                mins = age // 60
                return False, f"Không có scan trong {mins} phút — engine có thể treo"
            return True, f"Scan gần nhất {age}s trước"
        # Fallback: Redis key chưa có (engine vừa restart chưa scan lần nào)
        if out.startswith("ERR:"):
            return False, f"Không đọc được Redis: {out[4:]}"
        return True, "Heartbeat chưa có (engine mới khởi động)"
    except subprocess.TimeoutExpired:
        return False, "Timeout khi kiểm tra Redis"
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
