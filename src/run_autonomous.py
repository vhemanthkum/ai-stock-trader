#!/usr/bin/env python3
"""
Autonomous Orchestrator — run_autonomous.py
===========================================
• Runs Dual-Brain (Groq + Claude) scan on 20 NSE stocks every hour
• Sends hourly P&L report to Telegram (independent of scan timing)
• Rate-limit safe: 30s sleep between stocks (~100 Groq calls/scan << 1000 RPD limit)
"""

import os
import sys
import time
import json
from pathlib import Path
from loguru import logger
from datetime import datetime, date

# ── Ensure src/ is on path whether run via CLI or Gunicorn ──────────────────
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv
load_dotenv(override=True)   # Load .env first so all os.getenv calls work

from dual_brain import DualBrainOrchestrator
from data_ingestion.market_data import MarketData
from data_ingestion.news_sentiment import NewsSentiment
from notifications import send_telegram_alert, send_hourly_pnl_report, verify_telegram_connection

# ── Top 20 most liquid NSE stocks (Nifty 100 subset) ─────────────────────────
# Kept at 20 to stay within Groq free-tier: 1,000 RPD for llama-3.3-70b
WATCHLIST = [
    "RELIANCE",   "TCS",       "HDFCBANK",  "INFY",      "ICICIBANK",
    "HINDUNILVR", "ITC",       "SBIN",      "BHARTIARTL","KOTAKBANK",
    "LT",         "BAJFINANCE","AXISBANK",  "MARUTI",    "SUNPHARMA",
    "TITAN",      "WIPRO",     "HCLTECH",   "TATAMOTORS","ADANIPORTS",
]

# ── Shared in-memory portfolio state ─────────────────────────────────────────
# This persists for the lifetime of the process (resets on Render restart)
TRADING_STATE = {
    "capital":          100_000_000,   # ₹10 crore simulated capital
    "risk_per_trade":       500_000,   # 0.5% per trade
    "daily_loss":                 0,
    "trades_today":               0,
    "open_positions":            [],
    "closed_trades":             [],
    "last_reset_date":  str(date.today())
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _reset_daily_counters_if_new_day():
    """Reset daily loss/trade counters on a new calendar day."""
    today = str(date.today())
    if TRADING_STATE["last_reset_date"] != today:
        logger.info(f"📅 New day detected ({today}) — resetting daily counters.")
        TRADING_STATE["daily_loss"]       = 0
        TRADING_STATE["trades_today"]     = 0
        TRADING_STATE["last_reset_date"]  = today


def call_function(name: str, args: dict) -> dict:
    """Route a Groq tool call to the correct data_ingestion function."""
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


def execute_trade(ticker: str, action: str, quantity: int,
                  entry_price: float, stop_loss: float, target: float) -> dict:
    """Paper-trade executor — logs trade and sends Telegram alert."""
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
        "pnl":         0.0   # Updated when position is closed
    }

    TRADING_STATE["open_positions"].append(trade)
    TRADING_STATE["trades_today"]  += 1

    color = "🟢" if action.upper() == "BUY" else "🔴"
    rr    = trade["rr_ratio"]
    msg   = (
        f"{color} <b>DUAL-BRAIN TRADE SIGNAL</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Stock:</b>      {ticker}\n"
        f"<b>Action:</b>     {action.upper()}\n"
        f"<b>Quantity:</b>   {quantity:,}\n"
        f"<b>Entry:</b>      ₹{entry_price:,.2f}\n"
        f"<b>Stop Loss:</b>  ₹{stop_loss:,.2f}\n"
        f"<b>Target:</b>     ₹{target:,.2f}\n"
        f"<b>R:R Ratio:</b>  {rr:.1f}x\n"
        f"<b>Risk:</b>       ₹{risk:,.0f}\n\n"
        f"🤖 <i>Groq (Analyst) + Claude (Strategist) consensus</i>"
    )
    send_telegram_alert(msg)
    logger.info(f"✅ Trade executed: {ticker} {action} {quantity}@₹{entry_price}")
    return trade


# ── Hourly P&L Report ─────────────────────────────────────────────────────────

def hourly_pnl_report():
    """Called by scheduler every hour — sends P&L summary to Telegram."""
    logger.info("📊 Sending hourly P&L report to Telegram...")
    send_hourly_pnl_report(TRADING_STATE)


# ── Main Scan ─────────────────────────────────────────────────────────────────

