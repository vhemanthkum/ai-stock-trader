# 🤖 AI Stock Trader — Agent Progress & Performance Tracker

> **Updated:** 2026-04-04 | **Platform:** Render Cloud | **Mode:** Paper Trading

---

## 📋 Project Overview

| Field | Value |
|---|---|
| **Project** | AlphaV-7 Institutional AI Trading Agent |
| **Platform** | Render.com (Free Tier Web Service) |
| **Market** | NSE India (100 stocks watchlist) |
| **Trading Mode** | Paper (Simulation) |
| **Capital** | ₹10,00,00,000 (₹100 Crore simulated) |
| **AI Stack** | Groq (LLaMA 3.3-70B) + Claude (claude-haiku-3-5) |

---

## ✅ Step-by-Step History of What We've Built

### Phase 1 — Project Bootstrap (Conversation: c85ca26a)
- [x] Created project structure: `src/`, `config/`, `data/`, `logs/`, `tests/`
- [x] Implemented `trading_agent.py` — `InstitutionalTradingAgent` class
- [x] Used Groq's `llama-3.3-70b-versatile` as the AI brain
- [x] Defined 5 tools: `get_company_fundamentals`, `get_technical_indicators`, `scrape_news_cluster`, `get_social_sentiment`, `execute_trade`
- [x] System prompt crafted as "AlphaV-7" institutional trader persona
- [x] Created `run_autonomous.py` with 100-stock NSE watchlist (Nifty 100)
- [x] Autonomous scan runs every hour, 15-second delay between stocks
- [x] Created `notifications.py` — Telegram push alerts on trade execution
- [x] Created `app.py` — Flask web server wrapping the agent for Render
- [x] Created `Procfile` for Render: `gunicorn src.app:app --log-file -`
- [x] Created `requirements.txt` with all dependencies
- [x] Created `.env` and `.env.example` for secrets management

### Phase 2 — Cloud Deployment (Conversation: c85ca26a)
- [x] Deployed to Render.com as a Web Service
- [x] Setup environment variables (GROQ_API_KEY, TRADING_MODE, etc.)
- [x] Background thread runs `autonomous_scan()` continuously
- [x] Flask `/` endpoint acts as health check for UptimeRobot

### Phase 3 — Debugging (Conversation: f75f02b4)
- [x] Diagnosed `InstitutionalTradingAgent` import/runtime failures
- [x] Fixed sys.path so Gunicorn can find local modules from `src/`
- [x] Added `sys.path.insert(0, str(Path(__file__).parent))` to app.py
- [x] Identified Groq API key missing from Render environment variables
- [ ] **UNRESOLVED: Project still not working on Render — root cause TBD**

### Phase 4 — Dual-AI Architecture (Current — 2026-04-04)
- [ ] Add Claude API key to `.env` (user confirmed both Groq + Claude keys added)
- [ ] Design dual-model debate architecture (Groq ↔ Claude)
- [ ] Implement `dual_brain.py` — orchestrator that makes both AIs analyze independently
- [ ] Groq = fast quantitative analyst (tools, live data fetching)
- [ ] Claude = deep reasoning strategist (interprets Groq data, challenges decisions)
- [ ] Final consensus synthesizer produces single BUY/SELL/HOLD decision
- [ ] Update `run_autonomous.py` to use dual-brain pipeline
- [ ] Update `requirements.txt` with `anthropic` package
- [ ] Fix Render deployment & validate end-to-end

---

## 🐛 Known Issues & Current Status

| Issue | Status | Notes |
|---|---|---|
| Render deployment failing | 🔴 UNRESOLVED | Likely missing env vars or import errors |
| Only Groq key in .env | ✅ Fixed (user added Claude key) | Need ANTHROPIC_API_KEY in .env |
| Single AI makes all decisions alone | 🔴 Bad design | No cross-validation, high hallucination risk |
| No rate limit protection | 🟡 Partial | 15s sleep between stocks, but no retry/backoff |
| No persistence | 🔴 Missing | Trade state lost on restart (in-memory only) |

---

## 📊 API Limits Reference

### Groq (Free Tier)
| Model | RPM | RPD | TPM |
|---|---|---|---|
| `llama-3.3-70b-versatile` | 30 | 1,000 | ~6,000 |
| `llama-3.1-8b-instant` | 30 | 14,400 | ~20,000 |

> ⚠️ With 100 stocks × 4 tool calls each = ~400 Groq calls/scan. **Well above 1,000 RPD limit!**
> **Solution:** Reduce watchlist to top 20 stocks, or use batch processing.

### Claude (Anthropic — Paid Tiers)
| Tier | RPM | ITPM | OTPM |
|---|---|---|---|
| Tier 1 (entry) | 50 | 40,000 | 8,000 |
| Tier 2 | 1,000 | 80,000 | 16,000 |

> Claude is used for **reasoning/synthesis only** — 1 call per stock analysis (much cheaper).

---

## 🏗️ New Architecture Plan (Dual-Brain)

```
For each stock in watchlist:
    ┌─────────────────────────────────────────┐
    │  GROQ (llama-3.3-70b) — DATA ANALYST    │
    │  • Calls all 4 data tools               │
    │  • Produces raw analysis JSON           │
    └─────────────────────┬───────────────────┘
                          │ passes analysis to
    ┌─────────────────────▼───────────────────┐
    │  CLAUDE (haiku-3-5) — STRATEGIST        │
    │  • Reads Groq's analysis                │
    │  • Independently applies strategy       │
    │  • Challenges any weak reasoning        │
    └─────────────────────┬───────────────────┘
                          │ both opinions to
    ┌─────────────────────▼───────────────────┐
    │  CONSENSUS SYNTHESIZER (Claude)         │
    │  • Weighs both perspectives             │
    │  • Produces final BUY/SELL/HOLD signal  │
    │  • Only executes if both agree          │
    └─────────────────────────────────────────┘
```

---

## 📅 Next Steps (TODO)

- [ ] Implement `src/dual_brain.py`
- [ ] Update `.env` with `ANTHROPIC_API_KEY`
- [ ] Update `requirements.txt` with `anthropic>=0.25.0`
- [ ] Update `run_autonomous.py` to call dual brain
- [ ] Reduce watchlist to top 20 most liquid stocks (to stay within API limits)
- [ ] Add retry/backoff logic for 429 errors
- [ ] Test locally before redeploying to Render
- [ ] Commit and push to trigger Render redeploy

---

*This file is auto-updated by the AI agent. Do not manually edit.*
