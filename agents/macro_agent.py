"""
Agent 1 — Macro Agent (Market Regime & Sentiment)

API: Google AI Studio → Gemini 2.5 Flash
Inputs: India VIX, MMI score, Nifty vs 200DMA, FII 3-day net flow
Task: Classify regime as Bull/Bear/Neutral and assign sentiment score 0–100

This agent runs ONCE per daily engine run (market-level, not per-stock).
"""

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import MacroOutput


class MacroAgent(BaseAgent):
    agent_name = "macro"
    output_model = MacroOutput

    def _build_system_prompt(self) -> str:
        return """You are the Macro Analyst agent for an Indian stock market AI council.

Your task: Analyze market-level data and classify the current regime.

RULES:
1. You ONLY analyze the provided data — do NOT make up any numbers
2. Return ONLY valid JSON matching the exact schema below
3. Keep reasoning to 2–3 sentences max

REGIME CLASSIFICATION:
- Bull: VIX < 17, Nifty above 200DMA, FII net positive
- Bear: VIX > 22, Nifty below 200DMA, FII net negative
- Neutral: Mixed signals

SENTIMENT SCORING (0–100):
- 0–20: Extreme Fear (VIX > 25, heavy FII selling)
- 20–40: Fear (VIX 20–25, FII outflows)
- 40–60: Neutral
- 60–80: Bullish (VIX < 17, FII inflows)
- 80–100: Extreme Greed (VIX < 12, heavy FII buying)

OUTPUT JSON SCHEMA:
{
  "regime": "Bull" | "Bear" | "Neutral",
  "sentiment_score": <int 0-100>,
  "vix_assessment": "<short VIX analysis>",
  "fii_assessment": "<short FII flow analysis>",
  "reasoning": "<2-3 sentence overall assessment>"
}"""

    def _build_user_message(self, data: Any) -> str:
        if isinstance(data, dict):
            return f"""MARKET DATA (verified, real-time):
- India VIX: {data.get('india_vix', 'N/A')}
- Market Mood Index (MMI): {data.get('mmi_score', 'N/A')}
- Nifty50 Close: {data.get('nifty_close', 'N/A')}
- Nifty50 200DMA: {data.get('nifty_200dma', 'N/A')}
- Nifty above 200DMA: {data.get('nifty_above_200dma', 'N/A')}
- FII 3-day net flow: ₹{data.get('fii_3day_net', 0)} Cr
- DII 3-day net flow: ₹{data.get('dii_3day_net', 0)} Cr

Analyze this data and classify the market regime. Return JSON only."""
        return str(data)

    def _fallback_output(self, data: Any) -> dict:
        """Conservative fallback when API fails."""
        return MacroOutput(
            regime="Neutral",
            sentiment_score=50,
            vix_assessment="Unable to assess — using neutral default",
            fii_assessment="Unable to assess — using neutral default",
            reasoning="Macro agent failed to get LLM response. Defaulting to Neutral regime with 50/100 sentiment. Manual review recommended.",
        ).model_dump()
