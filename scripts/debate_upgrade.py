#!/usr/bin/env python3
"""
Upgrade Brainstorm: Claude vs DeepSeek
═══════════════════════════════════════════════════════════════════════════════
Hai AI đề xuất độc lập những cải tiến/nâng cấp cho hệ thống LONG/SHORT,
rồi tranh luận về độ ưu tiên và tính khả thi của từng đề xuất.

Vòng 1: Mỗi AI đề xuất 3–5 cải tiến quan trọng nhất (không biết ý kiến nhau)
Vòng 2: Mỗi AI đọc đề xuất của đối thủ và tranh luận: đồng ý / phản bác / bổ sung

Chạy: python scripts/debate_upgrade.py
Output: scripts/upgrade_output.txt
"""
import os
import sys
import httpx
from datetime import datetime
from pathlib import Path

# Load .env từ project root
_ROOT = Path(__file__).parent.parent
_ENV  = _ROOT / ".env"
if _ENV.exists():
    for line in _ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

# ── Config ─────────────────────────────────────────────────────────────────────
CLAUDE_API_URL   = "https://api.anthropic.com/v1/messages"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
CLAUDE_MODEL     = "claude-opus-4-5"
DEEPSEEK_MODEL   = "deepseek-chat"
TIMEOUT          = 120

CLAUDE_KEY   = os.getenv("CLAUDE_API_KEY",   "")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ── Trạng thái hiện tại của hệ thống (đã bao gồm tất cả fixes từ lần debate trước) ──
CURRENT_SYSTEM = """
## Crypto Trading Bot — Trạng thái hiện tại (sau debate lần 1)

### MÔI TRƯỜNG
- Capital: ~$215 USDT thực tế
- Watchlist: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ADAUSDT
- Scan interval: mỗi 5 phút
- Infrastructure: Python + SQLite + Redis + Docker, chạy trên VPS $6/tháng

---

### HỆ THỐNG LONG (Spot, không đòn bẩy)

**Conviction Scorer — 6 tầng, tổng 100 điểm:**

| Tầng      | Max | Nguồn dữ liệu | Logic |
|-----------|-----|----------------|-------|
| Whale     | 25  | Binance        | Funding rate + OI change + price change |
| Macro     | 20  | yfinance (UUP) | DXY trend + Gold/BTC correlation |
| Fiat Flow | 15  | CoinGecko      | USDT dominance change |
| BTC Lead  | 20  | Binance/CG     | Alt follow ratio vs BTC trong 4h |
| TA        | 10  | Binance        | RSI 14 + MACD + EMA cross + volume spike |
| Social    | 10  | CG + alt.me    | Fear&Greed index + CoinGecko sentiment |

**Pipeline:**
1. Manipulation filter (FAKE_PUMP detection: BTC futures/spot diverge)
2. Score ≥ 55 → Dual-LLM Gate (Claude Haiku + DeepSeek V3 cả 2 đồng ý "BUY")
3. Hard filter: BEAR regime → block LONG
4. Correlation filter: đang có alt LONG → không mở alt LONG khác
5. Position sizing — tiered theo score:
   - score ≥ 85 → 10% equity
   - score 70–84 → 7.5% equity
   - score 55–69 → 5% equity
6. SL: −5% từ entry | TP: HIGH=+8%, MEDIUM=+5% | Trailing stop: +3% kích hoạt

**Regime với hysteresis:**
- Vào BULL: BTC 7d ≥ +5% AND DXY < +1.5%
- Thoát BULL: BTC 7d giảm xuống dưới +2% (không phải về 0, tránh whipsaw)
- BEAR: BTC 7d ≤ −5% OR DXY ≥ +1.5%

**Adaptive Learning:**
- Weights điều chỉnh sau mỗi trade (chỉ khi đã có ≥ 30 trades để tránh overfit)
- Drawdown Guard: equity giảm >20% từ đỉnh → dừng toàn bộ giao dịch

---

### HỆ THỐNG SHORT (Futures, 1x đòn bẩy)

**Game-theory principle:** tránh signals mà market-maker đã biết retail dùng.
Đánh vào *aftermath* thay vì *peak*.

**ShortBrain — 4 tín hiệu, tổng 100 điểm:**

| Tín hiệu         | Max | Logic |
|------------------|-----|-------|
| Alt Weakness     | 25  | BTC stable nhưng alt giảm / alt không follow BTC pump |
| Funding Reset    | 25  | Funding từng elevated, nay giảm ≥70% (squeeze xong) |
| Volume Exhaustion| 25  | Giá gần đỉnh 20-nến NHƯNG avg 3-nến cuối < 55% avg 17-nến baseline |
| Macro Bearish    | 25  | UUP (DXY) tăng ≥1.5% trong 15 ngày |

**Hard filters:** BULL regime / open LONG cùng pair / negative funding → block

**Ngưỡng + sizing:**
- ≥ 65 điểm + Dual-LLM đồng ý → SHORT
- Max vị thế: 5% equity | Leverage: 1x
- SL: +5% | TP động: score ≥ 85 → 8% below, score 65–84 → 5% below

---

### NHỮNG GÌ CHƯA CÓ (known gaps)
- Không có time-based exit (vị thế có thể kẹt lâu, tích lũy funding fees)
- Không có news filter (pump/dump do tin tức không được lọc)
- Không có volume filter tối thiểu trước khi scan (scan cả alt volume thấp)
- Không có cross-pair signal (ví dụ: ETH yếu có thể báo hiệu BTC yếu sắp tới)
- LLM gate chỉ dùng Haiku (rẻ) — accuracy thấp hơn Sonnet/Opus
- Không có paper trading mode để test logic trước khi bật real money
- Không có performance attribution (không biết tầng nào đang thực sự sinh lời)
"""

