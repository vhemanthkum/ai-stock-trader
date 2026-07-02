"""
Agent 2 — Sector Agent (Sector Rotation Analysis)

API: Google AI Studio → Gemini 2.5 Flash
Inputs: 8 sector indices vs Nifty, 20-day and 60-day relative strength
Task: Rank sectors 1–8, identify top 2 with positive momentum, flag laggards

This agent runs ONCE per daily engine run (market-level).
"""

from typing import Any

from agents.base_agent import BaseAgent
from models.schemas import SectorOutput, SectorRSData


class SectorAgent(BaseAgent):
    agent_name = "sector"
    output_model = SectorOutput

    def _build_system_prompt(self) -> str:
        return """You are the Sector Rotation Analyst for an Indian stock market AI council.

Your task: Rank Nifty sectors by relative strength and identify where to focus.

RULES:
1. Analyze ONLY the provided sector data — do NOT make up numbers
2. Positive RS = outperforming Nifty50. Negative RS = underperforming
3. Focus on 20-day RS for current momentum, 60-day RS for trend confirmation
4. A sector is "strong" if both 20d and 60d RS are positive
5. A sector is "laggard" if both are negative
6. Return ONLY valid JSON

INVESTMENT RULE:
Only buy stocks in the top 2–3 sectors. This alone removes 70% of bad picks.

OUTPUT JSON SCHEMA:
{
  "sector_rankings": [
    {"name": "<sector>", "rs_20d": <float>, "rs_60d": <float>, "rank": <int>, "strength": "strong"|"neutral"|"weak"}
  ],
  "top_sectors": ["<sector1>", "<sector2>"],
  "laggard_sectors": ["<sector1>", "<sector2>"],
  "reasoning": "<2-3 sentence analysis of sector rotation>"
}"""

    def _build_user_message(self, data: Any) -> str:
        if isinstance(data, list):
            lines = ["SECTOR RELATIVE STRENGTH DATA (verified, computed from NSE index data):"]
            lines.append("Sector | RS(20d) vs Nifty | RS(60d) vs Nifty | 20d Change%")
            lines.append("-" * 60)

            for s in data:
                if isinstance(s, SectorRSData):
                    lines.append(
                        f"{s.sector_name} | {s.rs_20day:+.2f}% | "
                        f"{s.rs_60day:+.2f}% | {s.change_pct_20d:+.2f}%"
                    )
                elif isinstance(s, dict):
                    lines.append(
                        f"{s.get('sector_name', 'Unknown')} | "
                        f"{s.get('rs_20day', 0):+.2f}% | "
                        f"{s.get('rs_60day', 0):+.2f}% | "
                        f"{s.get('change_pct_20d', 0):+.2f}%"
                    )

            lines.append("\nRank all sectors and identify top 2–3 for stock picking. Return JSON only.")
            return "\n".join(lines)

        return str(data)

    def _fallback_output(self, data: Any) -> dict:
        return SectorOutput(
            sector_rankings=[],
            top_sectors=[],
            laggard_sectors=[],
            reasoning="Sector agent failed. Unable to rank sectors. Consider all sectors neutral.",
        ).model_dump()
