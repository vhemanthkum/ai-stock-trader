"""
yfinance data collector for NSE stocks.

Pulls OHLCV data and computes all technical indicators:
- 20DMA, 50DMA, 200DMA (moving averages)
- 14-day RSI (Relative Strength Index)
- 14-day ATR (Average True Range)
- 20-day volume average + volume ratio
- 3-month price performance
- 52-week high/low

Output: Compact JSON under 200 tokens per stock (as specified in the blueprint).
"""

import json
import logging
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import yfinance as yf

from config import (
    CACHE_DIR,
    OHLCV_PERIOD,
    OHLCV_INTERVAL,
    NIFTY50_TICKER,
    WATCHLIST,
)
from models.schemas import StockPriceData
from utils.exceptions import DataCollectionError

logger = logging.getLogger(__name__)


def _compute_rsi(series: pd.Series, period: int = 14) -> float:
    """Compute RSI (Relative Strength Index) for the last value."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)

    avg_gain = gain.ewm(alpha=1/period, min_periods=period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1/period, min_periods=period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    
    last_rsi = rsi.iloc[-1]
    return round(float(last_rsi), 2) if not np.isnan(last_rsi) else 50.0


def _compute_atr(df: pd.DataFrame, period: int = 14) -> float:
    """Compute ATR (Average True Range) for the last value."""
    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tr1 = high - low
    tr2 = abs(high - close.shift(1))
    tr3 = abs(low - close.shift(1))

    true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = true_range.rolling(window=period).mean()
    
    last_atr = atr.iloc[-1]
    return round(float(last_atr), 2) if not np.isnan(last_atr) else 0.0


def _flatten_column(series_or_df):
    """Handle yfinance multi-level columns when downloading single ticker."""
    if isinstance(series_or_df, pd.DataFrame):
        if series_or_df.shape[1] == 1:
            return series_or_df.iloc[:, 0]
    return series_or_df


def get_stock_data(ticker: str) -> StockPriceData:
    """
    Fetch OHLCV data for a single NSE stock and compute all technical indicators.
    
    Returns a StockPriceData object with all indicators pre-computed.
    The LLM agents receive this — never raw CSV.
    """
    logger.info(f"Fetching data for {ticker}")

    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period=OHLCV_PERIOD, interval=OHLCV_INTERVAL)

        if df.empty:
            logger.warning(f"No data returned for {ticker}")
            raise DataCollectionError(ticker, "yfinance", "Empty DataFrame returned")

        # Flatten multi-index columns if present
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"].dropna()
        volume = df["Volume"].dropna()

        if close.empty or volume.empty:
            logger.warning(f"All valid data is NaN for {ticker}")
            raise DataCollectionError(ticker, "yfinance", "All data returned as NaN")

        # Current values
        current_price = round(float(close.iloc[-1]), 2)
        current_volume = int(volume.iloc[-1])

        # Moving averages
        dma_20 = round(float(close.rolling(20).mean().iloc[-1]), 2)
        dma_50 = round(float(close.rolling(50).mean().iloc[-1]), 2)
        dma_200 = round(float(close.rolling(200).mean().iloc[-1]), 2) if len(close) >= 200 else round(float(close.mean()), 2)

        # RSI
        rsi_14 = _compute_rsi(close, 14)

        # ATR
        atr_14 = _compute_atr(df, 14)

        # Volume analysis
        volume_avg_20d = int(volume.rolling(20).mean().iloc[-1])
        volume_ratio = round(current_volume / volume_avg_20d, 2) if volume_avg_20d > 0 else 1.0

        # Position relative to MAs
        above_50dma = current_price > dma_50
        above_200dma = current_price > dma_200

        # 3-month performance
        if len(close) >= 63:  # ~3 months of trading days
            price_3m_ago = float(close.iloc[-63])
            price_change_3m = round(((current_price - price_3m_ago) / price_3m_ago) * 100, 2)
        else:
            price_change_3m = 0.0

        # 52-week high/low
        high_52w = round(float(df["High"].tail(252).max()), 2)
        low_52w = round(float(df["Low"].tail(252).min()), 2)

        data = StockPriceData(
            ticker=ticker,
            current_price=current_price,
            dma_20=dma_20,
            dma_50=dma_50,
            dma_200=dma_200,
            rsi_14=rsi_14,
            atr_14=atr_14,
            volume_current=current_volume,
            volume_avg_20d=volume_avg_20d,
            volume_ratio=volume_ratio,
            above_50dma=above_50dma,
            above_200dma=above_200dma,
            price_change_3m_pct=price_change_3m,
            high_52w=high_52w,
            low_52w=low_52w,
        )

        # Cache to disk
        _cache_data(ticker, data)
        logger.info(f"✓ {ticker}: ₹{current_price} | RSI {rsi_14} | Vol ratio {volume_ratio}×")
        return data

    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        raise DataCollectionError(ticker, "yfinance", str(e))


def get_nifty_data() -> dict:
    """
    Fetch Nifty50 index data for 200DMA comparison.
    Returns dict with close, 200dma, above_200dma.
    """
    try:
        nifty = yf.Ticker(NIFTY50_TICKER)
        df = nifty.history(period=OHLCV_PERIOD, interval=OHLCV_INTERVAL)

        if df.empty:
            return {"close": 0, "dma_200": 0, "above_200dma": True}

        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)

        close = df["Close"].dropna()
        if close.empty:
            return {"close": 0, "dma_200": 0, "above_200dma": True}
            
        current = float(close.iloc[-1])
        dma_200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.mean())

        return {
            "close": round(current, 2),
            "dma_200": round(dma_200, 2),
            "above_200dma": current > dma_200,
        }
    except Exception as e:
        logger.error(f"Error fetching Nifty data: {e}")
        return {"close": 0, "dma_200": 0, "above_200dma": True}


def get_all_stocks_data(watchlist: list[str] | None = None) -> dict[str, StockPriceData]:
    """Fetch data for all stocks in the watchlist."""
    tickers = watchlist or WATCHLIST
    results = {}
    for ticker in tickers:
        results[ticker] = get_stock_data(ticker)
    return results


def _empty_stock_data(ticker: str) -> StockPriceData:
    """Fallback when fetch fails — now fails loudly to prevent zero-data contamination."""
    raise DataCollectionError(ticker, "yfinance", "Forced empty data fallback triggered")


def _cache_data(ticker: str, data: StockPriceData) -> None:
    """Cache stock data to disk as JSON."""
    today = datetime.now().strftime("%Y-%m-%d")
    cache_file = CACHE_DIR / f"{ticker.replace('.', '_')}_{today}.json"
    cache_file.write_text(data.model_dump_json(indent=2))


# ── CLI entry point for testing ─────────────────────────────────────────
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    
    print("=" * 60)
    print("  yfinance Collector — Testing")
    print("=" * 60)

    # Test Nifty
    nifty = get_nifty_data()
    print(f"\nNifty50: ₹{nifty['close']} | 200DMA: ₹{nifty['dma_200']} | Above: {nifty['above_200dma']}")

    # Test first 2 stocks
    for ticker in WATCHLIST[:2]:
        data = get_stock_data(ticker)
        print(f"\n{data.ticker}:")
        print(f"  Price: ₹{data.current_price}")
        print(f"  20/50/200 DMA: ₹{data.dma_20} / ₹{data.dma_50} / ₹{data.dma_200}")
        print(f"  RSI: {data.rsi_14} | ATR: {data.atr_14}")
        print(f"  Volume ratio: {data.volume_ratio}×")
        print(f"  3M change: {data.price_change_3m_pct}%")
