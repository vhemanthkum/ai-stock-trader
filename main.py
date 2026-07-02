"""
main.py — Indian Stock AI Council Engine — Daily Orchestrator

The complete flow:
1. Collect all data (no API calls yet) — market data, prices, fundamentals, news
2. Run market-level agents (Macro A1, Sector A2) — single call each
3. Check macro regime gate — if conditions are dangerous, abort with "stay cash"
4. For each watchlist stock, run stock-level agents in parallel (A3, A4, A5)
5. Chairman A6 synthesizes per-stock
6. Apply sentiment position multiplier
7. Rank by confidence, generate report, save to SQLite
8. Output to console + save HTML report

Usage:
    python main.py                              # Run full engine
    python main.py --watchlist HDFCBANK.NS,INFY.NS  # Custom watchlist
    python main.py --dry-run                    # Skip LLM calls, test data pipeline
"""

import argparse
import asyncio
import json
import logging
import time
from datetime import datetime

from config import WATCHLIST
from utils.helpers import (
    setup_logging,
    print_header,
    print_macro_status,
    print_stock_result,
    print_summary_table,
    console,
)
from utils.sentiment import get_position_multiplier, should_trade, get_sentiment_label
from utils.exceptions import DataCollectionError, AgentFailureError
from utils.math_engine import inject_math_into_result
from data_collectors.sector_map import get_sector_for_dedup

logger = logging.getLogger(__name__)


async def collect_data(watchlist: list[str]) -> dict:
    """
    Step 1: Collect ALL data before any LLM calls.
    
    This is the most important architectural rule:
    Every number the agents see comes from real data sources.
    """
    from data_collectors.yfinance_collector import get_stock_data, get_nifty_data
    from data_collectors.nse_scraper import get_market_overview
    from data_collectors.screener_parser import get_fundamentals
    from data_collectors.news_collector import get_stock_news
    from data_collectors.sector_data import get_sector_rankings

    console.print("\n[bold cyan]━━━ Phase 1: Data Collection ━━━[/]")

    # Market-level data
    console.print("[dim]  Fetching market overview (VIX, FII/DII, MMI)...[/]")
    market_overview = get_market_overview()

    console.print("[dim]  Fetching Nifty50 index data...[/]")
    nifty_data = get_nifty_data()

    console.print("[dim]  Computing sector relative strength...[/]")
    sector_rankings = get_sector_rankings()

    # Per-stock data
    prices = {}
    fundamentals = {}
    news = {}

    valid_tickers = []
    for ticker in watchlist:
        console.print(f"[dim]  Fetching data for {ticker}...[/]")
        try:
            p = get_stock_data(ticker)
            f = get_fundamentals(ticker)
            n = get_stock_news(ticker)
            prices[ticker] = p
            fundamentals[ticker] = f
            news[ticker] = n
            valid_tickers.append(ticker)
        except DataCollectionError as e:
            logger.error(str(e))
            console.print(f"    [red]✗ Dropping {ticker} due to data collection failure: {e.reason}[/]")
            continue

    # Combine market data
    market_data = {
        "india_vix": market_overview.get("india_vix", 15.0),
        "mmi_score": market_overview.get("mmi_score", 50.0),
        "nifty_close": nifty_data.get("close", 0),
        "nifty_200dma": nifty_data.get("dma_200", 0),
        "nifty_above_200dma": nifty_data.get("above_200dma", True),
        "fii_3day_net": market_overview.get("fii_3day_net", 0),
        "dii_3day_net": market_overview.get("dii_3day_net", 0),
    }

    console.print(f"[green]  ✓ Data collection complete for {len(valid_tickers)}/{len(watchlist)} stocks[/]")

    return {
        "valid_tickers": valid_tickers,
        "market": market_data,
        "sector_rankings": sector_rankings,
        "prices": prices,
        "fundamentals": fundamentals,
        "news": news,
    }


