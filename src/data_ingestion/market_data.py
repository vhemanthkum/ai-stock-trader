import yfinance as yf
from loguru import logger
import pandas as pd
from typing import Dict, Any

class MarketData:
    @staticmethod
    def get_company_fundamentals(ticker: str) -> Dict[str, Any]:
        """Fetch fundamental data for the given ticker, mapped to Indian NSE if needed"""
        try:
            # Assuming Indian stocks need .NS suffix for yfinance
            if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
                yf_ticker = f"{ticker}.NS"
            else:
                yf_ticker = ticker
                
            stock = yf.Ticker(yf_ticker)
            info = stock.info
            
            fundamentals = {
                "ticker": ticker,
                "current_price": info.get("currentPrice"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "eps": info.get("trailingEps"),
                "dividend_yield": info.get("dividendYield"),
                "profit_margins": info.get("profitMargins"),
                "revenue_growth": info.get("revenueGrowth"),
                "debt_to_equity": info.get("debtToEquity"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow")
            }
            logger.info(f"Fetched fundamentals for {ticker}")
            return fundamentals
        except Exception as e:
            logger.error(f"Error fetching fundamentals for {ticker}: {e}")
            return {"error": str(e)}

    @staticmethod
    def get_technical_indicators(ticker: str) -> Dict[str, Any]:
        """Fetch historical data and compute simple technical indicators"""
        try:
            if not ticker.endswith('.NS') and not ticker.endswith('.BO'):
                yf_ticker = f"{ticker}.NS"
            else:
                yf_ticker = ticker
                
            stock = yf.Ticker(yf_ticker)
            hist = stock.history(period="1mo")
            
            if hist.empty:
                return {"error": "No historical data found"}
                
            # Compute a simple moving average (SMA) 20 and 5 days
            hist['SMA_5'] = hist['Close'].rolling(window=5).mean()
            hist['SMA_20'] = hist['Close'].rolling(window=20).mean()
            
            latest = hist.iloc[-1]
            
            indicators = {
                "ticker": ticker,
                "latest_close": latest['Close'],
                "sma_5": latest['SMA_5'],
                "sma_20": latest['SMA_20'],
                "volume": latest['Volume'],
                "trend": "BULLISH" if latest['SMA_5'] > latest['SMA_20'] else "BEARISH"
            }
            logger.info(f"Fetched technicals for {ticker}")
            return indicators
        except Exception as e:
            logger.error(f"Error fetching technicals for {ticker}: {e}")
            return {"error": str(e)}
