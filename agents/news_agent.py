"""
Agent 5 — News Agent (Catalyst & Sentiment)

API: OpenRouter → Llama 4 Maverick (long context, good at text sentiment)
Inputs: Last 3 days of ET/Moneycontrol news headlines for each stock
Task: Identify positive/negative catalysts. Score news sentiment −5 to +5.
      Flag any regulatory/earnings risk.

This agent runs ONCE PER STOCK in the watchlist.

WEIGHT: News sentiment is weighted at 15% max in Chairman's synthesis.
Technical + fundamental + macro together drive 85% of the call.
"""

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import NewsOutput, StockNewsData, NewsItem


class NewsAgent(BaseAgent):
    agent_name = "news"
    output_model = NewsOutput

    def _build_system_prompt(self) -> str:
        return """You are the News & Catalyst Analyst for an Indian stock market AI council.

Your task: Analyze recent news headlines and identify catalysts that could move a stock.

CATALYST TYPES TO IDENTIFY:
- Earnings (beat/miss, guidance changes)
- New product launches or partnerships
- Sector tailwinds (government policy, regulatory changes)
- Institutional activity (FII bulk buys/sells visible in news)
- Management changes, M&A, fundraising
- Regulatory risks (SEBI actions, RBI policy impact)

SENTIMENT SCORING (-5 to +5):
- +5: Very strong positive (earnings beat + upgrade + sector tailwind)
- +3: Positive (good earnings or strong catalyst)
- +1: Mildly positive (minor good news)
-  0: Neutral (no significant news)
- -1: Mildly negative (minor concerns)
- -3: Negative (earnings miss, downgrade)
- -5: Very negative (regulatory action, fraud, major risk)

RULES:
1. Analyze ONLY the provided headlines — do NOT make up news
2. A negative headline CAN be a buying opportunity (contrarian view)
3. Positive news at tops can mark a sell signal
4. If no relevant news found, score 0 and note "no catalysts identified"
5. Return ONLY valid JSON

OUTPUT JSON SCHEMA:
{
  "ticker": "<ticker>",
  "sentiment_score": <int -5 to +5>,
  "positive_catalysts": ["<catalyst1>", "<catalyst2>"],
  "negative_catalysts": ["<catalyst1>"],
  "regulatory_risks": ["<risk1>"],
  "reasoning": "<2-3 sentence news assessment>"
}"""

    def _build_user_message(self, data: Any) -> str:
        if isinstance(data, StockNewsData):
            news = data
        elif isinstance(data, dict):
            news = StockNewsData(**data) if "ticker" in data else None
        else:
            return str(data)

        if news:
            lines = [f"NEWS HEADLINES for {news.ticker} (last 3 days, from ET/Moneycontrol):"]

            if not news.headlines:
                lines.append("\nNo stock-specific news found in the last 3 days.")
            else:
                for i, h in enumerate(news.headlines, 1):
                    lines.append(f"\n{i}. [{h.source}] {h.title}")
                    if h.summary:
                        lines.append(f"   Summary: {h.summary[:150]}")
                    if h.published:
                        lines.append(f"   Published: {h.published}")

            lines.append(
                "\nIdentify catalysts, assess sentiment, and flag risks. Return JSON only."
            )
            return "\n".join(lines)

        return str(data)

    def _fallback_output(self, data: Any) -> dict:
        ticker = "UNKNOWN"
        if isinstance(data, StockNewsData):
            ticker = data.ticker
        elif isinstance(data, dict):
            ticker = data.get("ticker", "UNKNOWN")

        return NewsOutput(
            ticker=ticker,
            sentiment_score=0,
            positive_catalysts=[],
            negative_catalysts=[],
            regulatory_risks=[],
            reasoning="News agent failed. No sentiment analysis available. Defaulting to neutral (0). Manual news check recommended.",
        ).model_dump()
