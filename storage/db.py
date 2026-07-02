"""
SQLite database for logging every council call and tracking results.

Tables:
- daily_calls: Every call made by the engine (date, ticker, action, prices, confidence)
- agent_logs: Per-agent token usage and response times
- results: Updated end-of-week with actual price outcomes

This builds your own ground-truth dataset over time to fine-tune the council's weights.
"""

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from config import DB_PATH

logger = logging.getLogger(__name__)


def _get_connection() -> sqlite3.Connection:
    """Get SQLite connection, creating tables if needed."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    _create_tables(conn)
    return conn


def _create_tables(conn: sqlite3.Connection) -> None:
    """Create database tables if they don't exist."""
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS daily_calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            ticker TEXT NOT NULL,
            action TEXT NOT NULL,
            entry_low REAL,
            entry_high REAL,
            stop_loss_pct REAL,
            target_1 REAL,
            target_2 REAL,
            confidence INTEGER,
            position_multiplier REAL DEFAULT 1.0,
            macro_score INTEGER,
            fundamental_score REAL,
            technical_signal TEXT,
            news_sentiment INTEGER,
            reasoning TEXT,
            full_output TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS agent_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            agent_name TEXT NOT NULL,
            ticker TEXT,
            provider TEXT,
            model TEXT,
            success INTEGER DEFAULT 1,
            response_time_ms REAL,
            error_message TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id INTEGER REFERENCES daily_calls(id),
            ticker TEXT NOT NULL,
            call_date TEXT NOT NULL,
            review_date TEXT,
            price_at_call REAL,
            price_at_review REAL,
            actual_pnl_pct REAL,
            hit_target_1 INTEGER DEFAULT 0,
            hit_target_2 INTEGER DEFAULT 0,
            hit_stop_loss INTEGER DEFAULT 0,
            outcome TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS fii_daily (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL UNIQUE,
            fii_net REAL NOT NULL DEFAULT 0.0,
            dii_net REAL NOT NULL DEFAULT 0.0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_calls_date ON daily_calls(date);
        CREATE INDEX IF NOT EXISTS idx_calls_ticker ON daily_calls(ticker);
        CREATE INDEX IF NOT EXISTS idx_results_call_id ON results(call_id);
        CREATE INDEX IF NOT EXISTS idx_fii_daily_date ON fii_daily(date);
    """)
    conn.commit()


def log_call(result: dict) -> int:
    """
    Log a council call to the database.
    Returns the call ID for future result tracking.
    """
    conn = _get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO daily_calls 
               (date, ticker, action, entry_low, entry_high, stop_loss_pct,
                target_1, target_2, confidence, position_multiplier,
                macro_score, fundamental_score, technical_signal, news_sentiment,
                reasoning, full_output)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime("%Y-%m-%d"),
                result.get("ticker", ""),
                result.get("action", ""),
                result.get("entry_range_low", 0),
                result.get("entry_range_high", 0),
                result.get("stop_loss_pct", 0),
                result.get("target_1", 0),
                result.get("target_2", 0),
                result.get("confidence", 0),
                result.get("position_multiplier", 1.0),
                result.get("macro_score", 0),
                result.get("fundamental_score", 0),
                result.get("technical_signal", ""),
                result.get("news_sentiment", 0),
                result.get("reasoning", ""),
                json.dumps(result),
            ),
        )
        conn.commit()
        call_id = cursor.lastrowid
        logger.info(f"Logged call #{call_id}: {result.get('ticker')} → {result.get('action')}")
        return call_id
    finally:
        conn.close()


def log_agent(
    agent_name: str,
    ticker: str = "",
    provider: str = "",
    model: str = "",
    success: bool = True,
    response_time_ms: float = 0,
    error_message: str = "",
) -> None:
    """Log an individual agent's API call."""
    conn = _get_connection()
    try:
        conn.execute(
            """INSERT INTO agent_logs
               (date, agent_name, ticker, provider, model, success, response_time_ms, error_message)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                datetime.now().strftime("%Y-%m-%d"),
                agent_name,
                ticker,
                provider,
                model,
                1 if success else 0,
                response_time_ms,
                error_message,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def get_today_calls() -> list[dict]:
    """Get all calls made today."""
    conn = _get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        rows = conn.execute(
            "SELECT * FROM daily_calls WHERE date = ? ORDER BY confidence DESC",
            (today,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_call_history(ticker: str, limit: int = 30) -> list[dict]:
    """Get recent call history for a ticker."""
    conn = _get_connection()
    try:
        rows = conn.execute(
            "SELECT * FROM daily_calls WHERE ticker = ? ORDER BY date DESC LIMIT ?",
            (ticker, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_performance_stats() -> dict:
    """Get overall performance statistics."""
    conn = _get_connection()
    try:
        total = conn.execute("SELECT COUNT(*) FROM daily_calls").fetchone()[0]
        buys = conn.execute("SELECT COUNT(*) FROM daily_calls WHERE action = 'BUY'").fetchone()[0]
        holds = conn.execute("SELECT COUNT(*) FROM daily_calls WHERE action = 'HOLD'").fetchone()[0]
        avoids = conn.execute("SELECT COUNT(*) FROM daily_calls WHERE action = 'AVOID'").fetchone()[0]
        avg_conf = conn.execute("SELECT AVG(confidence) FROM daily_calls WHERE action = 'BUY'").fetchone()[0]

        return {
            "total_calls": total,
            "buy_calls": buys,
            "hold_calls": holds,
            "avoid_calls": avoids,
            "avg_buy_confidence": round(avg_conf or 0, 1),
        }
    finally:
        conn.close()


def store_fii_daily(fii_net: float, dii_net: float) -> None:
    """
    Store today's FII/DII net flow.

    Uses INSERT OR REPLACE so we only keep one row per day.
    This is called from nse_scraper.py after fetching FII/DII data.
    """
    conn = _get_connection()
    try:
        today = datetime.now().strftime("%Y-%m-%d")
        conn.execute(
            """INSERT OR REPLACE INTO fii_daily (date, fii_net, dii_net)
               VALUES (?, ?, ?)""",
            (today, fii_net, dii_net),
        )
        conn.commit()
        logger.info(f"Stored FII daily: date={today}, fii_net={fii_net}, dii_net={dii_net}")
    finally:
        conn.close()


def get_rolling_fii_net(days: int = 3) -> tuple[float, float]:
    """
    Get real rolling sum of FII and DII net flows over the last N days.

    Uses actual stored daily values — NOT fabricated by multiplying today's flow.

    Returns:
        (fii_rolling_net, dii_rolling_net) in ₹ Cr
    """
    conn = _get_connection()
    try:
        row = conn.execute(
            """SELECT COALESCE(SUM(fii_net), 0) as fii_sum,
                      COALESCE(SUM(dii_net), 0) as dii_sum
               FROM fii_daily
               WHERE date >= date('now', ? || ' days')""",
            (f"-{days}",),
        ).fetchone()
        fii_sum = round(float(row["fii_sum"]), 2)
        dii_sum = round(float(row["dii_sum"]), 2)
        logger.info(f"Rolling {days}-day FII net: ₹{fii_sum} Cr, DII net: ₹{dii_sum} Cr")
        return (fii_sum, dii_sum)
    finally:
        conn.close()
