#!/usr/bin/env python3
"""
Design Debate: Claude vs DeepSeek
═══════════════════════════════════════════════════════════════════════════════
Hai AI review độc lập thiết kế tính điểm LONG/SHORT, rồi phản biện lẫn nhau.

Vòng 1: Claude review → DeepSeek review (độc lập, không biết nhau)
Vòng 2: Claude đọc review của DeepSeek và phản biện
         DeepSeek đọc review của Claude và phản biện
Kết quả: In ra terminal + lưu vào scripts/debate_output.txt

Chạy: python scripts/debate_design.py
"""
import os
import sys
import json
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
CLAUDE_MODEL     = "claude-opus-4-5"   # Dùng Opus cho chất lượng tranh luận
DEEPSEEK_MODEL   = "deepseek-chat"     # DeepSeek V3
TIMEOUT          = 120                 # Seconds per call

CLAUDE_KEY   = os.getenv("CLAUDE_API_KEY",   "")
DEEPSEEK_KEY = os.getenv("DEEPSEEK_API_KEY", "")

# ── Thiết kế cần review ────────────────────────────────────────────────────────
DESIGN_CONTEXT = """
## Crypto Trading Bot — Thiết kế tính điểm LONG / SHORT

### HỆ THỐNG LONG (Spot, không đòn bẩy)

Conviction Scorer — 6 tầng, tổng 100 điểm:

| Tầng          | Max | Nguồn dữ liệu | Logic cốt lõi |
|---------------|-----|---------------|---------------|
| Whale         | 25  | On-chain      | Giao dịch lớn bất thường (>$100k) trong 4h |
| Macro         | 20  | yfinance      | DXY (UUP ETF) trend + Gold/BTC correlation |
| Fiat Flow     | 15  | CoinGecko     | USDT dominance giảm = tiền vào crypto |
| BTC Lead      | 20  | Binance/CG    | Alt follow BTC trong 4h — nếu BTC tăng mà alt cũng tăng |
| TA            | 10  | Binance       | RSI 14 + MACD + EMA cross + volume spike |
| Social        | 10  | CG + alt.me   | Fear&Greed index + CoinGecko sentiment |

Ngưỡng quyết định:
- ≥ 55 điểm: BUY candidate → gửi sang Dual-LLM gate
- < 55 điểm: SKIP

Dual-LLM Gate (Claude Haiku + DeepSeek V3):
- Cả 2 phải output "BUY" → execute LONG
- 1 trong 2 SKIP → bỏ qua (Disagreement Protocol)

Rủi ro:
- Max vị thế: 10% equity
- Stop-loss: -4% từ giá vào
- Take-profit: tuỳ confidence (HIGH: +8%, MEDIUM: +6%)
- Trailing stop kích hoạt khi lợi nhuận ≥ 3%

---

### HỆ THỐNG SHORT (Futures, 1x đòn bẩy)

Game-theory principle: tránh signals mà market-maker đã biết retail dùng
(raw funding HIGH, RSI overbought...). Thay vào đó đánh vào *aftermath*:

ShortBrain — 4 tín hiệu, tổng 100 điểm:

| Tín hiệu         | Max | Logic |
|------------------|-----|-------|
| Alt Weakness     | 25  | BTC stable (<0.5% change) nhưng alt giảm = vốn chảy ra khỏi alt |
|                  |     | BTC tăng nhưng alt giảm = alt rất yếu (20pts) |
|                  |     | Alt chỉ follow BTC <30% = yếu vừa (15pts) |
| Funding Reset    | 25  | Funding từng elevated (>5bps), nay giảm ≥70% = squeeze xong, safe to short (25pts) |
|                  |     | Giảm ≥30% = partial reset (15pts) |
|                  |     | Negative funding = lệnh short đã nhiều, không short thêm (0pts) |
| Volume Exhaustion| 25  | Giá ≥97% đỉnh 20 candles, nhưng volume 3 candles cuối declining |
|                  |     | Vol giảm ≥45% = exhaustion mạnh (25pts) |
|                  |     | Vol giảm ≥15% = exhaustion vừa (15pts) |
| Macro Bearish    | 25  | UUP (DXY ETF) tăng ≥1.5% trong 15 ngày = strong headwind (25pts) |
|                  |     | ≥1.0% = moderate headwind (15pts) |

Hard filters (block hoàn toàn, không tính điểm):
1. Regime = BULL (BTC 7d ≥+5% AND DXY 10d <1.5%) → không bao giờ short uptrend
2. Đang có vị thế LONG cùng pair → không short trong khi long
3. Funding rate hiện tại âm → longs đang được trả tiền, nguy cơ short squeeze

Regime Detection:
- BULL: BTC 7d ≥ +5% AND DXY 10d < +1.5%
- BEAR: BTC 7d ≤ -5% OR DXY 10d ≥ +1.5%
- SIDEWAYS: còn lại
- Cache 1 giờ

Ngưỡng quyết định:
- ≥ 65 điểm + không bị hard filter + Dual-LLM đồng ý → SHORT
- < 65 hoặc bị block → SKIP

Rủi ro SHORT:
- Max vị thế: 5% equity (nhỏ hơn LONG vì rủi ro cao hơn)
- Leverage: 1x Futures (không khuếch đại rủi ro)

---

### ĐIỂM CHUNG

Adaptive Learning:
- Bot học từ trades thua: nếu layer X liên tục dự đoán sai → giảm weight
- Drawdown Guard: nếu equity giảm >15% từ đỉnh → dừng giao dịch mới

Watchlist: BTCUSDT, ETHUSDT, BNBUSDT, SOLUSDT, ADAUSDT (top 5 thanh khoản)
Scan interval: mỗi 2 phút
Capital: ~$215 USDT thực tế
"""

