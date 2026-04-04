import os
import requests
from loguru import logger


def send_telegram_alert(message: str) -> bool:
    """
    Send an HTML-formatted message to Telegram.
    Returns True on success, False on failure.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.warning("Telegram not configured — TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing.")
        return False

    url     = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id":    chat_id,
        "text":       message,
        "parse_mode": "HTML",
    }

    try:
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        logger.debug(f"Telegram message sent OK (chat_id={chat_id})")
        return True
    except requests.exceptions.HTTPError as e:
        logger.error(f"Telegram HTTP error: {e} | Response: {resp.text}")
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
    return False


def verify_telegram_connection() -> bool:
    """
    Validates Telegram credentials by calling getMe.
    Returns True if the bot token is valid and the chat is reachable.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not chat_id:
        logger.error("❌ Telegram credentials missing from environment variables.")
        return False

    # Step 1: Verify the bot token is valid
    try:
        me_resp = requests.get(
            f"https://api.telegram.org/bot{bot_token}/getMe", timeout=10
        )
        me_resp.raise_for_status()
        bot_name = me_resp.json().get("result", {}).get("username", "unknown")
        logger.info(f"✅ Telegram bot valid: @{bot_name}")
    except Exception as e:
        logger.error(f"❌ Telegram bot token invalid: {e}")
        return False

    # Step 2: Send a test message to confirm chat_id works
    test_ok = send_telegram_alert(
        "🤖 <b>AlphaV-7 Telegram Connection Verified ✅</b>\n\n"
        "Your trading agent is connected and will send:\n"
        "• 🚀 Trade signals (BUY/SELL)\n"
        "• 📊 Hourly P&amp;L reports\n"
        "• ⚠️ Risk alerts\n\n"
        "<i>Dual-Brain (Groq + Claude) is online.</i>"
    )

    if test_ok:
        logger.info(f"✅ Telegram test message delivered to chat_id={chat_id}")
    else:
        logger.error(f"❌ Telegram test message failed for chat_id={chat_id}")

    return test_ok


def send_hourly_pnl_report(trading_state: dict) -> bool:
    """
    Send a formatted hourly P&L report to Telegram.
    Called by the scheduler every hour independently of scan.
    """
    capital        = trading_state.get("capital", 100_000_000)
    daily_loss     = trading_state.get("daily_loss", 0)
    trades_today   = trading_state.get("trades_today", 0)
    open_positions = trading_state.get("open_positions", [])
    closed_trades  = trading_state.get("closed_trades", [])

    # Compute realized P&L from closed trades
    realized_pnl = sum(t.get("pnl", 0) for t in closed_trades)

    # Format open positions list
    if open_positions:
        pos_lines = "\n".join(
            f"  • <b>{p['ticker']}</b> {p['action']} {p['quantity']}@₹{p.get('entry_price', 0):,.0f}"
            for p in open_positions[:5]
        )
        if len(open_positions) > 5:
            pos_lines += f"\n  ...and {len(open_positions) - 5} more"
    else:
        pos_lines = "  None"

    # Trend emoji
    if realized_pnl > 0:
        trend = "🚀 PROFITABLE"
    elif realized_pnl < 0:
        trend = "🩸 IN LOSS"
    else:
        trend = "➖ BREAKEVEN"

    message = (
        f"📊 <b>HOURLY P&amp;L REPORT</b>\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"<b>Status:</b> {trend}\n"
        f"<b>Capital:</b> ₹{capital:,.0f}\n"
        f"<b>Realized P&amp;L:</b> ₹{realized_pnl:+,.2f}\n"
        f"<b>Daily Loss Used:</b> ₹{abs(daily_loss):,.0f} / ₹25,00,000\n"
        f"<b>Trades Today:</b> {trades_today}/50\n"
        f"<b>Open Positions:</b> {len(open_positions)}\n\n"
        f"<b>Open Positions:</b>\n{pos_lines}\n\n"
        f"🤖 <i>AlphaV-7 Dual-Brain | Groq + Claude</i>"
    )

    return send_telegram_alert(message)