# ── Prompts ─────────────────────────────────────────────────────────────────────

UPGRADE_PROMPT = """\
Bạn là chuyên gia quant trading với kinh nghiệm 10 năm về crypto và algorithmic trading.

Dưới đây là trạng thái hiện tại của một crypto trading bot cá nhân (capital ~$215 USDT):

{system}

Bot đang hoạt động live. Chủ bot muốn biết: **nên nâng cấp / bổ sung gì tiếp theo?**

Hãy đề xuất BẰNG TIẾNG VIỆT theo cấu trúc sau:

**1. TOP 3 CẢI TIẾN ƯU TIÊN CAO**
Những gì có impact lớn nhất với effort vừa phải. Giải thích tại sao mỗi cái quan trọng.

**2. 2 CẢI TIẾN DÀI HẠN (worth doing nhưng phức tạp hơn)**
Những cải tiến tốt nhưng cần nhiều công sức hoặc data hơn.

**3. 1 THỨ KHÔNG NÊN LÀM**
Một cải tiến nghe có vẻ hấp dẫn nhưng thực ra không phù hợp với capital $215 hoặc sẽ làm phức tạp hệ thống không cần thiết.

Cụ thể, thực tế. Không đề xuất chung chung kiểu "thêm more data sources"."""

DEBATE_PROMPT = """\
Bạn là chuyên gia quant trading. Đây là trạng thái hiện tại của bot:

{system}

---
Đây là đề xuất nâng cấp của AI đối thủ ({opponent}):

{opponent_proposal}
---

Hãy tranh luận BẰNG TIẾNG VIỆT:

**ĐỒNG Ý & LÝ DO** — Đề xuất nào bạn thấy đúng? Tại sao nó sẽ work?
**PHẢN BÁC** — Đề xuất nào bạn không đồng ý? Rủi ro cụ thể là gì?
**ĐỀ XUẤT BỔ SUNG** — Cải tiến quan trọng mà đối thủ bỏ sót?
**ĐỀ XUẤT TRIỂN KHAI** — Trong số tất cả đề xuất (của cả hai), bạn sẽ làm gì TRƯỚC TIÊN nếu chỉ có 1 ngày để code?

Thẳng thắn, ngắn gọn."""


