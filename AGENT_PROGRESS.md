# 🤖 AlphaV-7 — Agent Progress & Performance Tracker

> **Last Updated:** 2026-04-04 17:05 IST | **Platform:** Render Cloud | **Mode:** Paper Trading

---

## 📋 Project Snapshot

| Field | Value |
|---|---|
| **Project** | AlphaV-7 Institutional AI Trading Agent |
| **Repo** | `github.com/vhemanthkum/ai-stock-trader` |
| **Platform** | Render.com (Free Web Service) |
| **Market** | NSE India — 20-stock curated watchlist |
| **Mode** | Paper Trading (simulation) |
| **Capital** | ₹10,00,00,000 simulated |
| **AI Stack** | Groq `llama-3.3-70b` + Claude `claude-3-5-haiku-20241022` |
| **Commit** | `fa04979` — pushed 2026-04-04 |

---

## ✅ Complete Step-by-Step History

### Phase 1 — Bootstrap (Conversation: c85ca26a · 2026-04-02)
- [x] Scaffolded project: `src/`, `config/`, `data/`, `logs/`, `tests/`
- [x] Built `trading_agent.py` with `InstitutionalTradingAgent` class (single Groq brain)
- [x] Defined 5 tools: `get_company_fundamentals`, `get_technical_indicators`, `scrape_news_cluster`, `get_social_sentiment`, `execute_trade`
- [x] `run_autonomous.py` — 100-stock NSE watchlist, hourly scan loop
- [x] `notifications.py` — Telegram push on trade sign
- [x] `app.py` — Flask server for Render health check
- [x] `Procfile` — `gunicorn src.app:app --log-file -`
- [x] `requirements.txt` — groq, flask, gunicorn, yfinance, etc.
- [x] Deployed to Render as a Web Service

### Phase 2 — Debugging (Conversation: f75f02b4 · 2026-04-04)
- [x] Diagnosed Gunicorn import failures (Python path not set for `src/`)
- [x] Fixed with `sys.path.insert(0, str(Path(__file__).parent))` in `app.py`
- [x] Identified GROQ_API_KEY missing from Render env vars
- [x] ⚠️ Project was still not working on Render after fixes

### Phase 3 — Dual-Brain Architecture (Current · 2026-04-04)
- [x] **Created `src/dual_brain.py`** — `DualBrainOrchestrator` class
  - Stage 1: Groq `llama-3.3-70b` → data analyst (tool calls for 4 data sources)
  - Stage 2: Claude `claude-3-5-haiku-20241022` → strategist (independent thesis)
  - Stage 3: Claude CIO → consensus synthesizer (final BUY/SELL/HOLD)
  - Trade only executes when `conviction ≥ 7/10` AND `execute_trade=true`
- [x] **Fixed Claude model name** — was `"claude-haiku-3-5"` (INVALID), now `"claude-3-5-haiku-20241022"`
- [x] **Rewrote `src/notifications.py`**
  - `send_telegram_alert()` — HTML push messages
  - `verify_telegram_connection()` — validates bot token + chat_id on boot
  - `send_hourly_pnl_report()` — formatted hourly P&L to Telegram
- [x] **Rewrote `src/run_autonomous.py`**
  - Reduced watchlist: 100 → 20 stocks (Groq RPD limit: 1,000/day)
  - Fixed daily counter reset — now date-aware (not resetting every scan)
  - Added `hourly_pnl_report()` job (scheduled independently of scan)
  - Fixed ticker: `SBI` → `SBIN` (correct NSE symbol)
  - `load_dotenv(override=True)` at module top
- [x] **Rewrote `src/app.py`**
  - Added `load_dotenv(override=True)` before all imports
  - Telegram connection verify on boot
  - Hourly P&L job added to scheduler
  - New endpoints: `/status`, `/positions`, `/history`, `/pnl`
  - Thread named `DualBrainWorker` for debuggability
- [x] **Fixed `Procfile`**
  - Old: `gunicorn src.app:app --log-file -`
  - New: `gunicorn src.app:app --workers 1 --threads 2 --timeout 120 --log-file -`
  - `--workers 1` is CRITICAL — threading + multiple workers = race conditions on Render
