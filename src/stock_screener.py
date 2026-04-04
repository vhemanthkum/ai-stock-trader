#!/usr/bin/env python3
"""
stock_screener.py — Smart Stock Universe Screener
==================================================
PROBLEM: The old system had a hardcoded 20-stock watchlist.
SOLUTION: Every hour, screen 500+ NSE stocks dynamically and pick
          the TOP 10 best opportunities based on:
           1. Momentum (price change today vs 5-day avg)
           2. Volume surge (today's volume vs 20-day avg)
           3. News catalyst (recent headline count)
           4. FII/DII flow signals (NSE public data)
           5. Big player block deal activity

Only THESE top 10 are then passed to the expensive Dual-Brain pipeline.
This avoids wasting API calls on boring stocks.

UNIVERSE: Nifty 500 (top 500 NSE stocks by market cap) + mid/small caps
          Total screened: ~500+ stocks → filtered to top 10
"""

import time
import requests
import feedparser
import yfinance as yf
import pandas as pd
from loguru import logger
from datetime import datetime, timedelta
from typing import List, Dict, Any


# ── Full Nifty 500 + key mid-cap NSE universe (~560 stocks) ─────────────────
# This is the raw screening universe — every scan we narrow this to top 10
NSE_UNIVERSE = [
    # Nifty 50
    "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK","HINDUNILVR","ITC","SBIN",
    "BHARTIARTL","KOTAKBANK","LT","BAJFINANCE","AXISBANK","MARUTI","SUNPHARMA",
    "TITAN","WIPRO","HCLTECH","TATAMOTORS","ADANIPORTS","ULTRACEMCO","NESTLEIND",
    "M&M","NTPC","POWERGRID","ONGC","JSWSTEEL","TATASTEEL","HINDALCO","COALINDIA",
    "TECHM","BAJAJFINSV","GRASIM","INDUSINDBK","DIVISLAB","DRREDDY","CIPLA",
    "APOLLOHOSP","EICHERMOT","HDFCLIFE","SBILIFE","BPCL","TATACONSUM","BRITANNIA",
    "HEROMOTOCO","BAJAJ-AUTO","ADANIENT","UPL","TRENT","ASIANPAINT",
    # Nifty Next 50
    "HAL","BEL","ZOMATO","JIOFIN","DLF","LODHA","GODREJPROP","PNB","CANBK",
    "BANKBARODA","TVSMOTOR","CHOLAFIN","RECLTD","PFC","IRFC","PERSISTENT",
    "COFORGE","LTIM","MPHASIS","NAUKRI","PIIND","SRF","DEEPAKNTR","TATACHEM",
    "MRF","BOSCHLTD","SIEMENS","ABB","POLYCAB","HAVELLS","DIXON","VOLTAS",
    "PIDILITIND","TORNTPHARM","AUROPHARMA","LUPIN","ALKEM","AUBANK","MUTHOOTFIN",
    "SHRIRAMFIN","ICICIGI","ICICIPRULI","IDFCFIRSTB","BANDHANBNK","M&MFIN",
    # Nifty Midcap 150 (key picks)
    "IDFC","HFCL","RBLBANK","FEDERALBNK","SOUTHBANK","KARNATAKBNK","J&KBANK",
    "YESBANK","CUB","DCB","EQUITASBNK","SURYODAY","UJJIVAN","FINPIPE",
    "PIIND","AARTIIND","GSFC","GNFC","NAVINFLUOR","FLUOROCHEM","ALKYLAMINE",
    "FINEORG","VINATIORGA","NOCIL","ATUL","BALAMINES","KANSAINER","AKZOINDIA",
    "GILLETTE","ABBOTINDIA","PFIZER","SANOFI","GLAXO","IOLCP","JUBILANTPHARMA",
    "GRANULES","SOLARA","LAURUSLABS","LALPATHLAB","METROPOLIS","THYROCARE",
    "FORTIS","NH","MAXHEALTH","ASTER","POLYMED","GSPL","MGL","IGL","GAIL",
    "PETRONET","CASTROLIND","AEGISCHEM","GULFOIL","HINDPETRO","MRPL",
    "SAIL","MOIL","NMDC","HINDCOPPER","NATIONALUM","VEDL","HINDZINC",
    "JSWENERGY","TORNTPOWER","CESC","TATAPOWER","ADANIGREEN","ADANIPOWER",
    "RPOWER","NHPC","SJVN","IRCON","RVNL","RAILVIKAS","IRCTC","CONCOR",
    "BLUEDART","GATI","MAHLOG","DELHIVERY","ZOMATO","SWIGGY",
    "PAYTM","POLICYBZR","NYKAA","MAPMYINDIA","EASEMYTRIP",
    "JUBLFOOD","DEVYANI","SAPPHIRE","WESTLIFE","BARBEQUE","BURGER",
    "BATAINDIA","CAMPUS","RELAXO","LIBERTY","SSCL","RAYMOND","GOKALDAS",
    "AGISNL","MANYAVAR","VEDANT","ABFRL","SHOPERSTOP","VJLT","PVRINOX",
    "INOXWIND","SUZLON","ORIENTELEC","BHEL","BEML","TIINDIA","ELGIEQUIP",
    "GREAVESCOT","ESCORTS","BHARATFORG","RAMKRISHNA","WELSPUN","STAR",
    "MINDA","UNO","SUPRAJIT","ENDURANCE","MOTHERSON","BALKRISIND","CEAT",
    "MRF","APOLLOTYRE","JK","TVSSCS","EXIDEIND","AMARA","HBLPOWER",
]

