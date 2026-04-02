import requests
import feedparser
from loguru import logger
import yfinance as yf
from typing import Dict, List, Any

class NewsSentiment:
    @staticmethod
    def scrape_news_cluster(ticker: str) -> List[Dict[str, str]]:
        """Fetch latest news headlines for the stock via Google News RSS and yfinance"""
        try:
            news_items = []
            
            # Source 1: Yahoo Finance News
            yf_ticker = f"{ticker}.NS" if not ticker.endswith(('.NS', '.BO')) else ticker
            stock = yf.Ticker(yf_ticker)
            yf_news = stock.news
            
            if yf_news:
                for item in yf_news[:5]:
                    news_items.append({
                        "source": "Yahoo/Partners",
                        "title": item.get('title', ''),
                        "publisher": item.get('publisher', '')
                    })
                    
            # Source 2: Google News RSS
            # e.g., standard RSS query for Indian stock
            url = f"https://news.google.com/rss/search?q={ticker}+stock+india&hl=en-IN&gl=IN&ceid=IN:en"
            feed = feedparser.parse(url)
            for entry in feed.entries[:5]:
                news_items.append({
                    "source": "Google News Aggregator",
                    "title": entry.title,
                    "publisher": entry.source.title if 'source' in entry else 'Unknown'
                })
                
            logger.info(f"Fetched {len(news_items)} news articles for {ticker}")
            return news_items
        except Exception as e:
            logger.error(f"Error fetching news for {ticker}: {e}")
            return [{"error": str(e)}]

    @staticmethod
    def get_social_sentiment(ticker: str) -> Dict[str, Any]:
        """Fetch social sentiment from StockTwits"""
        try:
            clean_ticker = ticker.split('.')[0] 
            url = f"https://api.stocktwits.com/api/2/streams/symbol/{clean_ticker}.json"
            response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
            
            if response.status_code == 200:
                data = response.json()
                messages = data.get('messages', [])
                
                bullish = 0
                bearish = 0
                
                recent_messages = []
                for msg in messages[:15]:
                    body = msg.get('body', '')
                    recent_messages.append(body[:100] + "...")
                    
                    entities = msg.get('entities', {})
                    sentiment = entities.get('sentiment', {})
                    if sentiment and sentiment.get('basic'):
                        if sentiment['basic'] == 'Bullish':
                            bullish += 1
                        elif sentiment['basic'] == 'Bearish':
                            bearish += 1
                            
                total = bullish + bearish
                overall = "NEUTRAL"
                if total > 0:
                    if bullish / total > 0.6: overall = "BULLISH"
                    elif bearish / total > 0.6: overall = "BEARISH"
                
                logger.info(f"Fetched StockTwits sentiment for {ticker}")
                return {
                    "source": "StockTwits",
                    "bullish_signals": bullish,
                    "bearish_signals": bearish,
                    "overall_sentiment": overall,
                    "sample_chatter": recent_messages[:5]
                }
            else:
                return {"error": f"StockTwits API returned {response.status_code}"}
        except Exception as e:
            logger.error(f"Error fetching sentiment for {ticker}: {e}")
            return {"error": str(e)}
