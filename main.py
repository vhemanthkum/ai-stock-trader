#!/usr/bin/env python3
"""
main.py — Local CLI entry point
================================
For Render deployment, Gunicorn uses src/app.py directly via the Procfile.
This file is only for running locally or testing.
"""

import os
import sys
from pathlib import Path

# Add src/ to Python path
sys.path.insert(0, str(Path(__file__).parent / "src"))

from dotenv import load_dotenv
from loguru import logger

# Load environment variables from .env
load_dotenv(override=True)

# Setup logging
log_dir = Path("logs")
log_dir.mkdir(exist_ok=True)
logger.add(
    log_dir / "trader.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level:<8} | {message}",
    rotation="100 MB",
    retention="7 days"
)

if __name__ == "__main__":
    logger.info("🏦 Starting AlphaV-7 in CLI mode (local)...")
    from run_autonomous import main
    main()