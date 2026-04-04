#!/usr/bin/env python3
"""
run_autonomous.py — Master Orchestrator
========================================
PIPELINE EVERY HOUR:
  Phase 0: StockScreener scans 500+ NSE stocks → picks top 10
  Phase 1: BigPlayerMonitor checks FII/DII + block deals (every 30 min)
  Phase 2: DualBrainOrchestrator runs Groq + Claude on the top 10
  Phase 3: Hourly P&L report to Telegram
"""

import os
import sys
import time
import json
from pathlib import Path
from loguru import logger
from datetime import datetime, date

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)

from dual_brain import DualBrainOrchestrator
from stock_screener import StockScreener
from big_player_monitor import BigPlayerMonitor
from data_ingestion.market_data import MarketData
from data_ingestion.news_sentiment import NewsSentiment
from notifications import send_telegram_alert, send_hourly_pnl_report, verify_telegram_connection

# ── Shared in-memory portfolio state ─────────────────────────────────────────
TRADING_STATE = {
    "capital":          100_000_000,
    "risk_per_trade":       500_000,
    "daily_loss":                 0,
    "trades_today":               0,
    "open_positions":            [],
    "closed_trades":             [],
    "last_reset_date":  str(date.today()),
    "last_scan_at":            None,
    "last_screen_result":      None,
}

# Singletons (created once, reused)
_screener      = None
_big_player    = None


def _get_screener() -> StockScreener:
    global _screener
    if _screener is None:
        _screener = StockScreener()
    return _screener


def _get_big_player() -> BigPlayerMonitor:
    global _big_player
    if _big_player is None:
        _big_player = BigPlayerMonitor()
    return _big_player


def _reset_daily_counters_if_new_day():
    today = str(date.today())
    if TRADING_STATE["last_reset_date"] != today:
        logger.info(f"📅 New day ({today}) — resetting daily counters.")
        TRADING_STATE["daily_loss"]      = 0
        TRADING_STATE["trades_today"]    = 0
        TRADING_STATE["last_reset_date"] = today


# ── Tool dispatcher ───────────────────────────────────────────────────────────
def call_function(name: str, args: dict) -> dict:
    try:
        if name == "get_company_fundamentals":
            return MarketData.get_company_fundamentals(args["ticker"])
        elif name == "get_technical_indicators":
            return MarketData.get_technical_indicators(args["ticker"])
        elif name == "scrape_news_cluster":
            return NewsSentiment.scrape_news_cluster(args["ticker"])
        elif name == "get_social_sentiment":
            return NewsSentiment.get_social_sentiment(args["ticker"])
        else:
            return {"error": f"Unknown tool: {name}"}
    except Exception as e:
        logger.error(f"Tool '{name}' error: {e}")
        return {"error": str(e)}


# ── Trade executor ────────────────────────────────────────────────────────────
def execute_trade(ticker: str, action: str, quantity: int,
                  entry_price: float, stop_loss: float, target: float) -> dict:
    risk   = abs(entry_price - stop_loss) * quantity
    reward = abs(target - entry_price)    * quantity

    trade = {
        "timestamp":   datetime.now().isoformat(),
        "ticker":      ticker,
        "action":      action.upper(),
        "quantity":    quantity,
        "entry_price": entry_price,
        "stop_loss":   stop_loss,
        "target":      target,
        "risk":        round(risk, 2),
        "reward":      round(reward, 2),
        "rr_ratio":    round(reward / risk, 2) if risk > 0 else 0,
        "pnl":         0.0,
    }

    TRADING_STATE["open_positions"].append(trade)
    TRADING_STATE["trades_today"]  += 1

    color = "🟢" if action.upper() == "BUY" else "🔴"
    msg   = (
        f"{color} <b>DUAL-BRAIN TRADE SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Stock:</b>      {ticker}\n"
        f"<b>Action:</b>     {action.upper()}\n"
        f"<b>Quantity:</b>   {quantity:,}\n"
        f"<b>Entry:</b>      ₹{entry_price:,.2f}\n"
        f"<b>Stop Loss:</b>  ₹{stop_loss:,.2f}\n"
        f"<b>Target:</b>     ₹{target:,.2f}\n"
        f"<b>R:R Ratio:</b>  {trade['rr_ratio']:.1f}x\n"
        f"<b>Risk:</b>       ₹{risk:,.0f}\n\n"
        f"🤖 <i>Groq (Analyst) + Claude (Strategist) consensus</i>"
    )
    send_telegram_alert(msg)
    logger.info(f"✅ Trade: {ticker} {action} {quantity}@₹{entry_price}")
    return trade


# ── Hourly P&L report ─────────────────────────────────────────────────────────
def hourly_pnl_report():
    logger.info("📊 Sending hourly P&L report...")
    send_hourly_pnl_report(TRADING_STATE)


# ── Big player check (every 30 min) ──────────────────────────────────────────
def big_player_check():
    try:
        bp = _get_big_player()
        bp.run_all_checks()
    except Exception as e:
        logger.error(f"BigPlayerMonitor error: {e}")