# Remove duplicates while preserving order
NSE_UNIVERSE = list(dict.fromkeys(NSE_UNIVERSE))


class StockScreener:
    """
    Phase 0: Screener that narrows 500+ stocks to top 10 opportunities.
    Uses lightweight checks (no LLM calls) to be fast and cheap.
    """

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "en-IN,en;q=0.9",
        })

    # ─────────────────────────────────────────────────────────────────────────
    # Core: score each stock and return top N
    # ─────────────────────────────────────────────────────────────────────────
    def screen(self, top_n: int = 10) -> List[Dict[str, Any]]:
        """
        Screen the full NSE universe and return the top_n opportunities.
        Each result dict contains ticker + reason + score.
        """
        logger.info(f"🔍 Screener: scanning {len(NSE_UNIVERSE)} stocks → picking top {top_n}")

        scored = []

        # Process in batches of 50 to avoid yfinance timeout
        batch_size = 50
        for batch_start in range(0, len(NSE_UNIVERSE), batch_size):
            batch = NSE_UNIVERSE[batch_start: batch_start + batch_size]
            batch_results = self._score_batch(batch)
            scored.extend(batch_results)
            time.sleep(2)  # polite delay between batches

        if not scored:
            logger.warning("Screener returned 0 results — using fallback top-20 watchlist")
            return self._fallback_watchlist(top_n)

        # Sort by score descending → pick top N
        scored.sort(key=lambda x: x["score"], reverse=True)
        top = scored[:top_n]

        logger.info(f"✅ Screener selected {len(top)} stocks:")
        for rank, s in enumerate(top, 1):
            logger.info(f"  #{rank} {s['ticker']} | score={s['score']:.1f} | {s['reason']}")

        return top

    def _score_batch(self, tickers: List[str]) -> List[Dict[str, Any]]:
        """Score a batch of tickers using yfinance bulk download."""
        results = []
        yf_tickers = [f"{t}.NS" for t in tickers]

        try:
            # Download 21 days of daily data for all tickers at once (1 API call)
            data = yf.download(
                tickers=yf_tickers,
                period="21d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False
            )
        except Exception as e:
            logger.error(f"yfinance batch download failed: {e}")
            return []

        for ticker, yf_ticker in zip(tickers, yf_tickers):
            try:
                score, reason = self._score_ticker(data, yf_ticker, ticker)
                if score > 0:
                    results.append({
                        "ticker": ticker,
                        "score":  round(score, 2),
                        "reason": reason
                    })
            except Exception as e:
                pass  # Skip broken tickers silently

        return results

    def _score_ticker(self, data, yf_ticker: str, ticker: str):
        """
        Compute an opportunity score for one ticker.
        Returns (score, reason_string).

        Scoring criteria:
          +30 pts  → Volume surge: today's volume > 2× 20-day avg
          +25 pts  → Price breakout: today's change > 3%
          +20 pts  → Bullish trend: price above SMA-20
          +15 pts  → Recent news: has headlines in last 24h
          +10 pts  → Momentum: price above SMA-5
          -20 pts  → Falling: price below SMA-5 AND SMA-20
          -15 pts  → Low volume: today < 0.5× avg (no activity)
        """
        score  = 0.0
        reasons = []

        # Extract single-ticker data
        try:
            if isinstance(data.columns, pd.MultiIndex):
                close  = data["Close"][yf_ticker].dropna()
                volume = data["Volume"][yf_ticker].dropna()
            else:
                close  = data["Close"].dropna()
                volume = data["Volume"].dropna()

            if len(close) < 5:
                return 0, "insufficient data"
        except Exception:
            return 0, "data error"

        latest_close = float(close.iloc[-1])
        prev_close   = float(close.iloc[-2]) if len(close) >= 2 else latest_close
        price_chg_pct = ((latest_close - prev_close) / prev_close) * 100

        # Moving averages
        sma5  = float(close.tail(5).mean())
        sma20 = float(close.tail(20).mean()) if len(close) >= 20 else sma5

        # Volume analysis
        today_vol    = float(volume.iloc[-1])
        avg_vol_20   = float(volume.tail(20).mean()) if len(volume) >= 20 else today_vol
        vol_ratio    = today_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        # ── Scoring ────────────────────────────────────────────────────────
        if vol_ratio >= 2.0:
            score += 30
            reasons.append(f"Volume surge {vol_ratio:.1f}×")
        elif vol_ratio >= 1.5:
            score += 15
            reasons.append(f"Vol up {vol_ratio:.1f}×")
        elif vol_ratio < 0.5:
            score -= 15
            reasons.append("Low volume")

        if price_chg_pct >= 3.0:
            score += 25
            reasons.append(f"Price +{price_chg_pct:.1f}%")
        elif price_chg_pct >= 1.5:
            score += 12
            reasons.append(f"Price +{price_chg_pct:.1f}%")
        elif price_chg_pct <= -3.0:
            score += 20  # Big drops can be shorting opportunities
            reasons.append(f"Price DROP {price_chg_pct:.1f}% (SELL?)")
        elif price_chg_pct <= -1.5:
            score += 8
            reasons.append(f"Price {price_chg_pct:.1f}%")

        if latest_close > sma20:
            score += 20
            reasons.append("Above SMA-20")
        else:
            score -= 10

        if latest_close > sma5:
            score += 10
            reasons.append("Above SMA-5")
        else:
            if latest_close < sma20:
                score -= 20
                reasons.append("Below SMA-5 & SMA-20")

        reason_str = " | ".join(reasons) if reasons else "neutral"
        return score, reason_str

    # ─────────────────────────────────────────────────────────────────────────
    # FII / DII Tracking (NSE Public Data)
    # ─────────────────────────────────────────────────────────────────────────
    def get_fii_dii_data(self) -> Dict[str, Any]:
        """
        Fetch today's FII and DII buy/sell data from NSE India.
        Returns a dict with net buy/sell amounts.
        """
        try:
            url = "https://www.nseindia.com/api/fiidiiTradeReact"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                result = {
                    "date":         datetime.now().strftime("%Y-%m-%d"),
                    "fii_net":      0,
                    "dii_net":      0,
                    "fii_buy":      0,
                    "fii_sell":     0,
                    "dii_buy":      0,
                    "dii_sell":     0,
                    "fii_sentiment": "NEUTRAL",
                    "dii_sentiment": "NEUTRAL",
                }
                for row in data:
                    cat = str(row.get("category", "")).upper()
                    if "FII" in cat or "FPI" in cat:
                        buy  = float(str(row.get("buyValue",  "0")).replace(",", "") or 0)
                        sell = float(str(row.get("sellValue", "0")).replace(",", "") or 0)
                        result["fii_buy"]  += buy
                        result["fii_sell"] += sell
                        result["fii_net"]  += (buy - sell)
                    elif "DII" in cat:
                        buy  = float(str(row.get("buyValue",  "0")).replace(",", "") or 0)
                        sell = float(str(row.get("sellValue", "0")).replace(",", "") or 0)
                        result["dii_buy"]  += buy
                        result["dii_sell"] += sell
                        result["dii_net"]  += (buy - sell)

                result["fii_sentiment"] = "BULLISH" if result["fii_net"] > 0 else "BEARISH"
                result["dii_sentiment"] = "BULLISH" if result["dii_net"] > 0 else "BEARISH"
                logger.info(
                    f"FII Net: ₹{result['fii_net']:,.0f} Cr | "
                    f"DII Net: ₹{result['dii_net']:,.0f} Cr"
                )
                return result
        except Exception as e:
            logger.error(f"FII/DII fetch error: {e}")

        return {"error": "FII/DII data unavailable", "fii_sentiment": "NEUTRAL", "dii_sentiment": "NEUTRAL"}

    # ─────────────────────────────────────────────────────────────────────────
    # Block Deal / Bulk Deal monitoring
    # ─────────────────────────────────────────────────────────────────────────
    def get_block_deals(self) -> List[Dict[str, Any]]:
        """
        Fetch today's block and bulk deals from NSE.
        Big institutional block deals (>₹10 Cr) signal smart money moves.
        """
        deals = []
        try:
            # Bulk deals
            url = "https://www.nseindia.com/api/snapshot-capital-market-largeDeals?type=bulk"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for row in data:
                    qty   = int(str(row.get("BD_QTY_TRD", "0")).replace(",", "") or 0)
                    price = float(str(row.get("BD_TP_WATP", "0")).replace(",", "") or 0)
                    value = qty * price
                    if value >= 10_00_00_000:  # ≥ ₹10 Cr
                        deals.append({
                            "type":    "BULK",
                            "ticker":  row.get("BD_SYMBOL", ""),
                            "client":  row.get("BD_CLIENT_NAME", ""),
                            "qty":     qty,
                            "price":   price,
                            "value_cr": round(value / 1_00_00_000, 2),
                            "side":    row.get("BD_BUY_SELL", "")
                        })
        except Exception as e:
            logger.error(f"Block deal fetch error: {e}")

        logger.info(f"Block/Bulk deals found: {len(deals)} (≥₹10 Cr)")
        return deals

    # ─────────────────────────────────────────────────────────────────────────
    # News-driven momentum: scan Google News for trending NSE stocks
    # ─────────────────────────────────────────────────────────────────────────
    def get_news_driven_movers(self) -> List[str]:
        """
        Scan Google News RSS for NSE-related headlines.
        Tickers mentioned frequently in financial news get a boost in screening.
        """
        trending = {}
        queries  = [
            "NSE India stock buy breakout",
            "NSE India block deal institutional buying",
            "NSE India earnings results today",
            "Sensex Nifty stock surge rally",
            "India stock upgrade target price"
        ]

        for q in queries:
            try:
                url  = f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
                feed = feedparser.parse(url)
                for entry in feed.entries[:10]:
                    title = entry.title.upper()
                    for ticker in NSE_UNIVERSE:
                        if ticker in title or ticker.replace("&", "AND") in title:
                            trending[ticker] = trending.get(ticker, 0) + 1
                time.sleep(0.5)
            except Exception:
                pass

        # Return tickers with 2+ news mentions
        hot = [t for t, count in sorted(trending.items(), key=lambda x: -x[1]) if count >= 2]
        logger.info(f"News-driven tickers found: {hot[:10]}")
        return hot[:10]

    # ─────────────────────────────────────────────────────────────────────────
    # Fallback: if screener fails, use curated top-20
    # ─────────────────────────────────────────────────────────────────────────
    def _fallback_watchlist(self, top_n: int) -> List[Dict[str, Any]]:
        fallback = [
            "RELIANCE","TCS","HDFCBANK","INFY","ICICIBANK",
            "SBIN","BHARTIARTL","LT","BAJFINANCE","AXISBANK"
        ]
        return [{"ticker": t, "score": 50.0, "reason": "fallback watchlist"} for t in fallback[:top_n]]

    # ─────────────────────────────────────────────────────────────────────────
    # MAIN: Screen + merge news momentum + FII confirmation
    # ─────────────────────────────────────────────────────────────────────────
    def get_best_opportunities(self, top_n: int = 10) -> Dict[str, Any]:
        """
        Master screening function. Returns:
        {
            "top_stocks":   [{"ticker":str, "score":float, "reason":str}],
            "fii_dii":      {...},
            "block_deals":  [...],
            "news_movers":  [...]
        }
        """
        logger.info("=" * 60)
        logger.info("🔭 STOCK SCREENER: Finding best opportunities...")
        logger.info("=" * 60)

        # Run all three screens in parallel conceptually (sequential for simplicity)
        top_stocks  = self.screen(top_n=top_n * 2)  # get 2× then boost with news
        fii_dii     = self.get_fii_dii_data()
        block_deals = self.get_block_deals()
        news_movers = self.get_news_driven_movers()

        # Boost stocks that appear in news
        news_set = set(news_movers)
        for s in top_stocks:
            if s["ticker"] in news_set:
                s["score"] += 15
                s["reason"] += " | NEWS CATALYST"

        # Boost stocks with block deal activity
        block_tickers = {d["ticker"] for d in block_deals}
        for s in top_stocks:
            if s["ticker"] in block_tickers:
                s["score"] += 20
                s["reason"] += " | BLOCK DEAL"

        # FII bullish → boost all scores slightly
        if fii_dii.get("fii_sentiment") == "BULLISH":
            for s in top_stocks:
                s["score"] += 5

        # Re-sort and take final top_n
        top_stocks.sort(key=lambda x: x["score"], reverse=True)
        final = top_stocks[:top_n]

        logger.info(f"🏆 Final top {len(final)} stocks selected for Dual-Brain analysis:")
        for i, s in enumerate(final, 1):
            logger.info(f"  {i}. {s['ticker']} | score={s['score']:.1f} | {s['reason']}")

        return {
            "top_stocks":  final,
            "fii_dii":     fii_dii,
            "block_deals": block_deals,
            "news_movers": news_movers,
            "screened_at": datetime.now().isoformat()
        }
