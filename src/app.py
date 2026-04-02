import os
import sys
from pathlib import Path
import threading
from flask import Flask
from loguru import logger
import schedule
import time

# Ensure Python can find local modules inside the src folder when run by Gunicorn
sys.path.insert(0, str(Path(__file__).parent))
from run_autonomous import autonomous_scan

app = Flask(__name__)

@app.route('/')
def home():
    """This is the dummy endpoint that UptimeRobot will ping to keep the agent awake"""
    return "Institutional Trading Agent AlphaV-7 is LIVE and Scanning! 🚀"

def run_agent_loop():
    """Background thread to run the 1-hour schedule indefinitely"""
    logger.info("Initializing background scheduled scanner...")
    
    # Run first scan immediately upon boot
    autonomous_scan()
    
    # Schedule hourly scans
    schedule.every(1).hours.do(autonomous_scan)
    
    while True:
        try:
            schedule.run_pending()
            time.sleep(60)
        except Exception as e:
            logger.error(f"Error in background loop: {e}")
            time.sleep(60) # Prevent rapid crash loops

# Start the continuous background trading agent loop in a separate thread globally for Gunicorn
worker = threading.Thread(target=run_agent_loop, daemon=True)
worker.start()

if __name__ == '__main__':
    # Used only if running app.py locally without Gunicorn
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
