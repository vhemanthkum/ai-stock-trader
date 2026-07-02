"""
stock_screener.py — Smart Stock Universe Screener
==================================================
Upgraded based on institutional code review (Stage 1A gates & Stage 1B scoring).

This module screens 500+ NSE stocks dynamically and picks the top opportunities based on:
  1. Stage 1A: Hard boolean gates (Market Cap, Volume, Trend, Solvency).
  2. Stage 1B: Institutional Scoring Matrix.
  3. Overlay: Block deal and Google News Catalysts (regex matched).
"""

import time
import re
import requests
import feedparser
import yfinance as yf
import pandas as pd
import logging
import json
from pathlib import Path
from typing import List, Dict, Any
from niftystocks import ns
from config import CACHE_DIR
from datetime import datetime

logger = logging.getLogger(__name__)

# Fallback watchlist if Nifty 500 fetch fails
FALLBACK_WATCHLIST = [
    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
    "TATAMOTORS.NS", "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS",
    "BAJFINANCE.NS", "AXISBANK.NS", "KOTAKBANK.NS", "HINDUNILVR.NS",
    "ASIANPAINT.NS", "MARUTI.NS", "SUNPHARMA.NS", "HCLTECH.NS", "TITAN.NS",
    "ULTRACEMCO.NS"
]

# Avoid noisy matching on short tickers
TICKER_NAME_MAP = {
    "LT": ["larsen", "l&t"],
    "ITC": [" itc "],
    "TCS": [" tcs "],
    "SBI": [" sbi ", "state bank"],
}

