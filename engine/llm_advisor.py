import os
import json
import httpx

CLAUDE_API_URL = "https://api.anthropic.com/v1/messages"
DEEPSEEK_API_URL = "https://api.deepseek.com/chat/completions"

CLAUDE_MODEL = "claude-haiku-4-5"
DEEPSEEK_MODEL = "deepseek-chat"   # DeepSeek V3

# Cost estimates (approximate per analysis call)
# Claude Haiku: ~$0.0008 per call (500 input + 200 output tokens)
# DeepSeek V3:  ~$0.0003 per call (500 input + 200 output tokens)
# Total per trade analysis: ~$0.0011

LLM_TIMEOUT_SECONDS = 15


def _build_analysis_prompt(
    symbol: str,
    conviction_score: int,
    layer_scores: dict,
    price_change_pct: float,
    reasons: list[str],
) -> str:
    return f"""You are a crypto trading risk analyst. Evaluate this trade signal briefly.

Symbol: {symbol}
Conviction Score: {conviction_score}/100
Price Change 24h: {price_change_pct:+.2f}%

Layer Scores:
{json.dumps(layer_scores, indent=2)}

Key Signals:
{chr(10).join(f"- {r}" for r in reasons)}

Respond in JSON only:
{{
  "signal": "BUY" | "SKIP",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "key_reason": "<one sentence>",
  "risk_flag": "<main risk or null>"
}}"""


