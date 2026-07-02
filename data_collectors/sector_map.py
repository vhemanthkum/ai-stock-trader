"""
Sector mapping for Nifty 500 stocks.

Maps each ticker to its NSE sector for:
1. Sector RS Multiplier in the screener (Flaw #6)
2. "Max 1 BUY per sector" enforcement in main.py (Flaw #1)

This is a static dictionary for the ~200 most liquid tickers.
Unknown tickers return "Other" — they are not penalized or boosted.
"""

# NSE Sector Classification
# Source: NSE India sector indices constituent lists
SECTOR_MAP = {
    # ── Banking & Financial Services ──
    "HDFCBANK": "Bank",
    "ICICIBANK": "Bank",
    "SBIN": "Bank",
    "KOTAKBANK": "Bank",
    "AXISBANK": "Bank",
    "INDUSINDBK": "Bank",
    "BANKBARODA": "Bank",
    "PNB": "Bank",
    "FEDERALBNK": "Bank",
    "IDFCFIRSTB": "Bank",
    "CANBK": "Bank",
    "UNIONBANK": "Bank",
    "INDIANB": "Bank",
    "BANDHANBNK": "Bank",
    "AUBANK": "Bank",
    "RBLBANK": "Bank",
    "BAJFINANCE": "Financial Services",
    "BAJAJFINSV": "Financial Services",
    "HDFCLIFE": "Financial Services",
    "SBILIFE": "Financial Services",
    "ICICIPRULI": "Financial Services",
    "MUTHOOTFIN": "Financial Services",
    "CHOLAFIN": "Financial Services",
    "SHRIRAMFIN": "Financial Services",
    "M&MFIN": "Financial Services",
    "MANAPPURAM": "Financial Services",
    "PEL": "Financial Services",
    "LICHSGFIN": "Financial Services",
    "RECLTD": "Financial Services",
    "PFC": "Financial Services",
    "IIFL": "Financial Services",
    "ANGELONE": "Financial Services",

    # ── IT & Technology ──
    "TCS": "IT",
    "INFY": "IT",
    "HCLTECH": "IT",
    "WIPRO": "IT",
    "TECHM": "IT",
    "LTIM": "IT",
    "MPHASIS": "IT",
    "COFORGE": "IT",
    "PERSISTENT": "IT",
    "LTTS": "IT",
    "CYIENT": "IT",
    "ZENSARTECH": "IT",
    "TATAELXSI": "IT",
    "SONATA": "IT",
    "BIRLASOFT": "IT",
    "HAPPSTMNDS": "IT",

    # ── Pharma & Healthcare ──
    "SUNPHARMA": "Pharma",
    "DRREDDY": "Pharma",
    "CIPLA": "Pharma",
    "DIVISLAB": "Pharma",
    "AUROPHARMA": "Pharma",
    "LUPIN": "Pharma",
    "TORNTPHARM": "Pharma",
    "ALKEM": "Pharma",
    "IPCALAB": "Pharma",
    "BIOCON": "Pharma",
    "GLENMARK": "Pharma",
    "LAURUSLABS": "Pharma",
    "NATCOPHARMA": "Pharma",
    "APOLLOHOSP": "Pharma",
    "MAXHEALTH": "Pharma",
    "FORTIS": "Pharma",
    "ZYDUSLIFE": "Pharma",
    "ABBOTINDIA": "Pharma",
    "SYNGENE": "Pharma",

    # ── Auto & Auto Components ──
    "TATAMOTORS": "Auto",
    "MARUTI": "Auto",
    "M&M": "Auto",
    "BAJAJ-AUTO": "Auto",
    "HEROMOTOCO": "Auto",
    "EICHERMOT": "Auto",
    "TVSMOTOR": "Auto",
    "ASHOKLEY": "Auto",
    "BHARATFORG": "Auto",
    "MOTHERSON": "Auto",
    "BOSCHLTD": "Auto",
    "MRF": "Auto",
    "BALKRISIND": "Auto",
    "EXIDEIND": "Auto",
    "AMARAJABAT": "Auto",
    "TIINDIA": "Auto",
    "APOLLOTYRE": "Auto",
    "SONACOMS": "Auto",
    "SCHAEFFLER": "Auto",

    # ── FMCG ──
    "HINDUNILVR": "FMCG",
    "ITC": "FMCG",
    "NESTLEIND": "FMCG",
    "BRITANNIA": "FMCG",
    "GODREJCP": "FMCG",
    "DABUR": "FMCG",
    "MARICO": "FMCG",
    "COLPAL": "FMCG",
    "TATACONSUM": "FMCG",
    "UBL": "FMCG",
    "VBL": "FMCG",
    "EMAMILTD": "FMCG",
    "PGHH": "FMCG",
    "RADICO": "FMCG",

    # ── Metals & Mining ──
    "TATASTEEL": "Metal",
    "JSWSTEEL": "Metal",
    "HINDALCO": "Metal",
    "COALINDIA": "Metal",
    "VEDL": "Metal",
    "NMDC": "Metal",
    "SAIL": "Metal",
    "NATIONALUM": "Metal",
    "HINDCOPPER": "Metal",
    "APLAPOLLO": "Metal",
    "JINDALSTEL": "Metal",
    "RATNAMANI": "Metal",

    # ── Realty & Construction ──
    "DLF": "Realty",
    "GODREJPROP": "Realty",
    "OBEROIRLTY": "Realty",
    "PHOENIXLTD": "Realty",
    "PRESTIGE": "Realty",
    "BRIGADE": "Realty",
    "SOBHA": "Realty",
    "LODHA": "Realty",
    "SUNTECK": "Realty",

    # ── Energy (Oil, Gas, Power) ──
    "RELIANCE": "Energy",
    "ONGC": "Energy",
    "NTPC": "Energy",
    "POWERGRID": "Energy",
    "ADANIGREEN": "Energy",
    "ADANIENT": "Energy",
    "BPCL": "Energy",
    "IOC": "Energy",
    "GAIL": "Energy",
    "TATAPOWER": "Energy",
    "NHPC": "Energy",
    "SJVN": "Energy",
    "TORNTPOWER": "Energy",
    "PETRONET": "Energy",
    "HINDPETRO": "Energy",
    "ADANIPOWER": "Energy",
    "JSWENERGY": "Energy",
    "IREDA": "Energy",

    # ── Cement ──
    "ULTRACEMCO": "Cement",
    "SHREECEM": "Cement",
    "AMBUJACEM": "Cement",
    "ACC": "Cement",
    "DALBHARAT": "Cement",
    "RAMCOCEM": "Cement",
    "JKCEMENT": "Cement",
    "BIRLACEM": "Cement",

    # ── Capital Goods & Engineering ──
    "LT": "Capital Goods",
    "SIEMENS": "Capital Goods",
    "ABB": "Capital Goods",
    "HAVELLS": "Capital Goods",
    "VOLTAS": "Capital Goods",
    "CUMMINSIND": "Capital Goods",
    "BHEL": "Capital Goods",
    "BEL": "Capital Goods",
    "HAL": "Capital Goods",
    "COCHINSHIP": "Capital Goods",
    "MAZAGONDOCK": "Capital Goods",
    "GRSE": "Capital Goods",
    "GARDENDR": "Capital Goods",

    # ── Telecom ──
    "BHARTIARTL": "Telecom",
    "IDEA": "Telecom",
    "TTML": "Telecom",
    "ROUTE": "Telecom",

    # ── Consumer Durables ──
    "TITAN": "Consumer Durables",
    "ASIANPAINT": "Consumer Durables",
    "BERGEPAINT": "Consumer Durables",
    "PIDILITIND": "Consumer Durables",
    "WHIRLPOOL": "Consumer Durables",
    "CROMPTON": "Consumer Durables",
    "KALYANKJIL": "Consumer Durables",
    "BATAINDIA": "Consumer Durables",
    "PAGEIND": "Consumer Durables",
    "RELAXO": "Consumer Durables",
    "RAJESHEXPO": "Consumer Durables",
    "DIXON": "Consumer Durables",
    "BLUESTARLT": "Consumer Durables",

    # ── Infrastructure ──
    "IRCTC": "Infrastructure",
    "IRFC": "Infrastructure",
    "INDIGO": "Infrastructure",
    "CONCOR": "Infrastructure",
    "ADANIPORTS": "Infrastructure",
    "GMRAIRPORT": "Infrastructure",

    # ── Media & Entertainment ──
    "ZEEL": "Media",
    "PVRINOX": "Media",
    "SUNTV": "Media",
    "NAUKRI": "Media",
}

