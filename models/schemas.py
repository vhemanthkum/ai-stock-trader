"""
Pydantic schemas for all agent inputs and outputs.

Every agent's response is validated against these models —
no unstructured data passes through the system.
"""

from __future__ import annotations
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────────────

class MarketRegime(str, Enum):
    BULL = "Bull"
    BEAR = "Bear"
    NEUTRAL = "Neutral"


class TradeAction(str, Enum):
    BUY = "BUY"
    HOLD = "HOLD"
    AVOID = "AVOID"


# ── Data Input Schemas ──────────────────────────────────────────────────

class MarketData(BaseModel):
    """Market-level data fed to Macro and Sector agents."""
    india_vix: float = Field(..., description="Current India VIX value")
    mmi_score: float = Field(..., description="Market Mood Index 0–100")
    nifty_close: float = Field(..., description="Nifty50 current close")
    nifty_200dma: float = Field(..., description="Nifty50 200-day MA")
    nifty_above_200dma: bool = Field(..., description="Is Nifty above 200DMA?")
    fii_3day_net: float = Field(..., description="FII 3-day rolling net (₹ Cr)")
    dii_3day_net: float = Field(..., description="DII 3-day rolling net (₹ Cr)")


class SectorRSData(BaseModel):
    """Relative strength data for a single sector."""
    sector_name: str
    rs_20day: float = Field(..., description="20-day relative strength vs Nifty50")
    rs_60day: float = Field(..., description="60-day relative strength vs Nifty50")
    current_price: float
    change_pct_20d: float


class StockPriceData(BaseModel):
    """Pre-computed technical data for a stock from yfinance."""
    ticker: str
    current_price: float
    dma_20: float
    dma_50: float
    dma_200: float
    rsi_14: float = Field(..., ge=0, le=100)
    atr_14: float
    volume_current: int
    volume_avg_20d: int
    volume_ratio: float
    above_50dma: bool
    above_200dma: bool
    price_change_3m_pct: float
    high_52w: float
    low_52w: float


class FundamentalData(BaseModel):
    """Fundamental data scraped from Screener.in."""
    ticker: str
    company_name: str = ""
    market_cap: float = 0.0
    pe_ratio: float = 0.0
    roe: float = Field(0.0, description="Return on Equity %")
    roce: float = Field(0.0, description="Return on Capital Employed %")
    debt_to_equity: float = 0.0
    revenue_growth_yoy: float = Field(0.0, description="Revenue growth YoY %")
    profit_growth_yoy: float = Field(0.0, description="Profit growth YoY %")
    promoter_holding: float = 0.0
    promoter_change_qoq: float = 0.0


class NewsItem(BaseModel):
    """A single news headline."""
    title: str
    source: str
    published: str
    summary: str = ""


class StockNewsData(BaseModel):
    """News data for a stock."""
    ticker: str
    headlines: list[NewsItem] = Field(default_factory=list)


# ── Agent Output Schemas ────────────────────────────────────────────────

class MacroOutput(BaseModel):
    """Output from Agent 1 — Macro / Market regime."""
    regime: MarketRegime = Field(..., description="Bull / Bear / Neutral")
    sentiment_score: int = Field(..., ge=0, le=100, description="0–100 sentiment")
    vix_assessment: str = Field(..., description="Short VIX assessment")
    fii_assessment: str = Field(..., description="Short FII flow assessment")
    reasoning: str = Field(..., description="2–3 sentence reasoning")


class SectorOutput(BaseModel):
    """Output from Agent 2 — Sector rotation analysis."""
    sector_rankings: list[dict] = Field(
        ..., description="Sectors ranked by RS, each with name + score"
    )
    top_sectors: list[str] = Field(..., description="Top 2–3 sectors to focus on")
    laggard_sectors: list[str] = Field(..., description="Sectors to avoid")
    reasoning: str


class FundamentalOutput(BaseModel):
    """Output from Agent 3 — Fundamental quality filter."""
    ticker: str
    quality_score: float = Field(..., ge=0, le=10, description="0–10 fundamental quality")
    passes_roe_filter: bool
    passes_de_filter: bool
    passes_growth_filter: bool
    key_strengths: list[str] = Field(default_factory=list)
    key_risks: list[str] = Field(default_factory=list)
    reasoning: str


class TechnicalOutput(BaseModel):
    """Output from Agent 4 — Technical / chart analysis."""
    ticker: str
    signal: str = Field(..., description="BUY_ZONE / NEUTRAL / OVERBOUGHT / OVERSOLD")
    entry_zone_low: float
    entry_zone_high: float
    stop_loss_pct: float = Field(..., description="ATR-based stop-loss %")
    support_levels: list[float] = Field(default_factory=list)
    resistance_levels: list[float] = Field(default_factory=list)
    reasoning: str


class NewsOutput(BaseModel):
    """Output from Agent 5 — News catalyst & sentiment."""
    ticker: str
    sentiment_score: int = Field(..., ge=-5, le=5, description="-5 to +5 sentiment")
    positive_catalysts: list[str] = Field(default_factory=list)
    negative_catalysts: list[str] = Field(default_factory=list)
    regulatory_risks: list[str] = Field(default_factory=list)
    reasoning: str


class ChairmanOutput(BaseModel):
    """Output from Agent 6 — Chairman final synthesis."""
    ticker: str
    action: TradeAction = Field(..., description="BUY / HOLD / AVOID")
    confidence: int = Field(..., ge=0, le=100, description="0–100% confidence")
    reasoning: str
    
    # ── Deterministic Math Fields (injected by Python, not LLM) ──
    entry_range_low: float = 0.0
    entry_range_high: float = 0.0
    stop_loss_pct: float = 0.0
    target_1: float = 0.0
    target_2: float = 0.0
    risk_reward_ratio: float = 0.0
    setup_type: str = Field("None", description="Breakout / MeanReversion / Momentum / None")

    position_multiplier: float = Field(
        1.0, description="Sentiment-adjusted position multiplier"
    )

    reasoning: str

    # Individual agent scores (for the report)
    macro_score: int = 0
    sector_score: str = ""
    fundamental_score: float = 0.0
    technical_signal: str = ""
    news_sentiment: int = 0


class DailyReport(BaseModel):
    """Complete daily report output."""
    date: str
    market_data: MarketData
    macro_assessment: MacroOutput
    sector_assessment: SectorOutput
    stock_calls: list[ChairmanOutput] = Field(default_factory=list)
    run_metadata: dict = Field(default_factory=dict)
