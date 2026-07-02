"""
News collector for Indian stock market.

Parses RSS feeds from:
- Economic Times Markets
- Moneycontrol

Filters for stock-specific and sector-specific news.
Returns last 3 days of headlines per stock.
"""

import logging
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import feedparser

from config import NEWS_RSS_FEEDS, NEWS_LOOKBACK_DAYS
from models.schemas import NewsItem, StockNewsData

logger = logging.getLogger(__name__)


def _parse_published_date(entry: dict) -> datetime | None:
    """Parse published date from an RSS entry."""
    date_str = entry.get("published", entry.get("updated", ""))
    if not date_str:
        return None
    try:
        return parsedate_to_datetime(date_str)
    except Exception:
        try:
            # Try ISO format
            return datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        except Exception:
            return None


def _is_recent(published: datetime | None, lookback_days: int) -> bool:
    """Check if a news item is within the lookback window."""
    if not published:
        return True  # Include if we can't determine date
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    return published >= cutoff


def _matches_ticker(title: str, summary: str, ticker: str) -> bool:
    """Check if a news item mentions the given stock."""
    # Build search terms from ticker
    symbol = ticker.replace(".NS", "").replace(".BO", "")
    search_terms = [symbol.lower()]

    # Common name mappings
    name_map = {
        "HDFCBANK": ["hdfc bank", "hdfcbank"],
        "ICICIBANK": ["icici bank", "icicibank"],
        "INFY": ["infosys", "infy"],
        "RELIANCE": ["reliance", "ril", "reliance industries"],
        "TCS": ["tcs", "tata consultancy"],
        "BAJFINANCE": ["bajaj finance", "bajfinance"],
        "SBIN": ["sbi", "state bank"],
        "BHARTIARTL": ["bharti airtel", "airtel", "bhartiartl"],
        "ITC": ["itc"],
        "LT": ["l&t", "larsen", "larsen & toubro"],
    }

    if symbol in name_map:
        search_terms.extend(name_map[symbol])

    combined = (title + " " + summary).lower()
    return any(term in combined for term in search_terms)


def _fetch_all_feeds() -> list[dict]:
    """Fetch and combine all RSS feeds."""
    all_entries = []

    for feed_url in NEWS_RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            source_name = feed.feed.get("title", feed_url)

            for entry in feed.entries:
                published = _parse_published_date(entry)
                if not _is_recent(published, NEWS_LOOKBACK_DAYS):
                    continue

                all_entries.append({
                    "title": entry.get("title", ""),
                    "summary": entry.get("summary", entry.get("description", "")),
                    "source": source_name,
                    "published": published.isoformat() if published else "",
                    "link": entry.get("link", ""),
                })

            logger.info(f"Fetched {len(feed.entries)} entries from {source_name}")

        except Exception as e:
            logger.warning(f"Failed to fetch feed {feed_url}: {e}")

    return all_entries


def get_stock_news(ticker: str) -> StockNewsData:
    """
    Get recent news headlines for a specific stock.
    
    Searches across all configured RSS feeds for mentions
    of the stock by symbol or common name.
    """
    logger.info(f"Collecting news for {ticker}")
    all_entries = _fetch_all_feeds()

    matching_headlines = []
    for entry in all_entries:
        if _matches_ticker(entry["title"], entry["summary"], ticker):
            matching_headlines.append(
                NewsItem(
                    title=entry["title"],
                    source=entry["source"],
                    published=entry["published"],
                    summary=entry["summary"][:200],  # Truncate for token efficiency
                )
            )

    # Sort by published date (newest first), limit to top 10
    matching_headlines.sort(key=lambda x: x.published, reverse=True)
    matching_headlines = matching_headlines[:10]

    logger.info(f"Found {len(matching_headlines)} news items for {ticker}")

    return StockNewsData(
        ticker=ticker,
        headlines=matching_headlines,
    )


def get_market_news() -> list[NewsItem]:
    """Get general market news (not stock-specific)."""
    all_entries = _fetch_all_feeds()

    # Market-level keywords
    market_keywords = [
        "nifty", "sensex", "rbi", "fed", "inflation", "gdp",
        "fii", "dii", "rupee", "crude", "global markets",
        "market rally", "market crash", "bear market", "bull market",
    ]

    market_news = []
    for entry in all_entries:
        combined = (entry["title"] + " " + entry["summary"]).lower()
        if any(kw in combined for kw in market_keywords):
            market_news.append(
                NewsItem(
                    title=entry["title"],
                    source=entry["source"],
                    published=entry["published"],
                    summary=entry["summary"][:200],
                )
            )

    market_news.sort(key=lambda x: x.published, reverse=True)
    return market_news[:15]


# ── CLI entry point for testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("  News Collector — Testing")
    print("=" * 60)

    # Test stock-specific news
    for ticker in ["HDFCBANK.NS", "RELIANCE.NS"]:
        news = get_stock_news(ticker)
        print(f"\n{ticker}: {len(news.headlines)} headlines")
        for h in news.headlines[:3]:
            print(f"  [{h.source}] {h.title}")

    # Test market news
    print("\n--- Market News ---")
    market = get_market_news()
    for h in market[:5]:
        print(f"  [{h.source}] {h.title}")
