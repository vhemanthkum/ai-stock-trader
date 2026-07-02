"""
NSE India data scraper.

Fetches:
- India VIX (current value)
- FII/DII daily activity (net buy/sell)
- Bulk/Block deals

Uses requests with proper headers to avoid NSE's 403 bot-protection.
Falls back to yfinance for VIX if direct NSE scraping fails.
"""

import json
import logging
from datetime import datetime, timedelta

import requests
import yfinance as yf
import pandas as pd

from config import CACHE_DIR

logger = logging.getLogger(__name__)

# NSE requires these headers to avoid 403
NSE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Referer": "https://www.nseindia.com/",
    "Connection": "keep-alive",
}

NSE_BASE = "https://www.nseindia.com"


_NSE_SESSION = None

def _get_nse_session() -> requests.Session:
    """Get or create cached session with NSE cookies."""
    global _NSE_SESSION
    if _NSE_SESSION is None:
        _NSE_SESSION = requests.Session()
        _NSE_SESSION.headers.update(NSE_HEADERS)
        try:
            # Visit homepage first to get cookies
            _NSE_SESSION.get(NSE_BASE, timeout=10)
        except Exception as e:
            logger.warning(f"Could not initialize NSE session: {e}")
    return _NSE_SESSION


def get_india_vix() -> float:
    """
    Fetch current India VIX value.
    Primary: yfinance (^INDIAVIX)
    Fallback: NSE API
    """
    # Method 1: yfinance (most reliable)
    try:
        vix = yf.Ticker("^INDIAVIX")
        hist = vix.history(period="5d")
        if not hist.empty:
            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)
            val = round(float(hist["Close"].iloc[-1]), 2)
            logger.info(f"India VIX (yfinance): {val}")
            return val
    except Exception as e:
        logger.warning(f"yfinance VIX fetch failed: {e}")

    # Method 2: Direct NSE API
    try:
        session = _get_nse_session()
        resp = session.get(f"{NSE_BASE}/api/allIndices", timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            for idx in data.get("data", []):
                if "VIX" in idx.get("indexSymbol", "").upper():
                    val = round(float(idx["last"]), 2)
                    logger.info(f"India VIX (NSE): {val}")
                    return val
    except Exception as e:
        logger.warning(f"NSE VIX fetch failed: {e}")

    # Fallback to a stable default
    logger.warning("Could not fetch India VIX, using default 15.0")
    return 15.0


def get_fii_dii_data() -> dict:
    """
    Fetch FII/DII net buying data.
    Returns daily flows for both FII and DII (honest value reporting).
    """
    fii_data = {"fii_today": 0.0, "dii_today": 0.0, "fii_3day_net": 0.0, "dii_3day_net": 0.0}

    try:
        session = _get_nse_session()
        resp = session.get(f"{NSE_BASE}/api/fiidiiTradeReact", timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            
            fii_buy = 0.0
            fii_sell = 0.0
            dii_buy = 0.0
            dii_sell = 0.0

            for entry in data:
                category = entry.get("category", "")
                if "FII" in category.upper() or "FPI" in category.upper():
                    fii_buy += float(entry.get("buyValue", 0))
                    fii_sell += float(entry.get("sellValue", 0))
                elif "DII" in category.upper():
                    dii_buy += float(entry.get("buyValue", 0))
                    dii_sell += float(entry.get("sellValue", 0))

            fii_net = round(fii_buy - fii_sell, 2)
            dii_net = round(dii_buy - dii_sell, 2)

            fii_data["fii_today"] = fii_net
            fii_data["dii_today"] = dii_net

            # Store to SQLite for real rolling sums (Flaw #4 fix)
            try:
                from storage.db import store_fii_daily, get_rolling_fii_net
                store_fii_daily(fii_net, dii_net)
                fii_rolling, dii_rolling = get_rolling_fii_net(days=3)
                fii_data["fii_3day_net"] = fii_rolling
                fii_data["dii_3day_net"] = dii_rolling
            except Exception as db_err:
                logger.warning(f"DB rolling sum failed, using today's value: {db_err}")
                fii_data["fii_3day_net"] = fii_net
                fii_data["dii_3day_net"] = dii_net

            logger.info(f"FII daily net: ₹{fii_net} Cr | DII daily net: ₹{dii_net} Cr")
            logger.info(f"FII 3-day rolling: ₹{fii_data['fii_3day_net']} Cr | DII 3-day rolling: ₹{fii_data['dii_3day_net']} Cr")
            return fii_data

    except Exception as e:
        logger.warning(f"FII/DII fetch failed: {e}")

    logger.warning("Using default FII/DII data (0)")
    return fii_data


def get_bulk_deals(ticker: str = "") -> list[dict]:
    """
    Fetch bulk deals from NSE.
    Any trade > 0.5% of company shares in single order.
    """
    deals = []
    try:
        session = _get_nse_session()
        resp = session.get(f"{NSE_BASE}/api/snapshot-capital-market-largedeal", timeout=10)
        
        if resp.status_code == 200:
            data = resp.json()
            bulk_data = data.get("BULK_DEALS_DATA", []) + data.get("BLOCK_DEALS_DATA", [])
            
            for deal in bulk_data:
                symbol = deal.get("symbol", "")
                # Filter for specific ticker if provided
                if ticker and ticker.replace(".NS", "") != symbol:
                    continue
                    
                deals.append({
                    "symbol": symbol,
                    "client": deal.get("clientName", ""),
                    "deal_type": deal.get("dealType", ""),
                    "quantity": deal.get("quantity", 0),
                    "price": deal.get("price", 0),
                    "date": deal.get("date", ""),
                })

            logger.info(f"Fetched {len(deals)} bulk/block deals")
    except Exception as e:
        logger.warning(f"Bulk deals fetch failed: {e}")

    return deals


def get_mmi_score() -> float:
    """
    Get Market Mood Index (MMI) score.

    Rebuilt to include 3 components (Flaw #4 fix):
    - VIX component (40% weight) — options-based fear gauge
    - Advance/Decline proxy (30% weight) — breadth of Nifty 50 components
    - % of index above 50DMA proxy (30% weight) — trend participation

    Scale: 0 (Extreme Fear) to 100 (Extreme Greed)
    """
    try:
        vix = get_india_vix()

        # ── Component 1: VIX (40% weight) ──
        if vix < 12:
            vix_score = 90
        elif vix < 15:
            vix_score = 75
        elif vix < 17:
            vix_score = 60
        elif vix < 20:
            vix_score = 45
        elif vix < 22:
            vix_score = 30
        elif vix < 25:
            vix_score = 20
        else:
            vix_score = 10

        # ── Component 2: Advance/Decline proxy (30% weight) ──
        # Use Nifty 50 components: how many gained vs lost today
        ad_score = 50  # default neutral
        try:
            nifty50_tickers = [
                "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "INFY.NS", "ICICIBANK.NS",
                "BHARTIARTL.NS", "SBIN.NS", "ITC.NS", "HINDUNILVR.NS", "LT.NS",
                "BAJFINANCE.NS", "KOTAKBANK.NS", "HCLTECH.NS", "TATAMOTORS.NS", "AXISBANK.NS",
                "MARUTI.NS", "SUNPHARMA.NS", "TITAN.NS", "NTPC.NS", "ADANIENT.NS",
            ]
            sample_data = yf.download(
                tickers=nifty50_tickers[:20],
                period="2d", interval="1d",
                group_by="ticker", threads=True, progress=False
            )
            advances = 0
            declines = 0
            for t in nifty50_tickers[:20]:
                try:
                    if isinstance(sample_data.columns, pd.MultiIndex):
                        lvl0 = sample_data.columns.get_level_values(0).unique()
                        key = t if t in lvl0 else t.replace('.NS', '')
                        if key not in lvl0: continue
                        close = sample_data[key]["Close"].dropna()
                    else:
                        close = sample_data["Close"].dropna()
                    if len(close) >= 2:
                        if float(close.iloc[-1]) > float(close.iloc[-2]):
                            advances += 1
                        else:
                            declines += 1
                except Exception:
                    pass
            total = advances + declines
            if total > 0:
                ad_ratio = advances / total
                ad_score = int(ad_ratio * 100)
            logger.info(f"A/D ratio: {advances} advances, {declines} declines -> score {ad_score}")
        except Exception as e:
            logger.warning(f"A/D ratio calculation failed: {e}")

        # ── Component 3: % above 50DMA proxy (30% weight) ──
        # Approximate: if Nifty is above its own 50DMA, score higher
        breadth_score = 50  # default neutral
        try:
            nifty = yf.Ticker("^NSEI")
            nifty_hist = nifty.history(period="3mo", interval="1d")
            if isinstance(nifty_hist.columns, pd.MultiIndex):
                nifty_hist.columns = nifty_hist.columns.get_level_values(0)
            if not nifty_hist.empty:
                nifty_close = nifty_hist["Close"]
                current_nifty = float(nifty_close.iloc[-1])
                dma_50_nifty = float(nifty_close.rolling(50).mean().iloc[-1])
                # Scale: 5% above 50DMA = 80, at 50DMA = 50, 5% below = 20
                pct_from_50dma = ((current_nifty - dma_50_nifty) / dma_50_nifty) * 100
                breadth_score = int(max(0, min(100, 50 + pct_from_50dma * 6)))
            logger.info(f"Breadth (Nifty vs 50DMA) score: {breadth_score}")
        except Exception as e:
            logger.warning(f"Breadth score calculation failed: {e}")

        # ── Weighted combination ──
        mmi = int(vix_score * 0.40 + ad_score * 0.30 + breadth_score * 0.30)
        mmi = max(0, min(100, mmi))

        logger.info(
            f"MMI Score: {mmi} (VIX={vix_score}×0.4 + A/D={ad_score}×0.3 + Breadth={breadth_score}×0.3)"
        )
        return float(mmi)

    except Exception as e:
        logger.warning(f"MMI calculation failed: {e}")
        return 50.0  # neutral default


def get_market_overview() -> dict:
    """
    Get complete market overview combining all NSE data.
    This is the main entry point for the Macro agent.
    """
    vix = get_india_vix()
    fii_dii = get_fii_dii_data()
    mmi = get_mmi_score()

    overview = {
        "india_vix": vix,
        "mmi_score": mmi,
        "fii_today": fii_dii["fii_today"],
        "dii_today": fii_dii["dii_today"],
        "fii_3day_net": fii_dii["fii_3day_net"],
        "dii_3day_net": fii_dii["dii_3day_net"],
        "timestamp": datetime.now().isoformat(),
    }

    # Cache overview
    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"market_overview_{today}.json"
    cache_file.write_text(json.dumps(overview, indent=2))

    return overview


# ── CLI entry point for testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("  NSE Scraper — Testing")
    print("=" * 60)

    overview = get_market_overview()
    print(f"\nIndia VIX: {overview['india_vix']}")
    print(f"MMI Score: {overview['mmi_score']}")
    print(f"FII Net (today): ₹{overview['fii_today']} Cr")
    print(f"DII Net (today): ₹{overview['dii_today']} Cr")
    print(f"FII 3-day rolling: ₹{overview['fii_3day_net']} Cr")

    deals = get_bulk_deals()
    print(f"\nBulk/Block deals today: {len(deals)}")
    for d in deals[:5]:
        print(f"  {d['symbol']}: {d['client']} — {d['quantity']} @ ₹{d['price']}")
