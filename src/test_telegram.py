import os
import sys
from pathlib import Path
from loguru import logger
from dotenv import load_dotenv

# Load local .env so it can find your Telegram Tokens locally!
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))
from notifications import send_telegram_alert

def run_test():
    logger.info("Testing Telegram Integration...")
    
    # Test 1: Direct Ping
    try:
        send_telegram_alert("🧪 <b>TEST ALERT</b>\n\nIf you are reading this, your Telegram API connection is working perfectly!")
        logger.info("Direct ping command sent to Telegram.")
    except Exception as e:
        logger.error(f"Failed to send direct ping: {e}")

    # Test 2 omitted locally because Windows Antivirus blocks pandas loading

if __name__ == "__main__":
    run_test()
