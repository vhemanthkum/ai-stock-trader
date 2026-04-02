from datetime import datetime, time, timedelta
import pytz
from loguru import logger

def is_market_open(market_timezone="Asia/Kolkata"):
    tz = pytz.timezone(market_timezone)
    current_time = datetime.now(tz).time()
    market_open = time(9, 15)
    market_close = time(15, 30)
    today = datetime.now(tz).weekday()
    is_weekday = today < 5
    return is_weekday and market_open <= current_time <= market_close

def calculate_position_size(capital, stop_loss_distance, risk_percent=1.0, leverage=1.0):
    risk_amount = capital * (risk_percent / 100) * leverage
    if stop_loss_distance == 0:
        return 0
    position_size = risk_amount / stop_loss_distance
    return int(position_size)

def calculate_kelly_fraction(win_rate, avg_win, avg_loss, kelly_fraction=0.5):
    if avg_loss == 0:
        return 0.0
    b = avg_win / avg_loss
    p = win_rate
    q = 1 - win_rate
    kelly_percent = ((b * p) - q) / b
    return max(0, min(kelly_percent * kelly_fraction, 0.25))

def format_price(price, decimals=2):
    return f"₹{price:,.{decimals}f}"

def calculate_atr(highs, lows, closes, period=14):
    if len(closes) < period:
        return 0
    true_ranges = []
    for i in range(len(closes)):
        if i == 0:
            tr = highs[i] - lows[i]
        else:
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i-1]),
                abs(lows[i] - closes[i-1])
            )
        true_ranges.append(tr)
    return sum(true_ranges[-period:]) / period
