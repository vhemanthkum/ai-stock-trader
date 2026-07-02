"""
Agent 3 — Fundamental Agent (Stock Quality Filter)

API: OpenRouter → DeepSeek R1 (reasoning model, good at financial math)
Inputs: Screener.in data for a single stock
Task: Filter by ROE, D/E, revenue growth. Score each stock 0–10

This agent runs ONCE PER STOCK in the watchlist.
"""

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import FundamentalOutput, FundamentalData


class FundamentalAgent(BaseAgent):
    agent_name = "fundamental"
    output_model = FundamentalOutput

    def _build_system_prompt(self) -> str:
        return """You are the Fundamental Analyst for an Indian stock market AI council.

Your task: Evaluate a stock's fundamental quality using verified financial data.

FILTER CRITERIA (Solvency check for short-term swing/intraday trading):
- Debt/Equity < 1.2 (Moderate leverage is fine for short trades)
- Promoter Pledging < 25% (Avoid heavily pledged risk)
- Solvent: Profitability and ROCE should be stable/neutral (not critical to have >15% ROE for a 3-day breakout trade)

QUALITY SCORING (0–10):
- 9–10: Exceptional — very safe balance sheet, zero pledge, strong promoter backing
- 7–8: Strong — passes all filters, solid liquidity
- 5–6: Moderate — passes D/E and pledge filters, but weak profitability/growth
- 3–4: Speculative — passes D/E or pledge, but has high leverage or business distress
- 0–2: Distressed — fails all solvency checks, high bankruptcy/pledge risk, avoid

RULES:
1. Use ONLY the provided financial data — do NOT make up or estimate numbers
2. Be honest — if data is missing, note it and reduce confidence
3. Flag any red flags (high debt, declining revenue, promoter selling)
4. Return ONLY valid JSON

OUTPUT JSON SCHEMA:
{
  "ticker": "<ticker>",
  "quality_score": <float 0-10>,
  "passes_roe_filter": <bool, true if ROE is positive/solvent>,
  "passes_de_filter": <bool, true if Debt/Equity is safe < 1.2>,
  "passes_growth_filter": <bool, true if revenue or profit growth is stable/improving>,
  "key_strengths": ["<strength1>", "<strength2>"],
  "key_risks": ["<risk1>", "<risk2>"],
  "reasoning": "<2-3 sentence fundamental assessment>"
}"""

    def _build_user_message(self, data: Any) -> str:
        if isinstance(data, FundamentalData):
            d = data
        elif isinstance(data, dict):
            d = FundamentalData(**data) if "ticker" in data else None
        else:
            return str(data)

        if d:
            return f"""FUNDAMENTAL DATA for {d.ticker} (verified from Screener.in):
- Company: {d.company_name}
- Market Cap: ₹{d.market_cap} Cr
- PE Ratio: {d.pe_ratio}
- ROE: {d.roe}%
- ROCE: {d.roce}%
- Debt/Equity: {d.debt_to_equity}
- Revenue Growth (YoY): {d.revenue_growth_yoy}%
- Profit Growth (YoY): {d.profit_growth_yoy}%
- Promoter Holding: {d.promoter_holding}%
- Promoter Change (QoQ): {d.promoter_change_qoq}%

Evaluate fundamental quality, apply all 3 filters, and score 0–10. Return JSON only."""

        return str(data)

    def _fallback_output(self, data: Any) -> dict:
        ticker = "UNKNOWN"
        if isinstance(data, FundamentalData):
            ticker = data.ticker
        elif isinstance(data, dict):
            ticker = data.get("ticker", "UNKNOWN")

        return FundamentalOutput(
            ticker=ticker,
            quality_score=5.0,
            passes_roe_filter=False,
            passes_de_filter=False,
            passes_growth_filter=False,
            key_strengths=[],
            key_risks=["Fundamental analysis unavailable — agent failed"],
            reasoning="Fundamental agent could not complete analysis. Defaulting to neutral score of 5/10. Manual fundamental review required.",
        ).model_dump()
