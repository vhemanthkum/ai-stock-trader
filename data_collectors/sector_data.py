"""
Sector data collector.

Fetches 8 Nifty sector indices and computes relative strength
against Nifty50 on 20-day and 60-day basis.

Sectors: Bank, IT, Pharma, Auto, FMCG, Metal, Realty, Energy
"""

import logging

import numpy as np
import pandas as pd
import yfinance as yf

from config import SECTOR_INDICES, NIFTY50_TICKER
from models.schemas import SectorRSData

logger = logging.getLogger(__name__)


def _compute_relative_strength(sector_close: pd.Series, nifty_close: pd.Series, period: int) -> float:
    """
    Compute relative strength of a sector vs Nifty50 over a given period.
    RS = (Sector % change over period) - (Nifty % change over period)
    Positive = outperforming, Negative = underperforming.
    """
    if len(sector_close) < period or len(nifty_close) < period:
        return 0.0

    sector_change = (sector_close.iloc[-1] / sector_close.iloc[-period] - 1) * 100
    nifty_change = (nifty_close.iloc[-1] / nifty_close.iloc[-period] - 1) * 100

    return round(float(sector_change - nifty_change), 2)


def get_sector_rankings() -> list[SectorRSData]:
    """
    Fetch all sector indices and rank by relative strength vs Nifty50.
    
    Returns sectors sorted by 20-day RS (strongest first).
    Blueprint rule: Only buy stocks in top 2–3 sectors.
    """
    logger.info("Fetching sector indices and computing relative strength...")

    # Fetch Nifty50 first
    try:
        nifty = yf.Ticker(NIFTY50_TICKER)
        nifty_hist = nifty.history(period="6mo", interval="1d")
        if isinstance(nifty_hist.columns, pd.MultiIndex):
            nifty_hist.columns = nifty_hist.columns.get_level_values(0)
        nifty_close = nifty_hist["Close"]
    except Exception as e:
        logger.error(f"Failed to fetch Nifty50 data: {e}")
        return []

    sectors = []

    for sector_name, ticker in SECTOR_INDICES.items():
        try:
            sector = yf.Ticker(ticker)
            hist = sector.history(period="6mo", interval="1d")

            if hist.empty:
                logger.warning(f"No data for {sector_name} ({ticker})")
                continue

            if isinstance(hist.columns, pd.MultiIndex):
                hist.columns = hist.columns.get_level_values(0)

            sector_close = hist["Close"]

            # Compute RS for 20-day and 60-day
            rs_20 = _compute_relative_strength(sector_close, nifty_close, 20)
            rs_60 = _compute_relative_strength(sector_close, nifty_close, 60)

            # Current price and 20-day change
            current_price = round(float(sector_close.iloc[-1]), 2)
            if len(sector_close) >= 20:
                change_20d = round(
                    (sector_close.iloc[-1] / sector_close.iloc[-20] - 1) * 100, 2
                )
            else:
                change_20d = 0.0

            sectors.append(SectorRSData(
                sector_name=sector_name,
                rs_20day=rs_20,
                rs_60day=rs_60,
                current_price=current_price,
                change_pct_20d=change_20d,
            ))

            logger.info(f"  {sector_name}: RS(20d)={rs_20:+.2f}% RS(60d)={rs_60:+.2f}%")

        except Exception as e:
            logger.warning(f"Error fetching {sector_name}: {e}")
            continue

    # Sort by 20-day RS (strongest first)
    sectors.sort(key=lambda s: s.rs_20day, reverse=True)

    logger.info(f"Ranked {len(sectors)} sectors by relative strength")
    return sectors


def get_top_sectors(n: int = 3) -> list[str]:
    """Get the top N sectors by relative strength."""
    rankings = get_sector_rankings()
    return [s.sector_name for s in rankings[:n]]


def get_laggard_sectors(n: int = 2) -> list[str]:
    """Get the bottom N sectors (laggards to avoid)."""
    rankings = get_sector_rankings()
    return [s.sector_name for s in rankings[-n:]]


# ── CLI entry point for testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    print("=" * 60)
    print("  Sector Rotation Analysis — Testing")
    print("=" * 60)

    rankings = get_sector_rankings()

    print("\n  Rank | Sector          | RS(20d)  | RS(60d)  | 20d Change")
    print("  " + "-" * 62)
    for i, s in enumerate(rankings, 1):
        print(
            f"  {i:>4} | {s.sector_name:<15} | {s.rs_20day:>+7.2f}% | "
            f"{s.rs_60day:>+7.2f}% | {s.change_pct_20d:>+7.2f}%"
        )

    print(f"\n  Top sectors: {', '.join(get_top_sectors(3))}")
    print(f"  Avoid:       {', '.join(get_laggard_sectors(2))}")