async def run_market_agents(data: dict) -> tuple[dict, dict]:
    """
    Step 2: Run market-level agents (one call each).
    - Agent 1 (Macro): Market regime + sentiment
    - Agent 2 (Sector): Sector rotation rankings
    """
    from agents import MacroAgent, SectorAgent

    console.print("\n[bold cyan]━━━ Phase 2: Market-Level Analysis ━━━[/]")

    # Agent 1 — Macro
    console.print("[dim]  🤖 Agent 1 (Macro) — Gemini Flash — analyzing market regime...[/]")
    macro_agent = MacroAgent()
    macro_result = await macro_agent.analyze(data["market"])
    console.print(
        f"  [bold]Regime: {macro_result.get('regime', 'N/A')} | "
        f"Sentiment: {macro_result.get('sentiment_score', 0)}/100[/]"
    )

    # Agent 2 — Sector
    console.print("[dim]  🤖 Agent 2 (Sector) — Gemini Flash — ranking sectors...[/]")
    sector_agent = SectorAgent()
    sector_rankings = data["sector_rankings"]
    # Convert Pydantic models to dicts if needed
    if sector_rankings and hasattr(sector_rankings[0], "model_dump"):
        sector_data = [s.model_dump() for s in sector_rankings]
    else:
        sector_data = sector_rankings
    sector_result = await sector_agent.analyze(sector_data)
    console.print(
        f"  [bold]Top sectors: {', '.join(sector_result.get('top_sectors', []))}[/]"
    )

    return macro_result, sector_result


async def run_stock_agents(
    ticker: str,
    price_data,
    fundamental_data,
    news_data,
) -> tuple[dict, dict, dict]:
    """
    Step 3: Run stock-level agents IN PARALLEL for a single stock.
    - Agent 3 (Fundamental): DeepSeek R1
    - Agent 4 (Technical): DeepSeek V3
    - Agent 5 (News): Llama 4 Maverick
    """
    from agents import FundamentalAgent, TechnicalAgent, NewsAgent

    # Convert to dicts/models as needed
    if hasattr(price_data, "model_dump"):
        price_input = price_data
    elif isinstance(price_data, dict):
        from models.schemas import StockPriceData
        price_input = StockPriceData(**price_data)
    else:
        price_input = price_data

    if hasattr(fundamental_data, "model_dump"):
        fund_input = fundamental_data
    elif isinstance(fundamental_data, dict):
        from models.schemas import FundamentalData
        fund_input = FundamentalData(**fundamental_data)
    else:
        fund_input = fundamental_data

    if hasattr(news_data, "model_dump"):
        news_input = news_data
    elif isinstance(news_data, dict):
        from models.schemas import StockNewsData
        news_input = StockNewsData(**news_data)
    else:
        news_input = news_data

    # Run all 3 agents in parallel
    fund_result, tech_result, news_result = await asyncio.gather(
        FundamentalAgent().analyze(fund_input),
        TechnicalAgent().analyze(price_input),
        NewsAgent().analyze(news_input),
    )

    return fund_result, tech_result, news_result


async def run_chairman(
    ticker: str,
    macro: dict,
    sector: dict,
    fundamental: dict,
    technical: dict,
    news: dict,
    position_multiplier: float,
) -> dict:
    """
    Step 4: Chairman synthesizes all agent outputs.
    One call per stock → Gemini Pro.
    """
    from agents import ChairmanAgent

    chairman = ChairmanAgent()
    result = await chairman.synthesize(
        ticker=ticker,
        macro=macro,
        sector=sector,
        fundamental=fundamental,
        technical=technical,
        news=news,
        position_multiplier=position_multiplier,
    )

    return result