- [x] **Fixed `main.py`** — was importing `trading_agent.main` (deleted), now `run_autonomous.main`
- [x] **Updated `requirements.txt`** — added `anthropic>=0.25.0`
- [x] **Updated `.env.example`** — added `ANTHROPIC_API_KEY`
- [x] **Created `AGENT_PROGRESS.md`** — this file
- [x] Committed all changes: `fa04979`
- [x] Pushed to GitHub → Render auto-redeploy triggered

---

## 🏗️ Current Architecture

```
Render Web Service (Gunicorn --workers 1)
├── Flask (HTTP)
│   ├── GET /           → Health check (UptimeRobot)
│   ├── GET /status     → Live portfolio state (JSON)
│   ├── GET /positions  → Open positions (JSON)
│   ├── GET /history    → Closed trades (JSON)
│   └── GET /pnl        → Trigger manual P&L report to Telegram
│
└── DualBrainWorker (daemon thread)
    ├── On Boot:   verify_telegram_connection() + send boot alert
    ├── Every 1h:  autonomous_scan() → 20 stocks × dual-brain pipeline
    └── Every 1h:  send_hourly_pnl_report() → Telegram

    Per-Stock Pipeline:
    ┌── Groq llama-3.3-70b ── DATA ANALYST ──────────────────┐
    │   Calls: fundamentals + technicals + news + sentiment   │
    │   Output: structured JSON analysis                      │
    └─────────────────────────────┬───────────────────────────┘
                                  ▼
    ┌── Claude claude-3-5-haiku ── STRATEGIST ────────────────┐
    │   Reads Groq data, builds independent thesis            │
    │   Challenges weak reasoning, applies risk rules         │
    │   Output: decision + conviction + entry/SL/target       │
    └─────────────────────────────┬───────────────────────────┘
                                  ▼
    ┌── Claude claude-3-5-haiku ── CIO CONSENSUS ─────────────┐
    │   Weighs both analyst + strategist                      │
    │   execute_trade=true only if conviction ≥ 7/10          │
    │   Output: final BUY/SELL/HOLD + trade params            │
    └─────────────────────────────┬───────────────────────────┘
                                  ▼
                    EXECUTE TRADE? → Telegram alert
```

---

## 📊 API Rate Limit Budget

| API | Model | Limit (Free) | Usage Per Scan | Safe? |
|---|---|---|---|---|
| Groq | llama-3.3-70b-versatile | 1,000 RPD | ~100 calls (20 stocks × 5) | ✅ Yes |
| Claude | claude-3-5-haiku-20241022 | Paid (Tier 1: 50 RPM) | ~40 calls (20 × 2) | ✅ Yes |
| yfinance | — | Unlimited | 20 × 2 | ✅ Yes |
| Telegram | Bot API | Unlimited | ~25/scan + 1/hour | ✅ Yes |

> **Sleep:** 30s between stocks → scan takes ~10 min total for 20 stocks

---

## 🔑 Required Environment Variables (Render Dashboard)

| Variable | Status | Where to Get |
|---|---|---|
| `GROQ_API_KEY` | ✅ Set | console.groq.com |
| `ANTHROPIC_API_KEY` | ⚠️ Needs setting | console.anthropic.com |
| `TELEGRAM_BOT_TOKEN` | ⚠️ Needs setting | t.me/BotFather |
| `TELEGRAM_CHAT_ID` | ⚠️ Needs setting | t.me/userinfobot |
| `TRADING_MODE` | ✅ Set (`paper`) | — |
| `INITIAL_CAPITAL` | ✅ Set | — |

---

## 🐛 Known Issues

| Issue | Status |
|---|---|
| Trade state lost on Render restart | 🟡 By design (in-memory) — use a DB for persistence |
| yfinance may rate-limit on cloud IPs | 🟡 Handled with error fallback in `call_function()` |
| StockTwits API returns 429 for Indian stocks | 🟡 Returns error dict, Groq handles gracefully |
| Render free tier sleeps after 15 min idle | ✅ Use UptimeRobot to ping `/` every 14 min |

---

## 📅 Next Steps

- [ ] **Set `ANTHROPIC_API_KEY`** in Render environment variables
- [ ] **Set `TELEGRAM_BOT_TOKEN` + `TELEGRAM_CHAT_ID`** in Render
- [ ] Monitor Render deploy logs for successful boot
- [ ] Watch for first Telegram message from the bot
- [ ] Optionally: add SQLite or Redis for trade state persistence across restarts

---
*Auto-updated by AlphaV-7 agent · Do not edit manually*