# ── MAIN SCAN ─────────────────────────────────────────────────────────────────
def autonomous_scan():
    """
    Full pipeline:
      1. Screen 500+ stocks → pick top 10
      2. Run Dual-Brain on each of the 10
      3. Send scan summary to Telegram
    """
    _reset_daily_counters_if_new_day()
    TRADING_STATE["last_scan_at"] = datetime.now().isoformat()

    now = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    logger.info("=" * 70)
    logger.info(f"🚀 AlphaV-7 Dual-Brain Scan | {now}")
    logger.info("=" * 70)

    # ── Phase 0: Smart Stock Screening ───────────────────────────────────────
    send_telegram_alert(
        f"🔭 <b>Smart Screener Running</b>\n"
        f"Scanning 500+ NSE stocks to find top 10...\n"
        f"⏱️ {now}"
    )

    try:
        screener       = _get_screener()
        screen_results = screener.get_best_opportunities(top_n=10)
        top_stocks     = screen_results["top_stocks"]
        fii_dii        = screen_results.get("fii_dii", {})
        block_deals    = screen_results.get("block_deals", [])

        TRADING_STATE["last_screen_result"] = screen_results

        tickers_chosen = [s["ticker"] for s in top_stocks]
        fii_emoji = "🟢" if fii_dii.get("fii_sentiment") == "BULLISH" else "🔴"

        # Announce top stocks selection
        stock_lines = "\n".join(
            f"  {i}. <b>{s['ticker']}</b> — {s['reason']}"
            for i, s in enumerate(top_stocks, 1)
        )
        send_telegram_alert(
            f"🏆 <b>Top 10 Selected for Analysis</b>\n"
            f"━━━━━━━━━━━━━━━━━━━━━\n"
            f"{stock_lines}\n\n"
            f"{fii_emoji} FII Today: {fii_dii.get('fii_sentiment','N/A')} | "
            f"DII: {fii_dii.get('dii_sentiment','N/A')}\n"
            f"🏛️ Block deals ≥₹10Cr: {len(block_deals)}"
        )

    except Exception as e:
        logger.error(f"Screener failed: {e} — using fallback watchlist")
        tickers_chosen = [
            "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK",
            "SBIN","BHARTIARTL","LT","BAJFINANCE","AXISBANK"
        ]
        send_telegram_alert(f"⚠️ Screener error — using fallback 10 stocks\n{e}")

    # ── Phase 1: Dual-Brain analysis on each selected stock ──────────────────
    try:
        brain = DualBrainOrchestrator(
            call_function_fn=call_function,
            execute_trade_fn=execute_trade,
            trading_state=TRADING_STATE
        )
    except ValueError as e:
        logger.error(f"Cannot start dual-brain: {e}")
        send_telegram_alert(f"❌ <b>Dual-Brain Failed to Start</b>\n{e}")
        return

    scan_results  = []
    signals_found = 0

    for i, ticker in enumerate(tickers_chosen, 1):
        logger.info(f"[{i:02d}/{len(tickers_chosen)}] 🧠 Analysing {ticker}...")

        if abs(TRADING_STATE["daily_loss"]) >= 2_500_000:
            send_telegram_alert("🛑 <b>Daily Loss Limit Hit</b> — scan halted.")
            break
        if TRADING_STATE["trades_today"] >= 50:
            break

        result = brain.analyze_stock(ticker)
        scan_results.append(result)
        if result.get("trade_executed"):
            signals_found += 1

        # 45s sleep between stocks to respect both Groq (1000 RPD) and Claude limits
        if i < len(tickers_chosen):
            logger.info(f"  ⏳ Rate-limit sleep 45s...")
            time.sleep(45)

    # ── Phase 2: Scan summary ─────────────────────────────────────────────────
    total_pnl = sum(t.get("pnl", 0) for t in TRADING_STATE["closed_trades"])
    send_telegram_alert(
        f"✅ <b>Scan Complete</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Stocks Analysed:</b>  {len(scan_results)}/10\n"
        f"<b>Signals Fired:</b>    {signals_found}\n"
        f"<b>Open Positions:</b>   {len(TRADING_STATE['open_positions'])}\n"
        f"<b>Realized P&amp;L:</b>     ₹{total_pnl:+,.0f}\n"
        f"<b>Trades Today:</b>     {TRADING_STATE['trades_today']}/50\n"
        f"🤖 <i>Next scan in ~1 hour</i>"
    )

    # Save log
    try:
        log_path = Path(__file__).parent.parent / "logs" / "last_scan.json"
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(scan_results, f, indent=2, default=str)
    except Exception as e:
        logger.warning(f"Could not save scan log: {e}")


# ── CLI entry ─────────────────────────────────────────────────────────────────
def main():
    import schedule

    log_path = Path(__file__).parent.parent / "logs" / "autonomous.log"
    log_path.parent.mkdir(exist_ok=True)
    logger.add(str(log_path), rotation="100 MB", retention="7 days")

    logger.info("🏦 AlphaV-7 — CLI mode")
    verify_telegram_connection()
    autonomous_scan()

    schedule.every(1).hours.do(autonomous_scan)
    schedule.every(1).hours.do(hourly_pnl_report)
    schedule.every(30).minutes.do(big_player_check)

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"Scheduler: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
