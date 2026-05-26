import os
import json
import httpx
from datetime import datetime, timezone

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"
CLAUDE_MODEL = "claude-haiku-4-5"
DEEPSEEK_MODEL = "deepseek-chat"
LLM_TIMEOUT = 20

REPORT_TIMES = os.getenv("REPORT_TIMES", "07:00,12:00,17:00,22:00").split(",")


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MarketReporter:
    def __init__(self, claude_key: str = None, deepseek_key: str = None):
        self.claude_key = claude_key or os.getenv("CLAUDE_API_KEY", "")
        self.deepseek_key = deepseek_key or os.getenv("DEEPSEEK_API_KEY", "")

    # ── Template section (always rendered, no LLM cost) ─────────────────────

    def build_template_section(self, market_data: dict) -> str:
        """
        Build the data-driven section of the report.
        market_data keys: btc_price, btc_change_24h, eth_change_24h,
                          total_market_cap_b, btc_dominance,
                          open_positions, total_pnl, equity
        """
        btc = market_data.get("btc_price", 0)
        btc_chg = market_data.get("btc_change_24h", 0)
        eth_chg = market_data.get("eth_change_24h", 0)
        mcap = market_data.get("total_market_cap_b", 0)
        dom = market_data.get("btc_dominance", 0)
        positions = market_data.get("open_positions", 0)
        pnl = market_data.get("total_pnl", 0)
        equity = market_data.get("equity", 0)

        timestamp = _now().strftime("%Y-%m-%d %H:%M UTC")
        pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"
        btc_str = f"+{btc_chg:.2f}%" if btc_chg >= 0 else f"{btc_chg:.2f}%"
        eth_str = f"+{eth_chg:.2f}%" if eth_chg >= 0 else f"{eth_chg:.2f}%"

        return (
            f"📊 *Báo cáo thị trường* — {timestamp}\n"
            f"\n"
            f"*BTC:* ${btc:,.0f} ({btc_str})\n"
            f"*ETH:* {eth_str}\n"
            f"*Market cap:* ${mcap:.0f}B\n"
            f"*BTC dominance:* {dom:.1f}%\n"
            f"\n"
            f"*Bot status:*\n"
            f"  Vị thế đang mở: {positions}\n"
            f"  PnL hôm nay: {pnl_str}\n"
            f"  Tổng equity: ${equity:.2f}\n"
        )

    # ── DeepSeek: quantitative analysis ─────────────────────────────────────

    def get_deepseek_analysis(self, market_data: dict) -> str:
        if not self.deepseek_key:
            return ""
        try:
            prompt = (
                f"Crypto market snapshot:\n{json.dumps(market_data, indent=2)}\n\n"
                f"In 2-3 sentences (Vietnamese), give a quantitative market assessment: "
                f"trend direction, key support/resistance, and risk level. Be concise."
            )
            headers = {
                "Authorization": f"Bearer {self.deepseek_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 200,
            }
            resp = httpx.post(DEEPSEEK_API_URL, headers=headers, json=body, timeout=LLM_TIMEOUT)
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            return ""

    # ── Claude: qualitative / macro commentary ───────────────────────────────

    def get_claude_commentary(self, market_data: dict) -> str:
        if not self.claude_key:
            return ""
        try:
            prompt = (
                f"Crypto market snapshot:\n{json.dumps(market_data, indent=2)}\n\n"
                f"In 2-3 sentences (Vietnamese), give a qualitative macro commentary: "
                f"sentiment, major narrative driving the market, and one key watch point. Be concise."
            )
            headers = {
                "x-api-key": self.claude_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body = {
                "model": CLAUDE_MODEL,
                "max_tokens": 200,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = httpx.post(CLAUDE_API_URL, headers=headers, json=body, timeout=LLM_TIMEOUT)
            resp.raise_for_status()
            return resp.json()["content"][0]["text"].strip()
        except Exception:
            return ""

    # ── Full report assembly ─────────────────────────────────────────────────

    def build_report(self, market_data: dict, include_llm: bool = True) -> str:
        """
        Assemble the full report:
        1. Template section (free)
        2. DeepSeek quantitative analysis (~$0.0002)
        3. Claude qualitative commentary (~$0.0004)
        Total: ~$0.0006 per report × 4/day = ~$0.07/month
        """
        sections = [self.build_template_section(market_data)]

        if include_llm:
            deepseek_text = self.get_deepseek_analysis(market_data)
            if deepseek_text:
                sections.append(f"\n📈 *Phân tích kỹ thuật:*\n{deepseek_text}")

            claude_text = self.get_claude_commentary(market_data)
            if claude_text:
                sections.append(f"\n🧠 *Nhận định vĩ mô:*\n{claude_text}")

        sections.append("\n_Cập nhật tự động bởi Trading Bot_")
        return "\n".join(sections)

    def should_send_report(self, hour: int, minute: int) -> bool:
        """Check if current time matches any report schedule."""
        current = f"{hour:02d}:{minute:02d}"
        return current in REPORT_TIMES
