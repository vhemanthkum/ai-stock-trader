"""
Agent 4 — Technical Agent (Chart & Price Analysis)

API: OpenRouter → DeepSeek V3 (strong at code/math, structured output)
Inputs: OHLCV summary with precomputed technicals (50DMA, 200DMA, RSI, ATR, volume ratio)
Task: Identify entry zone, calculate ATR-based stop-loss, flag support/resistance

This agent runs ONCE PER STOCK in the watchlist.
"""

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import TechnicalOutput, StockPriceData


class TechnicalAgent(BaseAgent):
    agent_name = "technical"
    output_model = TechnicalOutput

    def _build_system_prompt(self) -> str:
        return """You are the Technical Analyst for an Indian stock market AI council.

Your task: Analyze pre-computed technical indicators and identify entry/exit levels.

ENTRY RULES (from the trading framework):
- Enter ONLY on pullbacks to support (20DMA or previous resistance turned support)
- Never chase breakouts after first 2% move — wait for retest
- RSI between 45–70 is ideal (not overbought)
- Volume > 1.5× average confirms the move

STOP-LOSS RULES:
- Hard stop: 7% below entry, no exceptions
- ATR-based stop: 2× 14-day ATR below entry for volatile stocks
- Use the TIGHTER of the two

SIGNAL CLASSIFICATION:
- BUY_ZONE: Price near support, RSI 45–60, volume confirming
- NEUTRAL: No clear setup, wait for pullback
- OVERBOUGHT: RSI > 70 or price far above 20DMA
- OVERSOLD: RSI < 35, potential reversal zone

RULES:
1. Use ONLY the provided data — do NOT look up or estimate any prices
2. Entry zone should be a realistic range near current support
3. CRITICAL: All prices and percentages must be raw numbers (floats). Do NOT include currency symbols (like ₹) or string formatting. Use 1300.0 instead of "₹1300" and 7.0 instead of "7%".
4. Return ONLY valid JSON

OUTPUT JSON SCHEMA:
{
  "ticker": "<ticker>",
  "signal": "BUY_ZONE" | "NEUTRAL" | "OVERBOUGHT" | "OVERSOLD",
  "entry_zone_low": <float>,
  "entry_zone_high": <float>,
  "stop_loss_pct": <float>,
  "support_levels": [<float>, <float>],
  "resistance_levels": [<float>, <float>],
  "reasoning": "<2-3 sentence technical assessment>"
}"""

    def _build_user_message(self, data: Any) -> str:
        if isinstance(data, StockPriceData):
            d = data
        elif isinstance(data, dict):
            d = StockPriceData(**data) if "ticker" in data else None
        else:
            return str(data)

        if d:
            # Calculate ATR-based stop-loss % for reference
            atr_stop_pct = round((d.atr_14 * 2 / d.current_price) * 100, 2) if d.current_price > 0 else 7.0
            hard_stop_pct = 7.0
            recommended_stop = min(atr_stop_pct, hard_stop_pct)

            return f"""TECHNICAL DATA for {d.ticker} (verified from yfinance):
- Current Price: ₹{d.current_price}
- 20 DMA: ₹{d.dma_20} ({"above" if d.current_price > d.dma_20 else "below"})
- 50 DMA: ₹{d.dma_50} ({"above" if d.above_50dma else "below"})
- 200 DMA: ₹{d.dma_200} ({"above" if d.above_200dma else "below"})
- 14-day RSI: {d.rsi_14}
- 14-day ATR: ₹{d.atr_14}
- ATR-based SL (2×ATR): {atr_stop_pct}%
- Hard SL: {hard_stop_pct}%
- Recommended SL: {recommended_stop}% (tighter of ATR and hard)
- Current Volume: {d.volume_current:,}
- 20-day Avg Volume: {d.volume_avg_20d:,}
- Volume Ratio: {d.volume_ratio}×
- 3-Month Price Change: {d.price_change_3m_pct}%
- 52-Week High: ₹{d.high_52w}
- 52-Week Low: ₹{d.low_52w}

Analyze entry zone, stop-loss, and support/resistance. Return JSON only."""

        return str(data)

    def _fallback_output(self, data: Any) -> dict:
        ticker = "UNKNOWN"
        price = 0.0
        if isinstance(data, StockPriceData):
            ticker = data.ticker
            price = data.current_price
        elif isinstance(data, dict):
            ticker = data.get("ticker", "UNKNOWN")
            price = data.get("current_price", 0)

        return TechnicalOutput(
            ticker=ticker,
            signal="NEUTRAL",
            entry_zone_low=price * 0.97,
            entry_zone_high=price * 1.0,
            stop_loss_pct=7.0,
            support_levels=[price * 0.95],
            resistance_levels=[price * 1.05],
            reasoning="Technical agent failed. Defaulting to neutral signal with 7% stop-loss. Manual chart review recommended.",
        ).model_dump()
