"""
Screener.in fundamental data parser.

Scrapes key fundamentals for NSE stocks:
- PE ratio, ROE, ROCE
- Debt/Equity ratio
- Revenue growth YoY, Profit growth YoY
- Market cap, Promoter holding

Includes daily caching to avoid hammering Screener.in.
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

from config import CACHE_DIR
from models.schemas import FundamentalData
from utils.exceptions import DataCollectionError

logger = logging.getLogger(__name__)

SCREENER_BASE = "https://www.screener.in/company"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
    "Accept-Language": "en-US,en;q=0.9",
}


def _ticker_to_screener_symbol(ticker: str) -> str:
    """Convert yfinance ticker (e.g. 'HDFCBANK.NS') to Screener symbol ('HDFCBANK')."""
    return ticker.replace(".NS", "").replace(".BO", "")


def _parse_numeric(text: str) -> float:
    """Parse numeric value from Screener.in text (handles ₹, %, commas, Cr)."""
    if not text:
        return 0.0
    cleaned = text.strip().replace(",", "").replace("₹", "").replace("%", "")
    cleaned = cleaned.replace("Cr.", "").replace("Cr", "").strip()
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def get_fundamentals(ticker: str) -> FundamentalData:
    """
    Scrape fundamental data for a stock from Screener.in.
    
    Returns structured FundamentalData with all key metrics.
    Uses daily cache to avoid rate-limiting.
    """
    symbol = _ticker_to_screener_symbol(ticker)
    
    # Check cache first
    cached = _load_cache(symbol)
    if cached:
        return cached

    logger.info(f"Fetching fundamentals for {symbol} from Screener.in")

    try:
        url = f"{SCREENER_BASE}/{symbol}/consolidated/"
        resp = requests.get(url, headers=HEADERS, timeout=15)

        if resp.status_code == 404:
            # Try standalone (non-consolidated)
            url = f"{SCREENER_BASE}/{symbol}/"
            resp = requests.get(url, headers=HEADERS, timeout=15)

        if resp.status_code != 200:
            logger.warning(f"Screener.in returned {resp.status_code} for {symbol}")
            raise DataCollectionError(ticker, "Screener.in", f"HTTP {resp.status_code}")

        soup = BeautifulSoup(resp.text, "lxml")

        # Parse the key ratios from the top section
        data = _extract_ratios(soup, ticker, symbol)

        # Cache for today
        _save_cache(symbol, data)
        logger.info(
            f"✓ {symbol}: ROE {data.roe}% | D/E {data.debt_to_equity} | "
            f"Rev growth {data.revenue_growth_yoy}%"
        )
        return data

    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol}: {e}")
        raise DataCollectionError(ticker, "Screener.in", str(e))


def _extract_ratios(soup: BeautifulSoup, ticker: str, symbol: str) -> FundamentalData:
    """Extract financial ratios from Screener.in HTML."""
    ratios = {}

    # Method 1: Parse the "top-ratios" section
    ratio_list = soup.select("#top-ratios li")
    for li in ratio_list:
        name_el = li.select_one(".name")
        value_el = li.select_one(".value, .number")
        if name_el and value_el:
            name = name_el.get_text(strip=True).lower()
            value = value_el.get_text(strip=True)
            ratios[name] = value

    # Method 2: Parse from company-ratios section
    ratio_table = soup.select(".company-ratios .flex-row, .ranges-table tr")
    for row in ratio_table:
        cells = row.find_all(["td", "span"])
        if len(cells) >= 2:
            name = cells[0].get_text(strip=True).lower()
            value = cells[-1].get_text(strip=True)
            ratios[name] = value

    # Extract company name
    name_el = soup.select_one("h1.margin-0, .company-name h1")
    company_name = name_el.get_text(strip=True) if name_el else symbol

    # Map scraped data to our schema
    def find_ratio(*keys):
        for k in keys:
            for rk, rv in ratios.items():
                if k in rk:
                    return _parse_numeric(rv)
        return 0.0

    return FundamentalData(
        ticker=ticker,
        company_name=company_name,
        market_cap=find_ratio("market cap"),
        pe_ratio=find_ratio("stock p/e", "p/e"),
        roe=find_ratio("roe", "return on equity"),
        roce=find_ratio("roce", "return on capital"),
        debt_to_equity=find_ratio("debt to equity", "debt/equity", "d/e"),
        revenue_growth_yoy=find_ratio("revenue growth", "sales growth", "compounded sales growth"),
        profit_growth_yoy=find_ratio("profit growth", "compounded profit growth"),
        promoter_holding=find_ratio("promoter holding"),
        promoter_change_qoq=find_ratio("change in promoter"),
    )


def _default_fundamentals(ticker: str) -> FundamentalData:
    """Fallback when scraping fails — now fails loudly to prevent zero-data contamination."""
    raise DataCollectionError(ticker, "Screener.in", "Forced default fallback triggered")


def _cache_key(symbol: str) -> Path:
    """Generate cache file path."""
    today = datetime.now().strftime("%Y-%m-%d")
    return CACHE_DIR / f"fundamentals_{symbol}_{today}.json"


def _load_cache(symbol: str) -> FundamentalData | None:
    """Load cached fundamental data if available."""
    cache_file = _cache_key(symbol)
    if cache_file.exists():
        try:
            data = json.loads(cache_file.read_text())
            logger.info(f"Using cached fundamentals for {symbol}")
            return FundamentalData(**data)
        except Exception:
            pass
    return None


def _save_cache(symbol: str, data: FundamentalData) -> None:
    """Save fundamental data to cache."""
    cache_file = _cache_key(symbol)
    cache_file.write_text(data.model_dump_json(indent=2))


def get_all_fundamentals(tickers: list[str]) -> dict[str, FundamentalData]:
    """Fetch fundamentals for all tickers in the list."""
    results = {}
    for ticker in tickers:
        results[ticker] = get_fundamentals(ticker)
    return results


# ── CLI entry point for testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("  Screener.in Parser — Testing")
    print("=" * 60)

    for ticker in ["HDFCBANK.NS", "INFY.NS"]:
        data = get_fundamentals(ticker)
        print(f"\n{data.company_name} ({data.ticker}):")
        print(f"  Market Cap: ₹{data.market_cap} Cr")
        print(f"  PE: {data.pe_ratio} | ROE: {data.roe}% | ROCE: {data.roce}%")
        print(f"  D/E: {data.debt_to_equity}")
        print(f"  Revenue Growth: {data.revenue_growth_yoy}%")
        print(f"  Promoter Holding: {data.promoter_holding}%")
