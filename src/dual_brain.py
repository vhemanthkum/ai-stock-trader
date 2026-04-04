#!/usr/bin/env python3
"""
DualBrainOrchestrator
=====================
Architecture:
  1. Groq (llama-3.3-70b)  → DATA ANALYST  — calls data tools, produces structured JSON
  2. Claude (claude-3-5-haiku-20241022) → STRATEGIST — reads Groq data, builds own thesis, challenges it
  3. Consensus (Claude CIO) → weighs both, produces final BUY/SELL/HOLD
     Trade only executes when conviction ≥ 7/10
"""

import os
import json
import time
from loguru import logger
from groq import Groq
from anthropic import Anthropic
from datetime import datetime

# ── Tool definitions Groq uses to fetch market data ───────────────────────────
GROQ_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_company_fundamentals",
            "description": "Fetch fundamental data (P/E, EPS, market cap, revenue) for a given NSE ticker.",
            "parameters": {
                "type": "object",
                "properties": {
                    "ticker": {"type": "string", "description": "NSE ticker e.g. TCS"}
                },
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_technical_indicators",
            "description": "Fetch OHLCV data and compute SMA-5, SMA-20 moving averages and trend.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "scrape_news_cluster",
            "description": "Fetch latest news headlines for the stock from Google News and Yahoo Finance.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_social_sentiment",
            "description": "Fetch StockTwits social sentiment (bullish/bearish ratio) for the stock.",
            "parameters": {
                "type": "object",
                "properties": {"ticker": {"type": "string"}},
                "required": ["ticker"]
            }
        }
    }
]