async def run_engine(watchlist: list[str] | None = None, dry_run: bool = False) -> list[dict]:
    """
    Main engine orchestrator.
    
    Runs the complete daily analysis pipeline:
    1. Collect data
    2. Market-level agents
    3. Macro gate check
    4. Stock-level agents (parallel per stock)
    5. Chairman synthesis
    6. Rank, report, log
    """
    start_time = time.time()
    tickers = watchlist or WATCHLIST
    
    print_header()
    console.print(f"\n  Watchlist: {', '.join(t.replace('.NS', '') for t in tickers)}")
    console.print(f"  Stocks: {len(tickers)} | Agents: 6 | Models: 4")

    # ── Step 1: Collect all data ────────────────────────────────────────
    data = await collect_data(tickers)
    tickers = data["valid_tickers"]  # Only proceed with stocks that have full data
    market = data["market"]

    if dry_run:
        console.print("\n[yellow]  ⚠ DRY RUN — Skipping LLM calls. Data pipeline verified. ✓[/]")
        console.print(f"\n  Market data: VIX={market['india_vix']}, MMI={market['mmi_score']}")
        console.print(f"  Nifty: ₹{market['nifty_close']} (200DMA: ₹{market['nifty_200dma']})")
        for t in tickers:
            p = data["prices"][t]
            if hasattr(p, "current_price"):
                console.print(f"  {t}: ₹{p.current_price} RSI={p.rsi_14}")
            else:
                console.print(f"  {t}: data fetched")
        return []

    # ── Step 2: Market-level agents ─────────────────────────────────────
    macro_result, sector_result = await run_market_agents(data)

    # Print macro status
    print_macro_status(macro_result, market["mmi_score"], market["india_vix"])

    # ── Step 3: Macro regime gate ───────────────────────────────────────
    can_trade, gate_reason = should_trade(
        market["india_vix"],
        market["mmi_score"],
        macro_result.get("regime", "Neutral"),
    )

    if not can_trade:
        console.print(f"\n[bold red]  🚫 {gate_reason}[/]")
        console.print("[dim]  No stock analysis performed. Stay in cash today.[/]")
        
        # Still generate a report showing why we stayed cash
        from reporting.report_generator import generate_html_report
        report_path = generate_html_report(market, macro_result, sector_result, [])
        console.print(f"\n[dim]  Report saved: {report_path}[/]")
        return []

    console.print(f"\n[green]  ✓ {gate_reason}[/]")

    # Calculate position multiplier from sentiment
    pos_multiplier = get_position_multiplier(market["mmi_score"], market["india_vix"])
    sentiment_label = get_sentiment_label(market["mmi_score"])
    console.print(
        f"  Sentiment: {sentiment_label} | Position multiplier: {pos_multiplier}×"
    )

    # ── Step 4 & 5: Per-stock analysis + Chairman ───────────────────────
    console.print("\n[bold cyan]━━━ Phase 3: Stock-Level Analysis ━━━[/]")

    results = []
    for i, ticker in enumerate(tickers, 1):
        console.print(
            f"\n[bold]  [{i}/{len(tickers)}] Analyzing {ticker.replace('.NS', '')}...[/]"
        )

        try:
            # Run stock-level agents
            console.print("[dim]    🤖 Agents 3-5 running in parallel (Fundamental, Technical, News)...[/]")
            fund_result, tech_result, news_result = await run_stock_agents(
                ticker,
                data["prices"][ticker],
                data["fundamentals"][ticker],
                data["news"][ticker],
            )

            console.print(
                f"    Fund: {fund_result.get('quality_score', '?')}/10 | "
                f"Tech: {tech_result.get('signal', '?')} | "
                f"News: {news_result.get('sentiment_score', '?')}/5"
            )

            # Chairman synthesis
            console.print("[dim]    🤖 Agent 6 (Chairman) — Gemini Pro — synthesizing...[/]")
            call = await run_chairman(
                ticker,
                macro_result,
                sector_result,
                fund_result,
                tech_result,
                news_result,
                pos_multiplier,
            )

            # Inject deterministic math (Flaw #1 fix & Internal Audit Flaw #1 fix)
            # We must merge support_levels from tech_result into prices dict
            prices_dict = data["prices"][ticker].model_dump() if hasattr(data["prices"][ticker], "model_dump") else data["prices"][ticker].copy()
            prices_dict["support_levels"] = tech_result.get("support_levels", [])
            call = inject_math_into_result(call, prices_dict)

            # Ensure all fields are present
            call.setdefault("ticker", ticker)
            call.setdefault("position_multiplier", pos_multiplier)

            # Print result
            action = call.get("action", "HOLD")
            confidence = call.get("confidence", 0)
            action_color = "green" if action == "BUY" else "red" if action == "AVOID" else "yellow"
            console.print(
                f"    [bold {action_color}]→ {action}[/] | "
                f"Confidence: {confidence}% | "
                f"Entry: ₹{call.get('entry_range_low', 0):,.0f}–₹{call.get('entry_range_high', 0):,.0f}"
            )

            results.append(call)

        except AgentFailureError as e:
            logger.error(str(e))
            console.print(f"    [red]✗ Dropping {ticker} due to LLM failure: {e.reason}[/]")
            # Do NOT append a dummy HOLD. Let it die.
            continue
        except Exception as e:
            logger.error(f"Error analyzing {ticker}: {e}")
            console.print(f"    [red]✗ Error analyzing {ticker}: {e}[/]")
            continue
        finally:
            # We don't need manual sleep throttling because AsyncTokenBucketLimiter handles it!
            pass

    # ── Step 6: Enforce Portfolio Rules & Rank ──────────────────────────
    results.sort(key=lambda x: x.get("confidence", 0), reverse=True)

    # Max 1 BUY per sector rule (Flaw #6 / Flaw #1 rule enforcement)
    seen_sectors = set()
    for r in results:
        if r.get("action") == "BUY":
            sector = get_sector_for_dedup(r["ticker"])
            if sector in seen_sectors:
                r["action"] = "HOLD"
                r["reasoning"] += f" [Auto-downgraded: Sector '{sector}' already has a higher-confidence BUY pick to avoid concentration risk]"
            else:
                seen_sectors.add(sector)

    # ── Step 7: Output results ──────────────────────────────────────────
    console.print("\n[bold cyan]━━━ Phase 4: Results ━━━[/]")

    # Print detailed cards for top picks
    for r in results:
        print_stock_result(r)

    # Print summary table
    print_summary_table(results)

    # ── Step 8: Save report and log to database ─────────────────────────
    console.print("\n[bold cyan]━━━ Phase 5: Reporting ━━━[/]")

    # Generate HTML report
    from reporting.report_generator import generate_html_report
    report_path = generate_html_report(market, macro_result, sector_result, results)
    console.print(f"  📄 HTML report: [link=file:///{report_path}]{report_path}[/]")

    # Log to database
    from storage.db import log_call
    for r in results:
        log_call(r)
    console.print(f"  💾 Logged {len(results)} calls to SQLite database")

    # Final stats
    elapsed = time.time() - start_time
    buy_count = sum(1 for r in results if r.get("action") == "BUY")
    console.print(
        f"\n[bold green]  ✓ Engine complete in {elapsed:.1f}s | "
        f"{buy_count} BUY / {len(results) - buy_count} HOLD+AVOID[/]"
    )

    return results


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Indian Stock AI Council Engine — Daily stock analysis",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python main.py                                    # Full run with default watchlist
  python main.py --watchlist HDFCBANK.NS,INFY.NS    # Custom watchlist
  python main.py --dry-run                          # Test data pipeline only
  python main.py --log-level DEBUG                  # Verbose logging
        """,
    )
    parser.add_argument(
        "--watchlist",
        type=str,
        default=None,
        help="Comma-separated list of NSE tickers (e.g. HDFCBANK.NS,INFY.NS)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip LLM API calls, only test the data pipeline",
    )
    parser.add_argument(
        "--screen-nifty500",
        action="store_true",
        help="Run Stage 1 programmatic pre-screener on Nifty 500 to find top 20 momentum candidates",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    args = parser.parse_args()
    setup_logging(args.log_level)

    # Parse watchlist
    watchlist = None
    if args.screen_nifty500:
        from data_collectors.stock_screener import screen_nifty500
        console.print("\n[bold magenta]🚀 STAGE 1: NIFTY 500 PRE-SCREENING[/]")
        watchlist = screen_nifty500(top_n=30)  # Fetch top 30 for thorough institutional screening
    elif args.watchlist:
        watchlist = [t.strip() for t in args.watchlist.split(",")]
        # Ensure .NS suffix
        watchlist = [t if t.endswith(".NS") else f"{t}.NS" for t in watchlist]

    # Run the engine
    asyncio.run(run_engine(watchlist=watchlist, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
