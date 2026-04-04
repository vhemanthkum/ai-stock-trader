"""
app.py — Flask application for Render deployment
=================================================
• Gunicorn runs this file as the WSGI entry point
• Background daemon thread runs the dual-brain scan loop
• Exposes monitoring endpoints: /, /status, /positions, /history
"""

import os
import sys
import time
import threading
import schedule
from functools import wraps
from pathlib import Path
from flask import Flask, jsonify, render_template, request, Response
from loguru import logger

# ── Critical: add src/ to path BEFORE any local imports ─────────────────────
sys.path.insert(0, str(Path(__file__).parent))

# Load .env (works locally; Render injects env vars directly)
from dotenv import load_dotenv
load_dotenv(override=True)

# ── Local imports (after path fix) ───────────────────────────────────────────
from run_autonomous import autonomous_scan, hourly_pnl_report, TRADING_STATE
from notifications import verify_telegram_connection, send_telegram_alert

# ── Flask app ────────────────────────────────────────────────────────────────
app = Flask(__name__, template_folder="../templates", static_folder="../static")

# ── Authentication ───────────────────────────────────────────────────────────
def check_auth(username, password):
    expected_pass = os.getenv("DASHBOARD_PASSWORD", "alpha2026")
    return username == 'admin' and password == expected_pass

def authenticate():
    return Response(
        'Could not verify your access level for that URL.\n'
        'You have to login with proper credentials', 401,
        {'WWW-Authenticate': 'Basic realm="Login Required"'})

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    """Health check endpoint — Render & UptimeRobot ping this."""
    return (
        "🚀 AlphaV-7 Dual-Brain Trading Agent — LIVE\n"
        "Groq (Data Analyst) + Claude (Strategist) are scanning 20 NSE stocks.\n"
        "Endpoints: /status  /positions  /history"
    ), 200


@app.route("/status")
def status():
    """Live portfolio state as JSON."""
    total_pnl = sum(t.get("pnl", 0) for t in TRADING_STATE["closed_trades"])
    return jsonify({
        "status":          "running",
        "current_action":  TRADING_STATE.get("current_action", "Idle"),
        "capital":         TRADING_STATE["capital"],
        "daily_loss":      TRADING_STATE["daily_loss"],
        "realized_pnl":    round(total_pnl, 2),
        "trades_today":    TRADING_STATE["trades_today"],
        "open_positions":  len(TRADING_STATE["open_positions"]),
        "closed_trades":   len(TRADING_STATE["closed_trades"]),
        "last_screen_result": TRADING_STATE.get("last_screen_result")
    })


@app.route("/positions")
def positions():
    """All currently open positions."""
    return jsonify({"open_positions": TRADING_STATE["open_positions"]})


@app.route("/history")
def history():
    """All closed trade history."""
    return jsonify({"closed_trades": TRADING_STATE["closed_trades"]})


@app.route("/pnl")
def pnl_report():
    """Trigger a manual P&L report to Telegram."""
    hourly_pnl_report()
    return jsonify({"status": "P&L report sent to Telegram"}), 200


@app.route("/dashboard")
@requires_auth
def dashboard():
    """Renders the main frontend UI."""
    return render_template("index.html")


@app.route("/api/logs")
@requires_auth
def api_logs():
    """Returns the last 150 lines of the agent log."""
    log_file = Path(__file__).parent.parent / "logs" / "autonomous.log"
    logs = []
    if log_file.exists():
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                logs = lines[-150:]  # get last 150 lines
        except Exception:
            pass
    return jsonify({"logs": logs})


@app.route("/api/brain")
@requires_auth
def api_brain():
    """Returns the last scan JSON data."""
    log_file = Path(__file__).parent.parent / "logs" / "last_scan.json"
    data = []
    if log_file.exists():
        try:
            import json
            with open(log_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            pass
    return jsonify({"latest_scan": data})


# ── Background worker ─────────────────────────────────────────────────────────

def run_agent_loop():
    """
    Daemon thread: runs the dual-brain scan on boot + every hour.
    Also schedules hourly P&L Telegram reports.
    IMPORTANT: Must use --workers 1 in Gunicorn (see Procfile).
    """
    logger.info("🤖 Background agent loop starting...")

    # Verify Telegram credentials on boot
    tg_ok = verify_telegram_connection()
    if not tg_ok:
        logger.warning("⚠️ Telegram not configured — alerts will be skipped.")

    # Always announce boot state
    send_telegram_alert(
        "🏦 <b>AlphaV-7 Dual-Brain — ONLINE</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "• Groq llama-3.3-70b: <b>Data Analyst</b>\n"
        "• Claude 3.5 Haiku:   <b>Strategist + CIO</b>\n"
        "• Watchlist:          <b>20 NSE stocks</b>\n"
        "• Schedule:           <b>Every 1 hour</b>\n\n"
        "Starting first scan now... 🔍"
    )

    # Run first scan immediately on boot
    try:
        autonomous_scan()
    except Exception as e:
        logger.error(f"Initial scan error: {e}")
        send_telegram_alert(f"❌ <b>Initial Scan Failed</b>\n{e}")

    # Schedule: scan every hour, P&L report every hour (offset by 30 min)
    schedule.every(1).hours.do(autonomous_scan)
    schedule.every(1).hours.do(hourly_pnl_report)

    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            logger.error(f"Agent loop error: {e}")
            time.sleep(60)  # Prevent crash loops


# ── Start daemon on module load (Gunicorn-safe) ──────────────────────────────
_worker = threading.Thread(target=run_agent_loop, daemon=True, name="DualBrainWorker")
_worker.start()
logger.info("✅ DualBrainWorker thread started.")


# ── Local dev ─────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