# ── Prompts ────────────────────────────────────────────────────────────────────
REVIEW_PROMPT = """\
Bạn là chuyên gia quant trading với kinh nghiệm 10 năm về crypto và algorithmic trading.

Dưới đây là thiết kế kỹ thuật của một crypto trading bot cá nhân (capital ~$215):

{design}

Hãy phân tích với góc nhìn phê phán (critical review). Trả lời BẰNG TIẾNG VIỆT.

Cấu trúc câu trả lời:
**1. ĐIỂM MẠNH** — Những gì được thiết kế hợp lý (tối đa 3 điểm)
**2. ĐIỂM YẾU / RỦI RO** — Lỗ hổng nghiêm trọng, edge cases nguy hiểm (tối đa 4 điểm)
**3. CHALLENGE THIẾT KẾ** — 2 quyết định thiết kế bạn muốn tranh luận thêm
**4. ĐỀ XUẤT ƯU TIÊN** — 2 cải tiến quan trọng nhất (cụ thể, không chung chung)

Thẳng thắn, súc tích. Không khen ngợi chung chung."""

REBUTTAL_PROMPT = """\
Bạn là chuyên gia quant trading. Đây là thiết kế cần review:

{design}

---
Đây là nhận xét của AI đối thủ ({opponent}):

{opponent_review}
---

Dựa trên chuyên môn của bạn, hãy phản biện BẰNG TIẾNG VIỆT:

**ĐỒNG Ý** — Điểm nào trong nhận xét trên bạn đồng ý? Tại sao?
**PHẢN BÁC** — Điểm nào bạn KHÔNG đồng ý? Lý do cụ thể?
**BỔ SUNG** — Điểm quan trọng mà đối thủ bỏ sót?

Ngắn gọn, sắc sảo."""

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
                "max_tokens": 1024,
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
                "max_tokens": 1024,
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
    pad = (72 - len(title) - 2) // 2
    return f"\n{SEP}\n{'═' * pad} {title} {'═' * pad}\n{SEP}"

def section(speaker: str, round_label: str, text: str) -> str:
    lines = [
        f"\n{'─' * 72}",
        f"  🤖 {speaker.upper()}  [{round_label}]",
        f"{'─' * 72}",
        text,
    ]
    return "\n".join(lines)


# ── Main ───────────────────────────────────────────────────────────────────────
def main():
    output_lines = []

    def p(text: str = ""):
        print(text)
        output_lines.append(text)

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p(header(f"DESIGN DEBATE  —  {timestamp}"))
    p("  Claude Opus vs DeepSeek V3")
    p("  Chủ đề: Thiết kế tính điểm LONG/SHORT của crypto trading bot")
    p(SEP)

    # ── Vòng 1: Review độc lập ─────────────────────────────────────────────────
    p(header("VÒNG 1 — REVIEW ĐỘC LẬP"))
    p("  Mỗi AI phân tích thiết kế mà chưa biết ý kiến của nhau.\n")

    review_prompt = REVIEW_PROMPT.format(design=DESIGN_CONTEXT)

    print("  ⏳ Claude đang phân tích...", flush=True)
    claude_review = call_claude(review_prompt)
    p(section("Claude Opus", "Vòng 1 — Review", claude_review))

    print("\n  ⏳ DeepSeek đang phân tích...", flush=True)
    deepseek_review = call_deepseek(review_prompt)
    p(section("DeepSeek V3", "Vòng 1 — Review", deepseek_review))

    # ── Vòng 2: Phản biện ─────────────────────────────────────────────────────
    p(header("VÒNG 2 — PHẢN BIỆN"))
    p("  Mỗi AI đọc nhận xét của đối thủ và phản biện.\n")

    print("  ⏳ Claude đọc review của DeepSeek và phản biện...", flush=True)
    claude_rebuttal = call_claude(
        REBUTTAL_PROMPT.format(
            design=DESIGN_CONTEXT,
            opponent="DeepSeek V3",
            opponent_review=deepseek_review,
        )
    )
    p(section("Claude Opus", "Vòng 2 — Phản biện DeepSeek", claude_rebuttal))

    print("\n  ⏳ DeepSeek đọc review của Claude và phản biện...", flush=True)
    deepseek_rebuttal = call_deepseek(
        REBUTTAL_PROMPT.format(
            design=DESIGN_CONTEXT,
            opponent="Claude Opus",
            opponent_review=claude_review,
        )
    )
    p(section("DeepSeek V3", "Vòng 2 — Phản biện Claude", deepseek_rebuttal))

    # ── Tổng kết ───────────────────────────────────────────────────────────────
    p(header("KẾT THÚC TRANH LUẬN"))
    p("  Đọc output ở trên để xem điểm đồng thuận và bất đồng giữa hai AI.")
    p(f"  Thời gian: {timestamp}")
    p(SEP)

    # Lưu file
    out_path = Path(__file__).parent / "debate_output.txt"
    out_path.write_text("\n".join(output_lines), encoding="utf-8")
    print(f"\n  💾 Đã lưu kết quả vào: {out_path}")


if __name__ == "__main__":
    if not CLAUDE_KEY and not DEEPSEEK_KEY:
        print("❌ Cần ít nhất một API key: CLAUDE_API_KEY hoặc DEEPSEEK_API_KEY trong .env")
        sys.exit(1)
    main()