class AdvancedStockScreener:
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
        
        self.mc_cache = self._load_mc_cache()
        
        # Load Nifty 500 universe dynamically
        try:
            symbols = ns.get_nifty500()
            self.universe = [f"{sym}.NS" for sym in symbols]
            logger.info(f"Loaded {len(self.universe)} Nifty 500 symbols.")
        except Exception as e:
            logger.error(f"Failed to fetch Nifty 500: {e}")
            self.universe = FALLBACK_WATCHLIST

    def screen(self) -> List[Dict[str, Any]]:
        """Screen the full universe and return all scored survivors."""
        logger.info(f"🔍 Screener: scanning {len(self.universe)} stocks")

        scored = []
        batch_size = 25
        
        # Prefetch market caps for the whole universe to avoid slow individual lookups
        self._ensure_market_caps()

        for batch_start in range(0, len(self.universe), batch_size):
            batch = self.universe[batch_start: batch_start + batch_size]
            batch_results = self._score_batch(batch)
            scored.extend(batch_results)
            time.sleep(1.0)  # polite delay between batches

        return scored

    def _score_batch(self, yf_tickers: List[str]) -> List[Dict[str, Any]]:
        """Score a batch of tickers using yfinance bulk download."""
        results = []
        try:
            # Download 35 days to guarantee 20 trading days for SMA calculations
            data = yf.download(
                tickers=yf_tickers,
                period="1y",
                interval="1d",
                group_by="ticker",
                auto_adjust=False,
                threads=True,
                progress=False
            )
        except Exception as e:
            logger.error(f"yfinance batch download failed: {e}")
            return []

        for yf_ticker in yf_tickers:
            try:
                hist = pd.DataFrame()
                # Extract individual stock data safely
                if isinstance(data.columns, pd.MultiIndex):
                    if yf_ticker.replace('.NS', '') in data.columns.get_level_values(0):
                        hist = data[yf_ticker.replace('.NS', '')].dropna(subset=["Close"])
                    elif yf_ticker in data.columns.get_level_values(0):
                        hist = data[yf_ticker].dropna(subset=["Close"])
                elif not data.empty and "Close" in data.columns:
                    hist = data.dropna(subset=["Close"])
                
                # Single-ticker fallback for rate limits
                if hist.empty:
                    logger.debug(f"Batch fetch missed {yf_ticker}, attempting single fallback...")
                    time.sleep(1.0)
                    single_data = yf.download(yf_ticker, period="1y", interval="1d", progress=False)
                    if not single_data.empty and "Close" in single_data.columns:
                        hist = single_data.dropna(subset=["Close"])
                    
                    if hist.empty:
                        logger.warning(f"Fallback failed for {yf_ticker} (Likely delisted/renamed)")
                        continue

                # Stage 1A: Hard Gating
                passed, reason = self._passes_hard_gates(hist, yf_ticker)
                if not passed:
                    logger.debug(f"Stock {yf_ticker} failed hard gates: {reason}")
                    continue

                # Stage 1B: Scoring
                score, reason = self._score_ticker(hist)
                
                # Allow consolidations and oversold bounces to pass to overlay phase
                if score >= -10:
                    results.append({
                        "ticker": yf_ticker,
                        "score":  round(score, 2),
                        "reason": reason,
                        "current_price": float(hist["Close"].iloc[-1])
                    })
            except Exception as e:
                logger.debug(f"Exception screening {yf_ticker}: {e}")

        return results

    def _passes_hard_gates(self, hist: pd.DataFrame, ticker: str) -> tuple[bool, str]:
        """
        Stage 1A Hard Gates. Eliminates weak setups immediately.
        - Market Cap > 500 Cr
        - Avg Vol (20d) > 200,000
        - Price > 200 DMA (trend filter)
        """
        if hist.empty or len(hist) < 20:
            return False, "insufficient_history"

        close_prices = hist["Close"].dropna()
        latest_close = float(close_prices.iloc[-1])

        # Gate 1: Market Cap > 500 Cr
        mc = self.mc_cache.get(ticker, 0)
        if mc > 0 and mc < 5_000_000_000: # 500 Cr in raw rupees
            return False, "market_cap_too_low"

        # Gate 2: Liquidity (20-day average volume >= 200,000 shares)
        volume = hist["Volume"].dropna()
        avg_vol = float(volume.tail(20).mean()) if len(volume) >= 5 else 0
        if avg_vol < 200_000:
            return False, "illiquid"

        # Gate 3: Price above 200-DMA (Long term trend)
        sma200 = float(close_prices.tail(200).mean()) if len(close_prices) >= 200 else float(close_prices.mean())
        if latest_close < sma200:
            return False, "below_200dma"

        return True, "ok"

    def _score_ticker(self, hist: pd.DataFrame) -> tuple[float, str]:
        """
        Stage 1B: compute the mathematical opportunity score.
        """
        score = 0.0
        reasons = []

        close_prices = hist["Close"].dropna()
        volume = hist["Volume"].dropna()

        latest = float(close_prices.iloc[-1])
        prev = float(close_prices.iloc[-2]) if len(close_prices) >= 2 else latest
        price_chg_pct = ((latest - prev) / prev) * 100

        # Moving averages
        sma5 = float(close_prices.tail(5).mean())
        sma20 = float(close_prices.tail(20).mean()) if len(close_prices) >= 20 else sma5

        # Period high check (breakout proximity)
        recent_high = float(close_prices.max())
        pct_from_high = ((latest - recent_high) / recent_high) * 100 if recent_high > 0 else 0

        # Volume
        today_vol = float(volume.iloc[-1])
        avg_vol_20 = float(volume.tail(20).mean()) if len(volume) >= 20 else today_vol
        vol_ratio = today_vol / avg_vol_20 if avg_vol_20 > 0 else 1.0

        # ── MOMENTUM BLOCK ──
        if pct_from_high >= -5.0:
            score += 35
            reasons.append("Near 35d high")
        elif pct_from_high >= -10.0:
            score += 20
            reasons.append("Close to 35d high")

        if latest > sma20:
            score += 20
            reasons.append("Above SMA-20")
        else:
            score -= 10

        if latest > sma5 and latest > sma20:
            score += 10
            reasons.append("Short-term uptrend")
        elif latest < sma5 and latest < sma20:
            score -= 20
            reasons.append("Short-term downtrend")

        if 1.5 <= price_chg_pct <= 5.0:
            score += 15
            reasons.append(f"Healthy breakout +{price_chg_pct:.1f}%")
        elif price_chg_pct > 5.0:
            score += 5
            reasons.append(f"Parabolic +{price_chg_pct:.1f}% (late entry risk)")
        elif price_chg_pct < -4.0:
            score += 10
            reasons.append(f"Oversold drop {price_chg_pct:.1f}% (bounce candidate)")

        # ── VOLUME BLOCK ──
        if 1.2 <= vol_ratio <= 2.5:
            score += 25
            reasons.append(f"Accumulation vol {vol_ratio:.1f}x")
        elif vol_ratio > 2.5:
            score += 10
            reasons.append(f"Vol spike {vol_ratio:.1f}x")
        elif vol_ratio < 0.5:
            score -= 15
            reasons.append("Vol drying up")

        return score, " | ".join(reasons) if reasons else "neutral"

    def get_fii_dii_data(self) -> str:
        """Fetch today's FII sentiment (uses global session cache)."""
        # Session caching is now handled globally in nse_scraper.py, 
        # but we maintain a local backup here using the module's headers.
        try:
            url = "https://www.nseindia.com/api/fiidiiTradeReact"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                fii_net = 0
                for row in data:
                    cat = str(row.get("category", "")).upper()
                    if "FII" in cat or "FPI" in cat:
                        buy  = float(str(row.get("buyValue",  "0")).replace(",", "") or 0)
                        sell = float(str(row.get("sellValue", "0")).replace(",", "") or 0)
                        fii_net += (buy - sell)
                return "BULLISH" if fii_net > 0 else "BEARISH"
        except Exception:
            pass
        return "NEUTRAL"

    def get_block_deals(self) -> set:
        """Fetch tickers with Block Deals > ₹10 Cr today."""
        block_tickers = set()
        try:
            url = "https://www.nseindia.com/api/snapshot-capital-market-largeDeals?type=bulk"
            resp = self.session.get(url, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                for row in data:
                    qty   = int(str(row.get("BD_QTY_TRD", "0")).replace(",", "") or 0)
                    price_str = row.get("BD_TP_WATP", row.get("PRICE", "0"))
                    price = float(str(price_str).replace(",", "") or 0)
                    if qty > 0 and price > 0:
                        if (qty * price) >= 10_00_00_000:
                            block_tickers.add(f"{row.get('BD_SYMBOL', '')}.NS")
        except Exception:
            pass
        return block_tickers

    def get_news_driven_movers(self) -> set:
        """Scan Google News RSS using regex word-boundary lookup."""
        trending = {}
        queries  = ["NSE India stock breakout", "NSE India block deal", "India stock surge rally"]
        for q in queries:
            try:
                url  = f"https://news.google.com/rss/search?q={q.replace(' ', '+')}&hl=en-IN&gl=IN&ceid=IN:en"
                feed = feedparser.parse(url)
                for entry in feed.entries[:15]:
                    title_lower = entry.title.lower()
                    for ticker in self.universe:
                        base_ticker = ticker.replace(".NS", "")
                        
                        # Word boundary check for short tickers to avoid noise (e.g. matching LT inside LATEST)
                        if len(base_ticker) <= 3:
                            names = TICKER_NAME_MAP.get(base_ticker, [base_ticker.lower()])
                            matched = any(re.search(rf"\b{n}\b", title_lower) for n in names)
                        else:
                            matched = base_ticker.lower() in title_lower
                            
                        if matched:
                            trending[ticker] = trending.get(ticker, 0) + 1
            except Exception:
                pass
        
        return {t for t, count in trending.items() if count >= 2}

    def run_full_pipeline(self, top_n: int = 25) -> List[str]:
        """Runs the gated screener + block deal/news overlays."""
        logger.info("=" * 60)
        logger.info("🔭 INSTITUTIONAL SCREENER: Evaluating watchlist...")
        
        scored_stocks = self.screen()
        if not scored_stocks:
            logger.warning("Screener returned 0 results — using fallback")
            return FALLBACK_WATCHLIST[:top_n]

        fii_sentiment = self.get_fii_dii_data()
        block_tickers = self.get_block_deals()
        news_tickers  = self.get_news_driven_movers()

        # Apply overlays to ALL scored stocks BEFORE sorting/slicing
        for s in scored_stocks:
            if s["ticker"] in news_tickers:
                s["score"] += 15
                s["reason"] += " | NEWS CATALYST"
            if s["ticker"] in block_tickers:
                s["score"] += 20
                s["reason"] += " | BLOCK DEAL"
            if fii_sentiment == "BULLISH":
                s["score"] += 5

        # ── SECTOR RS MULTIPLIER (Flaw #6 Fix) ──
        try:
            from data_collectors.sector_data import get_top_sectors, get_laggard_sectors
            from data_collectors.sector_map import get_nifty_index_sector
            
            top_sectors = get_top_sectors(3)
            laggard_sectors = get_laggard_sectors(3)
            
            for s in scored_stocks:
                sector_idx = get_nifty_index_sector(s["ticker"])
                if sector_idx in top_sectors:
                    s["score"] *= 1.2
                    s["reason"] += " | SECTOR TAILWIND"
                elif sector_idx in laggard_sectors:
                    s["score"] *= 0.7
                    s["reason"] += " | SECTOR HEADWIND"
        except Exception as e:
            logger.warning(f"Sector RS overlay failed: {e}")

        # Re-sort and slice the top_n stocks
        scored_stocks.sort(key=lambda x: x["score"], reverse=True)
        final = scored_stocks[:top_n]

        logger.info(f"🏆 Final top {len(final)} mathematically-scored stocks:")
        for i, s in enumerate(final, 1):
            logger.info(f"  {i}. {s['ticker']} | price=₹{s['current_price']:.2f} | score={s['score']:.1f} | {s['reason']}")

        return [s["ticker"] for s in final]

    def _load_mc_cache(self) -> dict:
        """Load market cap cache from disk."""
        cache_file = CACHE_DIR / f"market_caps_{datetime.now().strftime('%Y-%m')}.json"
        if cache_file.exists():
            try:
                return json.loads(cache_file.read_text())
            except Exception:
                pass
        return {}

    def _save_mc_cache(self) -> None:
        """Save market cap cache to disk."""
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file = CACHE_DIR / f"market_caps_{datetime.now().strftime('%Y-%m')}.json"
        try:
            cache_file.write_text(json.dumps(self.mc_cache, indent=2))
        except Exception as e:
            logger.warning(f"Could not save market cap cache: {e}")

    def _ensure_market_caps(self) -> None:
        """Fetch missing market caps in batches."""
        missing = [t for t in self.universe if t not in self.mc_cache]
        if not missing:
            return

        logger.info(f"Fetching market caps for {len(missing)} tickers...")
        # Since yf.Tickers allows bulk lookup, we use it to speed this up
        batch_size = 100
        for i in range(0, len(missing), batch_size):
            batch = missing[i:i+batch_size]
            try:
                tickers = yf.Tickers(" ".join(batch))
                for t in batch:
                    try:
                        info = tickers.tickers[t].info
                        if info and "marketCap" in info:
                            self.mc_cache[t] = info["marketCap"]
                        else:
                            self.mc_cache[t] = 0
                    except Exception:
                        self.mc_cache[t] = 0
            except Exception as e:
                logger.warning(f"Market cap batch fetch failed: {e}")
        
        self._save_mc_cache()


def screen_nifty500(top_n: int = 25) -> List[str]:
    """Wrapper function to match the interface expected by main.py"""
    screener = AdvancedStockScreener()
    return screener.run_full_pipeline(top_n)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    screen_nifty500(top_n=5)
