import os
import threading
from flask import Flask
from loguru import logger
import schedule
import time

# Import our autonomous scan loop
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

if __name__ == '__main__':
    # Start the continuous background trading agent loop in a separate thread
    worker = threading.Thread(target=run_agent_loop, daemon=True)
    worker.start()
    
    # Start the Flask web server to keep Render/Cloud platform happy
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