class LlmAdvisor:
    def __init__(self, claude_key: str = None, deepseek_key: str = None):
        self.claude_key = claude_key or os.getenv("CLAUDE_API_KEY", "")
        self.deepseek_key = deepseek_key or os.getenv("DEEPSEEK_API_KEY", "")

    def _query_claude(self, prompt: str) -> dict:
        """Query Claude Haiku for qualitative signal analysis."""
        if not self.claude_key:
            return {"signal": "SKIP", "confidence": "LOW", "key_reason": "No Claude API key", "risk_flag": None}
        try:
            headers = {
                "x-api-key": self.claude_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            }
            body = {
                "model": CLAUDE_MODEL,
                "max_tokens": 256,
                "messages": [{"role": "user", "content": prompt}],
            }
            resp = httpx.post(CLAUDE_API_URL, headers=headers, json=body, timeout=LLM_TIMEOUT_SECONDS)
            resp.raise_for_status()
            text = resp.json()["content"][0]["text"].strip()
            # Strip markdown code blocks if present
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text)
        except Exception as e:
            return {"signal": "SKIP", "confidence": "LOW", "key_reason": f"Claude error: {e}", "risk_flag": None}

    def _query_deepseek(self, prompt: str) -> dict:
        """Query DeepSeek V3 for quantitative/pattern-based analysis."""
        if not self.deepseek_key:
            return {"signal": "SKIP", "confidence": "LOW", "key_reason": "No DeepSeek API key", "risk_flag": None}
        try:
            headers = {
                "Authorization": f"Bearer {self.deepseek_key}",
                "Content-Type": "application/json",
            }
            body = {
                "model": DEEPSEEK_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 256,
                "response_format": {"type": "json_object"},
            }
            resp = httpx.post(DEEPSEEK_API_URL, headers=headers, json=body, timeout=LLM_TIMEOUT_SECONDS)
            resp.raise_for_status()
            text = resp.json()["choices"][0]["message"]["content"].strip()
            return json.loads(text)
        except Exception as e:
            return {"signal": "SKIP", "confidence": "LOW", "key_reason": f"DeepSeek error: {e}", "risk_flag": None}

    def _parse_signal(self, response: dict) -> str:
        """Extract normalized signal from LLM response."""
        raw = response.get("signal", "SKIP").upper()
        return "BUY" if raw == "BUY" else "SKIP"

    def analyze(
        self,
        symbol: str,
        conviction_score: int,
        layer_scores: dict,
        price_change_pct: float,
        reasons: list[str],
    ) -> dict:
        """
        Dual LLM analysis with Disagreement Protocol.

        Returns:
        {
            "final_signal": "BUY" | "SKIP",
            "agreement": bool,
            "claude": {...},
            "deepseek": {...},
            "disagreement_skipped": bool
        }
        """
        prompt = _build_analysis_prompt(symbol, conviction_score, layer_scores, price_change_pct, reasons)

        claude_result = self._query_claude(prompt)
        deepseek_result = self._query_deepseek(prompt)

        claude_signal = self._parse_signal(claude_result)
        deepseek_signal = self._parse_signal(deepseek_result)

        agreement = claude_signal == deepseek_signal
        disagreement_skipped = not agreement

        # Disagreement Protocol: if LLMs disagree, skip the trade
        if disagreement_skipped:
            final_signal = "SKIP"
        else:
            final_signal = claude_signal  # Both agree

        return {
            "final_signal": final_signal,
            "agreement": agreement,
            "disagreement_skipped": disagreement_skipped,
            "claude": claude_result,
            "deepseek": deepseek_result,
        }

    # ── SHORT dual-LLM analysis ───────────────────────────────────────────────

    def _build_short_prompt(
        self,
        symbol: str,
        short_score: int,
        signal_scores: dict,
        regime: str,
        reasons: list[str],
    ) -> str:
        return f"""You are a crypto trading risk analyst evaluating a SHORT trade signal.

Symbol: {symbol}
Market Regime: {regime}
Short Conviction Score: {short_score}/100

Signal Breakdown:
{json.dumps(signal_scores, indent=2)}

Key Signals:
{chr(10).join(f"- {r}" for r in reasons)}

Should this SHORT position be taken?
Respond in JSON only:
{{
  "signal": "SHORT" | "SKIP",
  "confidence": "HIGH" | "MEDIUM" | "LOW",
  "key_reason": "<one sentence>",
  "risk_flag": "<main risk or null>"
}}"""

    def _parse_short_signal(self, response: dict) -> str:
        """Extract normalized short signal: SHORT or SKIP."""
        raw = response.get("signal", "SKIP").upper()
        return "SHORT" if raw == "SHORT" else "SKIP"

    def analyze_short(
        self,
        symbol: str,
        short_score: int,
        signal_scores: dict,
        regime: str,
        reasons: list[str],
    ) -> dict:
        """
        Dual LLM analysis for SHORT signals — same disagreement protocol as analyze().
        Both Claude AND DeepSeek must output "SHORT"; disagreement → SKIP.
        """
        prompt = self._build_short_prompt(symbol, short_score, signal_scores, regime, reasons)

        claude_result = self._query_claude(prompt)
        deepseek_result = self._query_deepseek(prompt)

        claude_signal = self._parse_short_signal(claude_result)
        deepseek_signal = self._parse_short_signal(deepseek_result)

        agreement = claude_signal == deepseek_signal
        disagreement_skipped = not agreement
        final_signal = "SKIP" if disagreement_skipped else claude_signal

        return {
            "final_signal": final_signal,
            "agreement": agreement,
            "disagreement_skipped": disagreement_skipped,
            "claude": claude_result,
            "deepseek": deepseek_result,
        }

    def analyze_short_with_mock(
        self,
        symbol: str,
        short_score: int,
        signal_scores: dict,
        regime: str,
        reasons: list[str],
        mock_claude: dict = None,
        mock_deepseek: dict = None,
    ) -> dict:
        """Test-friendly version of analyze_short() using pre-canned LLM responses."""
        claude_result = mock_claude or {
            "signal": "SKIP", "confidence": "LOW", "key_reason": "mock", "risk_flag": None
        }
        deepseek_result = mock_deepseek or {
            "signal": "SKIP", "confidence": "LOW", "key_reason": "mock", "risk_flag": None
        }

        claude_signal = self._parse_short_signal(claude_result)
        deepseek_signal = self._parse_short_signal(deepseek_result)

        agreement = claude_signal == deepseek_signal
        disagreement_skipped = not agreement
        final_signal = "SKIP" if disagreement_skipped else claude_signal

        return {
            "final_signal": final_signal,
            "agreement": agreement,
            "disagreement_skipped": disagreement_skipped,
            "claude": claude_result,
            "deepseek": deepseek_result,
        }

    def analyze_with_mock(
        self,
        symbol: str,
        conviction_score: int,
        layer_scores: dict,
        price_change_pct: float,
        reasons: list[str],
        mock_claude: dict = None,
        mock_deepseek: dict = None,
    ) -> dict:
        """Test-friendly version that accepts pre-canned LLM responses."""
        claude_result = mock_claude or {"signal": "SKIP", "confidence": "LOW", "key_reason": "mock", "risk_flag": None}
        deepseek_result = mock_deepseek or {"signal": "SKIP", "confidence": "LOW", "key_reason": "mock", "risk_flag": None}

        claude_signal = self._parse_signal(claude_result)
        deepseek_signal = self._parse_signal(deepseek_result)

        agreement = claude_signal == deepseek_signal
        disagreement_skipped = not agreement
        final_signal = "SKIP" if disagreement_skipped else claude_signal

        return {
            "final_signal": final_signal,
            "agreement": agreement,
            "disagreement_skipped": disagreement_skipped,
            "claude": claude_result,
            "deepseek": deepseek_result,
        }