def autonomous_scan():
    """
    Full dual-brain scan of all watchlist stocks.
    Called on boot and then every hour by the scheduler.
    """
    _reset_daily_counters_if_new_day()

    now = datetime.now().strftime("%Y-%m-%d %H:%M IST")
    logger.info("=" * 70)
    logger.info(f"🚀 Dual-Brain Scan | {len(WATCHLIST)} stocks | {now}")
    logger.info("=" * 70)

    send_telegram_alert(
        f"🧠 <b>Dual-Brain Scan Starting</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"Stocks: {len(WATCHLIST)} | Time: {now}\n"
        f"Models: Groq (llama-3.3-70b) + Claude (haiku-3-5)"
    )

    # Initialise the dual-brain
    try:
        brain = DualBrainOrchestrator(
            call_function_fn=call_function,
            execute_trade_fn=execute_trade,
            trading_state=TRADING_STATE
        )
    except ValueError as e:
        logger.error(f"❌ Cannot start: {e}")
        send_telegram_alert(f"❌ <b>Scan Aborted</b>\n{e}")
        return

    scan_results   = []
    signals_found  = 0
    errors_found   = 0

    for i, ticker in enumerate(WATCHLIST, 1):
        logger.info(f"[{i:02d}/{len(WATCHLIST)}] Analysing {ticker}...")

        # Hard stop: daily loss limit
        if abs(TRADING_STATE["daily_loss"]) >= 2_500_000:
            logger.warning("🛑 Daily loss limit hit — halting scan.")
            send_telegram_alert("🛑 <b>Daily Loss Limit Hit</b>\nScan halted.")
            break

        # Hard stop: max trades
        if TRADING_STATE["trades_today"] >= 50:
            logger.warning("🛑 Max daily trades (50) reached — halting scan.")
            break

        result = brain.analyze_stock(ticker)
        scan_results.append(result)

        if result.get("trade_executed"):
            signals_found += 1
        if result.get("error"):
            errors_found  += 1

        # Sleep between stocks to respect rate limits
        # Groq free tier: 1,000 RPD → ~100 calls per scan → 30s sleep is safe
        if i < len(WATCHLIST):
            logger.info(f"  ⏳ Rate-limit sleep 30s...")
            time.sleep(30)

    # ── Post-scan summary ────────────────────────────────────────────────────
    total_pnl = sum(t.get("pnl", 0) for t in TRADING_STATE["closed_trades"])
    summary   = (
        f"✅ <b>Dual-Brain Scan Complete</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n"
        f"<b>Stocks Scanned:</b>    {len(scan_results)}/{len(WATCHLIST)}\n"
        f"<b>Signals Executed:</b>  {signals_found}\n"
        f"<b>Errors:</b>            {errors_found}\n"
        f"<b>Trades Today:</b>      {TRADING_STATE['trades_today']}/50\n"
        f"<b>Open Positions:</b>    {len(TRADING_STATE['open_positions'])}\n"
        f"<b>Realized P&amp;L:</b>      ₹{total_pnl:+,.2f}\n"
        f"<b>Finished:</b>          {datetime.now().strftime('%H:%M IST')}\n\n"
        f"🤖 <i>Next scan in 1 hour</i>"
    )
    logger.info(summary.replace("<b>", "").replace("</b>", "").replace("<i>", "").replace("</i>", ""))
    send_telegram_alert(summary)

    # Save scan log for debugging
    try:
        log_path = Path(__file__).parent.parent / "logs" / "last_scan.json"
        log_path.parent.mkdir(exist_ok=True)
        with open(log_path, "w") as f:
            json.dump(scan_results, f, indent=2, default=str)
        logger.info(f"📄 Scan log saved: {log_path}")
    except Exception as e:
        logger.warning(f"Could not save scan log: {e}")


# ── CLI entry (when not using Gunicorn) ──────────────────────────────────────

def main():
    """Standalone CLI runner — used for local testing."""
    import schedule

    log_path = Path(__file__).parent.parent / "logs" / "autonomous.log"
    log_path.parent.mkdir(exist_ok=True)
    logger.add(str(log_path), rotation="100 MB", retention="7 days")

    logger.info("🏦 AlphaV-7 Dual-Brain — CLI mode starting")

    # Verify Telegram on startup
    verify_telegram_connection()

    # First scan immediately
    autonomous_scan()

    # Schedule hourly scan + hourly P&L
    schedule.every(1).hours.do(autonomous_scan)
    schedule.every(1).hours.do(hourly_pnl_report)

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Shutdown requested — bye.")
            break
        except Exception as e:
            logger.error(f"Scheduler error: {e}")
            time.sleep(60)


if __name__ == "__main__":
    main()
