#!/usr/bin/env python3
import os
import sys
from pathlib import Path
import schedule
import time
from loguru import logger
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))
from trading_agent import InstitutionalTradingAgent

agent = InstitutionalTradingAgent()

# Top 100 NSE Stocks (Nifty 100)
WATCHLIST = [
    "RELIANCE", "TCS", "HDFC", "INFY", "ICICIBANK", "HUL", "ITC", "SBI", "BHARTIARTL", "KOTAKBANK",
    "LT", "BAJFINANCE", "ASIANPAINT", "AXISBANK", "MARUTI", "SUNPHARMA", "TITAN", "ULTRACEMCO", "WIPRO",
    "TATASTEEL", "POWERGRID", "NTPC", "M&M", "HCLTECH", "BAJAJFINSV", "NESTLEIND", "TECHM", "ONGC",
    "JSWSTEEL", "HINDALCO", "TATAMOTORS", "GRASIM", "INDUSINDBK", "ADANIPORTS", "ADANIENT", "DIVISLAB",
    "CIPLA", "APOLLOHOSP", "BAJAJ-AUTO", "COALINDIA", "EICHERMOT", "TATACONSUM", "DRREDDY", "HEROMOTOCO",
    "BRITANNIA", "UPL", "BPCL", "INDIGO", "PIDILITIND", "HDFCLIFE", "SBILIFE", "TVSMOTOR", "HAL",
    "BEL", "TRENT", "CHOLAFIN", "BANKBARODA", "PNB", "CANBK", "ZOMATO", "JIOFIN", "DLF", "LODHA",
    "GODREJPROP", "TORNTPHARM", "AUROPHARMA", "LUPIN", "ALKEM", "MRF", "BOSCHLTD", "CUMMINSIND",
    "SIEMENS", "ABB", "POLYCAB", "HAVELLS", "VOLTAS", "DIXON", "TATACOMM", "PERSISTENT", "LTIM",
    "COFORGE", "MPHASIS", "RECLTD", "PFC", "IRFC", "TATACHEM", "DEEPAKNTR", "PIIND", "NAUKRI",
    "SRF", "AUBANK", "IDFCFIRSTB", "BANDHANBNK", "MUTHOOTFIN", "SHRIRAMFIN", "M&MFIN", "ICICIGI", "ICICIPRULI"
]

def autonomous_scan():
    logger.info("=" * 80)
    logger.info(f"Starting Autonomous Market Scan of {len(WATCHLIST)} stocks at {datetime.now().strftime('%H:%M:%S')}")
    logger.info("=" * 80)
    
    for ticker in WATCHLIST:
        logger.info(f"Triggering Orchestrator for {ticker}...")
        prompt = f"""
AUTONOMOUS TASK: Perform a comprehensive review on {ticker}. 
1. Use your tools to fetch fundamentals, technicals, news, and social sentiment.
2. Analyze the ingested data.
3. Decide if you should execute a BUY, SELL, or HOLD. 
4. If executing, USE THE execute_trade TOOL directly. 
Do not wait for my permission. You are autonomous.
"""
        response = agent.chat(prompt)
        logger.info(f"Agent Final Log for {ticker}: {response.strip()}")
        
        # INCREASED DELAY: Scanning 100 stocks hits APIs 400+ times. 
        # Groq and Yahoo Finance will ban the IP if requests are too fast.
        logger.info(f"Sleeping for 15 seconds to prevent API Rate Limits...")
        time.sleep(15)  
        
    logger.info("Autonomous scan complete. Sleeping until next schedule.")

def main():
    logger.add("../logs/autonomous.log", rotation="500 MB")
    logger.info("Initializing Autonomous Orchestrator (1-Hour Loop)")
    
    # Run once immediately on startup
    autonomous_scan()
    
    # Schedule to run every hour
    schedule.every(1).hours.do(autonomous_scan)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except KeyboardInterrupt:
            logger.info("Autonomous Orchestrator terminating.")
            break

if __name__ == "__main__":
    main()
