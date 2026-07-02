"""
Central configuration for the Indian Stock AI Council Engine.

All model assignments, thresholds, watchlists, and API settings live here.
Swap models by changing a single string — no code changes needed.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# ── Load environment variables ──────────────────────────────────────────
load_dotenv()

# ── Project paths ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).parent
DATA_DIR = PROJECT_ROOT / "data"
CACHE_DIR = DATA_DIR / "cache"
REPORTS_DIR = DATA_DIR / "reports"
DB_PATH = DATA_DIR / "council.db"

# Create directories on import
CACHE_DIR.mkdir(parents=True, exist_ok=True)
REPORTS_DIR.mkdir(parents=True, exist_ok=True)

# ── API Keys ────────────────────────────────────────────────────────────
GOOGLE_AI_API_KEY    = os.getenv("GOOGLE_AI_API_KEY", "")
OPENROUTER_API_KEY   = os.getenv("OPENROUTER_API_KEY", "")
# Local Ollama configuration
OLLAMA_BASE_URL = "http://localhost:11434/v1"
OLLAMA_TIMEOUT = 120.0  # Seconds to wait for local Llama inference
NVIDIA_API_KEY       = os.getenv("NVIDIA_API_KEY", "")
GROQ_API_KEY         = os.getenv("GROQ_API_KEY", "")
ANTHROPIC_API_KEY    = os.getenv("ANTHROPIC_API_KEY", "")

# ── Watchlist ───────────────────────────────────────────────────────────
# Default watchlist — append .NS for NSE tickers
WATCHLIST = [
    "HDFCBANK.NS",
    "ICICIBANK.NS",
    "INFY.NS",
    "RELIANCE.NS",
    "TCS.NS",
    "BAJFINANCE.NS",
]

# ── Nifty Sector Indices ────────────────────────────────────────────────
# Yahoo Finance tickers for NSE sector indices
SECTOR_INDICES = {
    "Nifty Bank":    "^NSEBANK",
    "Nifty IT":      "^CNXIT",
    "Nifty Pharma":  "^CNXPHARMA",
    "Nifty Auto":    "^CNXAUTO",
    "Nifty FMCG":    "^CNXFMCG",
    "Nifty Metal":   "^CNXMETAL",
    "Nifty Realty":  "^CNXREALTY",
    "Nifty Energy":  "^CNXENERGY",
}
NIFTY50_TICKER = "^NSEI"

# ── Model Assignments — 4-Provider Strategy ────────────────────────────
#
# Provider selection rationale:
#   google     → A1, A2, A6 — best structured output + large context synthesis
#   nvidia     → A3 — DeepSeek R1 on GPU infrastructure, fastest deep reasoning
#   groq       → A4, A5 — sub-200ms LPU inference, critical for real-time analysis
#   openrouter → fallback/overflow when primary providers hit rate limits
#   anthropic  → A6 (Chairman) optional best reasoning/synthesis model
#
# Agent → (primary_provider, model_id, fallback_provider, fallback_model)
# Hybrid Architecture: 
# Technical/Sector/Macro run locally on Llama 3.1 8B (via Ollama).
# News runs fast on Groq. Fundamental/Chairman use Gemini Flash.
AGENT_MODELS = {
    "fundamental": ("google", "gemini-2.5-flash", "openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
    "chairman":    ("google", "gemini-2.5-flash", "openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
    "news":        ("groq", "llama-3.1-8b-instant", "openrouter", "meta-llama/llama-3.1-8b-instruct:free"),
    "macro":       ("ollama", "llama3.1", "groq", "llama-3.1-8b-instant"),
    "sector":      ("ollama", "llama3.1", "groq", "llama-3.1-8b-instant"),
    "technical":   ("ollama", "llama3.1", "groq", "llama-3.1-8b-instant"),
}

# ── LLM Settings ────────────────────────────────────────────────────────
LLM_TEMPERATURE = 0.3          # Low temp for analytical tasks
LLM_MAX_TOKENS = 4096          # Max output tokens per agent (increased for reasoning models)
CHAIRMAN_MAX_TOKENS = 4096     # Chairman gets more room for synthesis

# ── Provider API Base URLs ───────────────────────────────────────────────
NVIDIA_BASE_URL     = "https://integrate.api.nvidia.com/v1"
GROQ_BASE_URL       = "https://api.groq.com/openai/v1"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
ANTHROPIC_BASE_URL  = "https://api.anthropic.com/v1/messages"

# ── Rate Limits ─────────────────────────────────────────────────────────
GOOGLE_RPM       = 15     # 15 req/min (free Flash tier)
GOOGLE_RPD       = 1500   # 1,500 req/day (Flash)
GOOGLE_PRO_RPD   = 50     # 50 req/day (Pro)
OPENROUTER_RPM   = 20     # 20 req/min
OPENROUTER_RPD   = 200    # 200 req/day (free tier)
NVIDIA_RPM       = 60     # 60 req/min (generous)
NVIDIA_RPD       = 1000   # ~1000 req/day with free credits
GROQ_RPM         = 30     # 30 req/min
GROQ_RPD         = 1000   # 1000+ req/day (very generous free tier)
ANTHROPIC_RPM    = 5      # very low default rate limit placeholder

# Delay between API calls to stay within rate limits
API_DELAY_GOOGLE      = 4.0   # seconds
API_DELAY_OPENROUTER  = 3.0   # seconds
API_DELAY_NVIDIA      = 1.5   # seconds (faster limits)
API_DELAY_GROQ        = 1.0   # seconds (LPU is fast, using 8b is even safer)
API_DELAY_ANTHROPIC   = 5.0   # seconds

# ── Retry Settings ──────────────────────────────────────────────────────
MAX_RETRIES = 3
RETRY_BASE_DELAY = 2.0         # seconds, doubles each retry

# ── Trading Thresholds (from the blueprint) ─────────────────────────────
# Macro regime thresholds
VIX_OK_THRESHOLD = 17          # Below this = OK to trade
VIX_REDUCE_THRESHOLD = 22     # Above this = reduce risk (0.5× position)
FII_BULLISH_THRESHOLD = 2000   # 3-day net ≥ ₹2000 Cr = bullish
FII_BEARISH_THRESHOLD = -2000  # 3-day net ≤ −₹2000 Cr = defensive

# Fundamental filters
MIN_ROE = 15.0                 # ROE > 15%
MAX_DE_RATIO = 0.5             # Debt/Equity < 0.5
MIN_REVENUE_GROWTH = 15.0      # Revenue growth > 15% YoY

# Technical filters
RSI_LOWER = 45                 # RSI between 45–70 (not overbought)
RSI_UPPER = 70
VOLUME_RATIO_MIN = 1.5         # Volume > 1.5× 20-day average

# Position sizing
RISK_PER_TRADE = 0.005         # 0.5% of portfolio per trade
DEFAULT_STOP_LOSS_PCT = 7.0    # 7% hard stop-loss
ATR_STOP_MULTIPLIER = 2.0     # 2× 14-day ATR

# ── Sentiment thresholds (MMI) ──────────────────────────────────────────
MMI_EXTREME_FEAR = 30
MMI_FEAR = 50
MMI_NEUTRAL = 70
MMI_GREED = 85

# ── News sources ────────────────────────────────────────────────────────
NEWS_RSS_FEEDS = [
    "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms",
    "https://www.moneycontrol.com/rss/marketreports.xml",
    "https://www.moneycontrol.com/rss/results.xml",
]

# ── Data collection settings ────────────────────────────────────────────
OHLCV_PERIOD = "1y"           # 1 year of historical data
OHLCV_INTERVAL = "1d"         # Daily candles
NEWS_LOOKBACK_DAYS = 3         # Last 3 days of news

# ── Chairman synthesis weights ──────────────────────────────────────────
CHAIRMAN_WEIGHTS = {
    "fundamental": 0.25,
    "technical":   0.25,
    "macro":       0.20,
    "sector":      0.15,
    "news":        0.15,
}