# Sector name normalization to match SECTOR_INDICES in config.py
# Maps our detailed sectors to the 8 Nifty sector indices
SECTOR_TO_INDEX = {
    "Bank": "Nifty Bank",
    "Financial Services": "Nifty Bank",
    "IT": "Nifty IT",
    "Pharma": "Nifty Pharma",
    "Auto": "Nifty Auto",
    "FMCG": "Nifty FMCG",
    "Metal": "Nifty Metal",
    "Realty": "Nifty Realty",
    "Energy": "Nifty Energy",
    "Cement": "Nifty Energy",       # Cement tracks with Energy/Infrastructure
    "Capital Goods": "Nifty Energy", # Capital Goods tracks with Energy
    "Telecom": "Nifty IT",          # Telecom tracks with IT broadly
    "Consumer Durables": "Nifty FMCG",  # Consumer tracks with FMCG
    "Infrastructure": "Nifty Energy",
    "Media": "Nifty IT",
}


def get_stock_sector(ticker: str) -> str:
    """
    Get the sector for a given ticker.

    Args:
        ticker: NSE ticker with or without .NS suffix (e.g., "HDFCBANK" or "HDFCBANK.NS")

    Returns:
        Sector name (e.g., "Bank", "IT", "Pharma") or "Other" if unknown.
    """
    symbol = ticker.replace(".NS", "").replace(".BO", "").upper()
    return SECTOR_MAP.get(symbol, "Other")


def get_nifty_index_sector(ticker: str) -> str:
    """
    Map a ticker to its Nifty sector INDEX name (for RS multiplier lookup).

    Returns the Nifty sector index name (e.g., "Nifty Bank") or "" if unknown.
    """
    sector = get_stock_sector(ticker)
    return SECTOR_TO_INDEX.get(sector, "")


def get_sector_for_dedup(ticker: str) -> str:
    """
    Get sector for deduplication (max 1 BUY per sector).

    Uses the broader sector name for grouping to avoid concentration.
    Bank + Financial Services → "Banking & Finance"
    """
    sector = get_stock_sector(ticker)

    # Group related sectors for concentration limits
    GROUP_MAP = {
        "Bank": "Banking & Finance",
        "Financial Services": "Banking & Finance",
        "IT": "IT",
        "Pharma": "Pharma",
        "Auto": "Auto",
        "FMCG": "FMCG",
        "Metal": "Metal",
        "Realty": "Realty",
        "Energy": "Energy",
        "Cement": "Materials",
        "Capital Goods": "Industrials",
        "Telecom": "Telecom",
        "Consumer Durables": "Consumer",
        "Infrastructure": "Infrastructure",
        "Media": "Media",
    }
    return GROUP_MAP.get(sector, sector)