class DualBrainOrchestrator:
    """
    Two-AI pipeline:
      Groq (data) → Claude Strategist (thesis) → Claude CIO (consensus) → Execute
    """

    # Correct Anthropic API model IDs (as of 2025-2026)
    GROQ_MODEL   = "llama-3.3-70b-versatile"
    CLAUDE_MODEL = "claude-3-5-haiku-20241022"   # Fast, cheap, great reasoning

    def __init__(self, call_function_fn, execute_trade_fn, trading_state: dict):
        groq_key   = os.getenv("GROQ_API_KEY", "").strip()
        claude_key = os.getenv("ANTHROPIC_API_KEY", "").strip()

        if not groq_key:
            raise ValueError("GROQ_API_KEY is missing from environment variables!")
        if not claude_key or claude_key == "your_claude_api_key_here":
            raise ValueError("ANTHROPIC_API_KEY is missing or not set in environment variables!")

        self.groq          = Groq(api_key=groq_key)
        self.claude        = Anthropic(api_key=claude_key)
        self.call_function = call_function_fn
        self.execute_trade = execute_trade_fn
        self.trading_state = trading_state

        logger.info(f"✅ DualBrainOrchestrator ready | Groq={self.GROQ_MODEL} | Claude={self.CLAUDE_MODEL}")

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 1 — Groq: data collection via tool calls
    # ─────────────────────────────────────────────────────────────────────────
    def groq_data_analyst(self, ticker: str) -> dict:
        """Use Groq tool calls to collect all market data for ticker."""
        logger.info(f"[Groq 📊] Collecting data for {ticker}")

        system_prompt = (
            "You are a quantitative data analyst at a hedge fund. "
            "Collect market data for the given NSE stock using ALL available tools "
            "(fundamentals, technicals, news, social sentiment). "
            "After collecting all 4 data points, respond with ONLY a single JSON object:\n"
            '{"ticker":str,"fundamentals":{...},"technicals":{...},"news":[...],"sentiment":{...},"data_summary":str}\n'
            "No text outside the JSON."
        )

        messages      = [{"role": "user", "content": f"Collect all market data for NSE stock: {ticker}"}]
        gathered_data = {}

        for attempt in range(10):  # max 10 rounds (4 tool calls + analysis)
            try:
                response = self.groq.chat.completions.create(
                    model=self.GROQ_MODEL,
                    max_tokens=2048,
                    temperature=0.1,
                    messages=[{"role": "system", "content": system_prompt}] + messages,
                    tools=GROQ_TOOLS,
                    tool_choice="auto"
                )
            except Exception as e:
                logger.error(f"[Groq] API error attempt {attempt+1}: {e}")
                time.sleep(10)
                continue

            msg = response.choices[0].message

            # Build assistant history entry
            assistant_msg = {"role": "assistant"}
            if msg.content:
                assistant_msg["content"] = msg.content
            if msg.tool_calls:
                assistant_msg["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments}
                    }
                    for tc in msg.tool_calls
                ]
            messages.append(assistant_msg)

            if msg.tool_calls:
                # Execute each tool and feed results back
                for tc in msg.tool_calls:
                    fn_name = tc.function.name
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError:
                        args = {"ticker": ticker}

                    logger.info(f"[Groq 🔧] {fn_name}({args})")
                    result = self.call_function(fn_name, args)
                    gathered_data[fn_name] = result

                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": fn_name,
                        "content": json.dumps(result, default=str)
                    })
            else:
                # No more tool calls — parse the final JSON analysis
                raw = (msg.content or "{}").strip()
                try:
                    start = raw.find("{")
                    end   = raw.rfind("}") + 1
                    analysis = json.loads(raw[start:end]) if start != -1 and end > start else {}
                except json.JSONDecodeError:
                    analysis = {"ticker": ticker, "data_summary": raw}

                analysis.setdefault("ticker", ticker)
                analysis.setdefault("data_summary", raw)
                analysis["_raw_tool_data"] = gathered_data
                logger.info(f"[Groq ✅] Data collected for {ticker}")
                return analysis

        # Fallback if we exhaust attempts
        logger.warning(f"[Groq ⚠️] Exhausted attempts for {ticker}, using partial data")
        return {
            "ticker": ticker,
            "data_summary": "Partial data — tool loop exhausted",
            "_raw_tool_data": gathered_data
        }

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 2 — Claude: independent strategy from Groq's data
    # ─────────────────────────────────────────────────────────────────────────
    def claude_strategist(self, ticker: str, groq_analysis: dict) -> dict:
        """Claude reads Groq data, forms its own independent trading thesis."""
        logger.info(f"[Claude 🧠] Building strategy for {ticker}")

        capital          = self.trading_state.get("capital", 100_000_000)
        daily_loss       = self.trading_state.get("daily_loss", 0)
        budget_remaining = 2_500_000 - abs(daily_loss)
        trades_today     = self.trading_state.get("trades_today", 0)

        system = (
            "You are a senior fund manager at Goldman Sachs India Equities desk.\n"
            "You receive raw quantitative data from a junior analyst (Groq AI).\n"
            "YOUR JOB:\n"
            "1. Form your OWN independent trading thesis from the data.\n"
            "2. Challenge any weak or unsupported claims in the analyst's summary.\n"
            "3. Apply strict institutional risk rules.\n\n"
            "RISK RULES (NON-NEGOTIABLE):\n"
            f"• Max risk per trade: ₹5,00,000 (0.5% of ₹{capital:,})\n"
            f"• Daily risk budget remaining today: ₹{budget_remaining:,}\n"
            f"• Trades placed today: {trades_today}/50\n"
            "• Minimum Risk:Reward ratio = 1:2\n"
            "• Only BUY or SELL high-cap NSE stocks (Nifty 100)\n\n"
            "Return ONLY valid JSON (no text outside it):\n"
            '{"decision":"BUY"|"SELL"|"HOLD","conviction":1-10,'
            '"entry_price":number|null,"stop_loss":number|null,"target":number|null,'
            '"quantity":number|null,"reasoning":str,"challenges_to_analyst":str}'
        )

        user_msg = (
            f"Analyst data for {ticker}:\n\n"
            f"```json\n{json.dumps(groq_analysis, indent=2, default=str)}\n```\n\n"
            "Build your independent strategy."
        )

        try:
            resp    = self.claude.messages.create(
                model=self.CLAUDE_MODEL,
                max_tokens=1024,
                temperature=0.2,
                system=system,
                messages=[{"role": "user", "content": user_msg}]
            )
            raw     = resp.content[0].text.strip()
            start   = raw.find("{")
            end     = raw.rfind("}") + 1
            strategy = json.loads(raw[start:end]) if start != -1 and end > start else {}
        except Exception as e:
            logger.error(f"[Claude Strategist] Error for {ticker}: {e}")
            strategy = {}

        strategy.setdefault("decision",   "HOLD")
        strategy.setdefault("conviction", 1)
        strategy.setdefault("reasoning",  "Claude error — defaulting to HOLD")
        logger.info(f"[Claude ✅] {ticker}: {strategy['decision']} (conviction={strategy['conviction']})")
        return strategy

    # ─────────────────────────────────────────────────────────────────────────
    # STAGE 3 — Claude CIO: consensus from both views
    # ─────────────────────────────────────────────────────────────────────────
    def synthesize_consensus(self, ticker: str, groq_analysis: dict, claude_strategy: dict) -> dict:
        """CIO weighs both analyst and strategist opinions → final actionable decision."""
        logger.info(f"[Consensus 🤝] Synthesizing for {ticker}")

        system = (
            "You are the Chief Investment Officer (CIO) at an institutional hedge fund.\n"
            "You receive:\n"
            "  1. Raw market data summary from the Data Analyst (Groq AI)\n"
            "  2. An independent trading strategy from the Senior Strategist (Claude)\n\n"
            "YOUR JOB: Make the single final call.\n"
            "• Only set execute_trade=true if conviction ≥ 7/10\n"
            "• If analyst and strategist disagree substantively → HOLD\n"
            "• Prioritize capital preservation over alpha generation\n\n"
            "Return ONLY valid JSON:\n"
            '{"final_decision":"BUY"|"SELL"|"HOLD","final_conviction":1-10,'
            '"execute_trade":true|false,"entry_price":number|null,'
            '"stop_loss":number|null,"target":number|null,'
            '"quantity":number|null,"rationale":str}'
        )

        user_msg = (
            f"STOCK: {ticker}\n\n"
            f"DATA ANALYST SUMMARY:\n{groq_analysis.get('data_summary', 'No summary available')}\n\n"
            f"STRATEGIST DECISION: {claude_strategy.get('decision')} | "
            f"Conviction: {claude_strategy.get('conviction')}/10\n"
            f"Reasoning: {claude_strategy.get('reasoning', '')}\n"
            f"Challenges: {claude_strategy.get('challenges_to_analyst', '')}\n\n"
            f"Proposed trade:\n"
            f"  Entry=₹{claude_strategy.get('entry_price')} | "
            f"  SL=₹{claude_strategy.get('stop_loss')} | "
            f"  Target=₹{claude_strategy.get('target')} | "
            f"  Qty={claude_strategy.get('quantity')}\n\n"
            "Make the final call."
        )

        try:
            resp      = self.claude.messages.create(
                model=self.CLAUDE_MODEL,
                max_tokens=512,
                temperature=0.1,
                system=system,
                messages=[{"role": "user", "content": user_msg}]
            )
            raw       = resp.content[0].text.strip()
            start     = raw.find("{")
            end       = raw.rfind("}") + 1
            consensus = json.loads(raw[start:end]) if start != -1 and end > start else {}
        except Exception as e:
            logger.error(f"[Consensus] Error for {ticker}: {e}")
            consensus = {}

        consensus.setdefault("final_decision",   "HOLD")
        consensus.setdefault("final_conviction", 1)
        consensus.setdefault("execute_trade",    False)
        consensus.setdefault("rationale",        "Consensus error — defaulting to HOLD")

        logger.info(
            f"[Consensus ✅] {ticker}: {consensus['final_decision']} "
            f"(conviction={consensus['final_conviction']}, execute={consensus['execute_trade']})"
        )
        return consensus

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN — Full pipeline for one stock
    # ─────────────────────────────────────────────────────────────────────────
    def analyze_stock(self, ticker: str) -> dict:
        """
        Full pipeline: Groq data → Claude strategy → Consensus → Optional trade execution.
        Returns a result dict for logging.
        """
        result = {
            "ticker":         ticker,
            "timestamp":      datetime.now().isoformat(),
            "groq_analysis":  None,
            "claude_strategy": None,
            "consensus":      None,
            "trade_executed": False,
            "trade_details":  None,
            "error":          None
        }

        try:
            # Stage 1: Groq data collection
            groq_analysis = self.groq_data_analyst(ticker)
            result["groq_analysis"] = groq_analysis

            # Stage 2: Claude strategy
            claude_strategy = self.claude_strategist(ticker, groq_analysis)
            result["claude_strategy"] = claude_strategy

            # Stage 3: Consensus
            consensus = self.synthesize_consensus(ticker, groq_analysis, claude_strategy)
            result["consensus"] = consensus

            # Stage 4: Execute if approved
            should_execute = (
                consensus.get("execute_trade") is True
                and consensus.get("final_conviction", 0) >= 7
                and consensus.get("final_decision") in ("BUY", "SELL")
            )

            if should_execute:
                action  = consensus.get("final_decision")
                entry   = consensus.get("entry_price")
                sl      = consensus.get("stop_loss")
                target  = consensus.get("target")
                qty     = consensus.get("quantity")

                if all(x is not None for x in [action, entry, sl, target, qty]):
                    try:
                        logger.info(
                            f"🚀 EXECUTING {action} {ticker} | "
                            f"Entry=₹{entry} SL=₹{sl} Target=₹{target} Qty={qty}"
                        )
                        trade = self.execute_trade(
                            ticker, action,
                            int(qty), float(entry), float(sl), float(target)
                        )
                        result["trade_executed"] = True
                        result["trade_details"]  = trade
                    except Exception as e:
                        logger.error(f"Trade execution error for {ticker}: {e}")
                        result["error"] = f"Trade execution failed: {e}"
                else:
                    logger.warning(f"⚠️ Consensus approved but params incomplete for {ticker}")
            else:
                logger.info(f"⏸️ HOLD {ticker} — conviction={consensus.get('final_conviction')}")

        except Exception as e:
            logger.error(f"❌ Pipeline failed for {ticker}: {e}")
            result["error"] = str(e)

        return result
