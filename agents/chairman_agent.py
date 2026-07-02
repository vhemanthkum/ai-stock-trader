"""
Agent 6 — Chairman Agent (Final Synthesis)

API: Google AI Studio → Gemini 2.5 Pro
Inputs: Structured output from all 5 agents (< 800 tokens total)
Task: Issue BUY / HOLD / AVOID with entry price range, stop-loss %,
      target 1, target 2, confidence 0–100%, and reasoning.

This is the MOST IMPORTANT agent. It runs ONCE PER STOCK.
Only 1 call per stock means ~10–15 calls per day → well within 50 RPD limit.

WEIGHTS (from blueprint):
- Fundamental: 25%
- Technical: 25%
- Macro: 20%
- Sector: 15%
- News: 15%
"""

from typing import Any

from agents.base_agent import BaseAgent
from config import CHAIRMAN_MAX_TOKENS, CHAIRMAN_WEIGHTS
from models.schemas import ChairmanOutput


class ChairmanAgent(BaseAgent):
    agent_name = "chairman"
    output_model = ChairmanOutput

    def __init__(self):
        super().__init__()
        # Chairman gets more output tokens for detailed reasoning
        from config import CHAIRMAN_MAX_TOKENS
        self._max_tokens = CHAIRMAN_MAX_TOKENS

    def _build_system_prompt(self) -> str:
        return """You are the Chairman of an Indian stock market AI council.

5 specialist agents have independently analyzed a stock. You synthesize their outputs into a FINAL CALL optimized for INTRADAY and SWING trading (1-10 day holding period).

DECISION FRAMEWORK:
- BUY:
  - Setup 1 (High Quality Swing): 4+ agents positive, macro regime is Neutral/Bull, fundamental score >= 5, technical signal is BUY_ZONE.
  - Setup 2 (Momentum/Breakout Swing): Technical signal is BUY_ZONE, news sentiment is positive (>= 3), volume ratio is high (>= 1.5x), macro is Neutral/Bull. (Allows speculative/low-priced stocks where fundamental score is < 5 but D/E filter is PASS).
- HOLD: Mixed signals (neutral technicals, low volume, or low news catalyst).
- AVOID: Technical signal is SELL_ZONE, OR macro regime is Bear, OR D/E filter is FAIL (high solvency/bankruptcy risk), OR VIX > 22.

WEIGHTS:
- Fundamental: 25% (quality of the business)
- Technical: 25% (timing of entry)
- Macro: 20% (market environment)
- Sector: 15% (sector tailwind/headwind)
- News: 15% (catalyst presence, capped influence)

ENTRY RULES:
- The exact entry price, stop-loss, and targets will be calculated deterministically by the system based on support/resistance and ATR. 
- You do NOT need to calculate or return these numbers. Focus solely on the setup classification and reasoning.

CONFIDENCE SCORING (0–100%):
- 80–100%: All agents aligned, strong setup (rare)
- 60–80%: Most agents positive, good setup
- 40–60%: Mixed signals, cautious
- 0–40%: Weak setup, avoid or reduce size

RULES:
1. NEVER make up prices — use ONLY the prices from agent outputs
2. Be conservative — when in doubt, HOLD or AVOID
3. Maximum 1 BUY per sector to avoid concentration risk
4. Return ONLY valid JSON

OUTPUT JSON SCHEMA:
{
  "ticker": "<ticker>",
  "action": "BUY" | "HOLD" | "AVOID",
  "confidence": <int 0-100>,
  "setup_type": "Breakout" | "MeanReversion" | "Momentum" | "None",
  "reasoning": "<3-5 sentence synthesis explaining the call>",
  "macro_score": <int>,
  "sector_score": "<sector assessment>",
  "fundamental_score": <float>,
  "technical_signal": "<signal>",
  "news_sentiment": <int>
}"""

    def _build_user_message(self, data: Any) -> str:
        """
        data should be a dict with keys:
        - ticker, macro, sector, fundamental, technical, news, position_multiplier
        """
        if not isinstance(data, dict):
            return str(data)

        ticker = data.get("ticker", "UNKNOWN")
        macro = data.get("macro", {})
        sector = data.get("sector", {})
        fundamental = data.get("fundamental", {})
        technical = data.get("technical", {})
        news = data.get("news", {})
        pos_mult = data.get("position_multiplier", 1.0)

        return f"""COUNCIL ANALYSIS for {ticker}
Synthesize all 5 agent outputs below into a final BUY/HOLD/AVOID call.

═══ AGENT 1 — MACRO (weight: 20%) ═══
Regime: {macro.get('regime', 'N/A')}
Sentiment Score: {macro.get('sentiment_score', 'N/A')}/100
VIX Assessment: {macro.get('vix_assessment', 'N/A')}
FII Assessment: {macro.get('fii_assessment', 'N/A')}

═══ AGENT 2 — SECTOR (weight: 15%) ═══
Top Sectors: {', '.join(sector.get('top_sectors', []))}
Laggard Sectors: {', '.join(sector.get('laggard_sectors', []))}
Reasoning: {sector.get('reasoning', 'N/A')}

═══ AGENT 3 — FUNDAMENTAL (weight: 25%) ═══
Quality Score: {fundamental.get('quality_score', 'N/A')}/10
ROE Filter: {'PASS' if fundamental.get('passes_roe_filter') else 'FAIL'}
D/E Filter: {'PASS' if fundamental.get('passes_de_filter') else 'FAIL'}
Growth Filter: {'PASS' if fundamental.get('passes_growth_filter') else 'FAIL'}
Strengths: {', '.join(fundamental.get('key_strengths', []))}
Risks: {', '.join(fundamental.get('key_risks', []))}

═══ AGENT 4 — TECHNICAL (weight: 25%) ═══
Signal: {technical.get('signal', 'N/A')}
Entry Zone: ₹{technical.get('entry_zone_low', 0)}–₹{technical.get('entry_zone_high', 0)}
Stop-Loss: {technical.get('stop_loss_pct', 7)}%
Support: {technical.get('support_levels', [])}
Resistance: {technical.get('resistance_levels', [])}

═══ AGENT 5 — NEWS (weight: 15%) ═══
Sentiment: {news.get('sentiment_score', 0)}/5
Positive Catalysts: {', '.join(news.get('positive_catalysts', []))}
Negative Catalysts: {', '.join(news.get('negative_catalysts', []))}
Regulatory Risks: {', '.join(news.get('regulatory_risks', []))}

═══ SENTIMENT OVERLAY ═══
Position Multiplier: {pos_mult}× (based on MMI/VIX gating)

Issue your final call with confidence and reasoning. Return JSON only."""

    async def synthesize(
        self,
        ticker: str,
        macro: dict,
        sector: dict,
        fundamental: dict,
        technical: dict,
        news: dict,
        position_multiplier: float = 1.0,
    ) -> dict:
        """
        Convenience method to call analyze() with properly structured data.
        """
        data = {
            "ticker": ticker,
            "macro": macro,
            "sector": sector,
            "fundamental": fundamental,
            "technical": technical,
            "news": news,
            "position_multiplier": position_multiplier,
        }
        result = await self.analyze(data)

        # Ensure ticker is set
        if result and not result.get("ticker"):
            result["ticker"] = ticker

        # Ensure position multiplier is set
        if result and "position_multiplier" not in result:
            result["position_multiplier"] = position_multiplier

        return result

    def _fallback_output(self, data: Any) -> dict:
        ticker = "UNKNOWN"
        if isinstance(data, dict):
            ticker = data.get("ticker", "UNKNOWN")

        from utils.exceptions import AgentFailureError
        raise AgentFailureError(self.agent_name, ticker, "All retries exhausted")