# ── API Calls ──────────────────────────────────────────────────────────────────
def call_claude(prompt: str) -> str:
    if not CLAUDE_KEY:
        return "[ERROR] Thiếu CLAUDE_API_KEY"
    try:
        resp = httpx.post(
            CLAUDE_API_URL,
            headers={
                "x-api-key": CLAUDE_KEY,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            json={
                "model": CLAUDE_MODEL,
                "max_tokens": 1200,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["content"][0]["text"].strip()
    except Exception as e:
        return f"[ERROR Claude] {e}"


def call_deepseek(prompt: str) -> str:
    if not DEEPSEEK_KEY:
        return "[ERROR] Thiếu DEEPSEEK_API_KEY"
    try:
        resp = httpx.post(
            DEEPSEEK_API_URL,
            headers={
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 1200,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"[ERROR DeepSeek] {e}"


# ── Display helpers ────────────────────────────────────────────────────────────
SEP = "═" * 72

def header(title: str) -> str:
    pad = max(0, (72 - len(title) - 2) // 2)
    return f"\n{SEP}\n{'═' * pad} {title} {'═' * pad}\n{SEP}"

def section(speaker: str, round_label: str, text: str) -> str:
    return "\n".join([
        f"\n{'─' * 72}",
        f"  🤖 {speaker.upper()}  [{round_label}]",
        f"{'─' * 72}",
        text,
    ])


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    output_lines = []

    def p(text: str = ""):
        print(text)
        output_lines.append(text)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p(header(f"UPGRADE BRAINSTORM  —  {timestamp}"))
    p("  Claude Opus vs DeepSeek V3")
    p("  Chủ đề: Nâng cấp gì tiếp theo cho LONG/SHORT bot?")
    p(SEP)

    # ── Vòng 1: Đề xuất độc lập ───────────────────────────────────────────────
    p(header("VÒNG 1 — ĐỀ XUẤT ĐỘC LẬP"))
    p("  Mỗi AI đề xuất cải tiến mà chưa biết ý kiến của nhau.\n")

    upgrade_prompt = UPGRADE_PROMPT.format(system=CURRENT_SYSTEM)

    print("  ⏳ Claude đang suy nghĩ...", flush=True)
    claude_proposal = call_claude(upgrade_prompt)
    p(section("Claude Opus", "Vòng 1 — Đề xuất", claude_proposal))

    print("\n  ⏳ DeepSeek đang suy nghĩ...", flush=True)
    deepseek_proposal = call_deepseek(upgrade_prompt)
    p(section("DeepSeek V3", "Vòng 1 — Đề xuất", deepseek_proposal))

    # ── Vòng 2: Tranh luận ────────────────────────────────────────────────────
    p(header("VÒNG 2 — TRANH LUẬN"))
    p("  Mỗi AI đọc đề xuất của đối thủ và tranh luận.\n")

    print("  ⏳ Claude đọc đề xuất của DeepSeek và phản hồi...", flush=True)
    claude_debate = call_claude(
        DEBATE_PROMPT.format(
            system=CURRENT_SYSTEM,
            opponent="DeepSeek V3",
            opponent_proposal=deepseek_proposal,
        )
    )
    p(section("Claude Opus", "Vòng 2 — Tranh luận với DeepSeek", claude_debate))

    print("\n  ⏳ DeepSeek đọc đề xuất của Claude và phản hồi...", flush=True)
    deepseek_debate = call_deepseek(
        DEBATE_PROMPT.format(
            system=CURRENT_SYSTEM,
            opponent="Claude Opus",
            opponent_proposal=claude_proposal,
        )
    )
    p(section("DeepSeek V3", "Vòng 2 — Tranh luận với Claude", deepseek_debate))

    # ── Kết thúc ──────────────────────────────────────────────────────────────
    p(header("KẾT THÚC"))
    p("  Tổng hợp: xem phần 'ĐỀ XUẤT TRIỂN KHAI' của cả hai AI ở Vòng 2.")
    p(f"  Thời gian: {timestamp}")
    p(SEP)

    out_path = Path(__file__).parent / "upgrade_output.txt"
    out_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"\n  💾 Đã lưu kết quả vào: {out_path}")


if __name__ == "__main__":
    if not CLAUDE_KEY and not DEEPSEEK_KEY:
        print("Can ít nhat mot API key: CLAUDE_API_KEY hoac DEEPSEEK_API_KEY trong .env")
        sys.exit(1)
    main()
