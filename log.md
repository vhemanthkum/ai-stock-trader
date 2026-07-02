# Indian Stock AI Council Engine — Execution Log

## Ultimate Execution Plan — Status Tracking

This log tracks the completion of all tasks identified in the ultimate execution plan deep-dive.

### 1. Soft Math & Hallucination
- [x] Create `utils/math_engine.py` for deterministic calculations
- [x] Strip mathematical generation from `ChairmanAgent` prompt
- [x] Update `ChairmanOutput` schema to default math fields to 0
- [x] Inject Python-computed targets, SL, and entry ranges into the final result in `main.py`
- [x] Implement minimum Risk-to-Reward (1.5) auto-downgrade logic

### 2. Silent Degradation & Error Handling
- [x] Create custom `DataCollectionError` and `AgentFailureError` exceptions
- [x] Update `screener_parser.py` to raise `DataCollectionError` instead of returning empty data
- [x] Update `yfinance_collector.py` to raise `DataCollectionError` instead of returning empty data
- [x] Update `main.py` to catch `DataCollectionError` and drop stocks cleanly
- [x] Update `BaseAgent._fallback_output` to raise `AgentFailureError`
- [x] Update `main.py` to catch `AgentFailureError` and drop the stock instead of returning dummy HOLD

### 3. Garbage Screening (Micro-Caps & Illiquid)
- [x] Add `mc_cache` (Market Cap caching) to `AdvancedStockScreener` to speed up yfinance lookups
- [x] Implement Stage 1A Gate: Market Cap > ₹500 Cr
- [x] Implement Stage 1A Gate: 20-Day Avg Volume > 200,000 shares
- [x] Implement Stage 1A Gate: Price > 200-DMA (Uptrend filter)
- [x] Fix the `pd.MultiIndex` extraction bug in `_score_batch` when downloading single vs multiple tickers

### 4. Data Fabrication
- [x] Remove the fake `fii_net * 3` logic
- [x] Add `fii_daily` table to SQLite (`storage/db.py`)
- [x] Create `store_fii_daily` and `get_rolling_fii_net` in `storage/db.py`
- [x] Update `nse_scraper.py` to read real rolling sums from SQLite
- [x] Rebuild `get_mmi_score()` to use VIX (40%), Advance/Decline proxy (30%), and % above 50DMA (30%)

### 5. Rate Limit Suicide
- [x] Implement `AsyncTokenBucketLimiter` in `utils/rate_limiter.py` with per-provider RPM/RPD limits
- [x] Replace `asyncio.sleep(4.0)` in `BaseAgent` with the new rate limiter
- [x] Add `ollama` as a supported provider with `OLLAMA_BASE_URL` in `config.py`
- [x] Configure hybrid routing in `AGENT_MODELS`: Local Llama for Technical/Sector/Macro, Gemini for Fundamental/Chairman, Groq for News
- [x] Switch `OpenAI` client to `AsyncOpenAI` in `BaseAgent`
- [x] Add `OLLAMA_TIMEOUT = 120.0` for local Llama inference

### 6. Context-Blind Momentum Gap
- [x] Create `data_collectors/sector_map.py` to map Nifty 500 tickers to NSE sectors
- [x] Apply Sector RS Multiplier in `stock_screener.py` (1.2× for top 3 sectors, 0.7× for bottom 3 sectors)
- [x] Enforce "max 1 BUY per sector" in `main.py` before finalizing results

---

## Status
**Completed:** 2026-07-02
All 6 major architectural flaws identified in the institutional code review have been successfully resolved.
The engine is now robust, fails loudly, screens intelligently, uses real data, respects API limits, and prevents sector concentration.
