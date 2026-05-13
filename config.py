import os
import pytz
from dotenv import load_dotenv

load_dotenv()

# ── Account ────────────────────────────────────────────────────────────────────
ACCOUNT_CAPITAL = float(os.getenv("ACCOUNT_CAPITAL", 10000))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 0.01))
MAX_POSITION_SIZE_PCT = float(os.getenv("MAX_POSITION_SIZE_PCT", 0.05))
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ── Risk Rules (hardcoded — never change these) ────────────────────────────────
MIN_RISK_REWARD = 1.8
EARNINGS_BLACKOUT_DAYS = 7
MONTHLY_DRAWDOWN_CAP_PCT = 0.08
PAPER_TRADE_WEEKS_MIN = 4

# ── Timezone ───────────────────────────────────────────────────────────────────
GULF_TZ = pytz.timezone("Asia/Dubai")  # UTC+4, no DST

# ── Watchlist (72 tickers, approved 2026-05-13) ────────────────────────────────
WATCHLIST = [
    # Technology
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "AMZN", "CRM", "ADBE", "ORCL",
    "QCOM", "INTC", "MU", "AMAT", "LRCX",
    # High-volatility growth
    "PLTR", "COIN", "SNOW", "UBER", "PANW", "AVGO",
    # Healthcare
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "DHR", "ABT", "ISRG",
    # Financials
    "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BLK", "SCHW", "C",
    # Energy
    "XOM", "CVX", "COP", "SLB", "EOG", "FANG",
    # Consumer Discretionary
    "TSLA", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "BKNG",
    # Consumer Staples
    "WMT", "PG", "KO", "PEP", "COST", "PM",
    # Industrials
    "CAT", "BA", "HON", "UPS", "RTX", "DE", "LMT",
    # Materials / Utilities / Real Estate
    "LIN", "APD", "NEE", "AMT", "SPG",
]

# ── Company name mapping (for news queries) ────────────────────────────────────
SYMBOL_TO_COMPANY = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "AMD": "Advanced Micro Devices",
    "GOOGL": "Alphabet Google",
    "META": "Meta Platforms",
    "AMZN": "Amazon",
    "CRM": "Salesforce",
    "ADBE": "Adobe",
    "ORCL": "Oracle",
    "QCOM": "Qualcomm",
    "INTC": "Intel",
    "MU": "Micron Technology",
    "AMAT": "Applied Materials",
    "LRCX": "Lam Research",
    "PLTR": "Palantir",
    "COIN": "Coinbase",
    "SNOW": "Snowflake",
    "UBER": "Uber",
    "PANW": "Palo Alto Networks",
    "AVGO": "Broadcom",
    "JNJ": "Johnson Johnson",
    "UNH": "UnitedHealth",
    "PFE": "Pfizer",
    "ABBV": "AbbVie",
    "MRK": "Merck",
    "LLY": "Eli Lilly",
    "TMO": "Thermo Fisher Scientific",
    "DHR": "Danaher",
    "ABT": "Abbott Laboratories",
    "ISRG": "Intuitive Surgical",
    "JPM": "JPMorgan Chase",
    "BAC": "Bank of America",
    "GS": "Goldman Sachs",
    "MS": "Morgan Stanley",
    "V": "Visa",
    "MA": "Mastercard",
    "AXP": "American Express",
    "BLK": "BlackRock",
    "SCHW": "Charles Schwab",
    "C": "Citigroup",
    "XOM": "ExxonMobil",
    "CVX": "Chevron",
    "COP": "ConocoPhillips",
    "SLB": "SLB Schlumberger",
    "EOG": "EOG Resources",
    "FANG": "Diamondback Energy",
    "TSLA": "Tesla",
    "HD": "Home Depot",
    "MCD": "McDonald's",
    "NKE": "Nike",
    "SBUX": "Starbucks",
    "TGT": "Target",
    "LOW": "Lowe's",
    "BKNG": "Booking Holdings",
    "WMT": "Walmart",
    "PG": "Procter Gamble",
    "KO": "Coca-Cola",
    "PEP": "PepsiCo",
    "COST": "Costco",
    "PM": "Philip Morris",
    "CAT": "Caterpillar",
    "BA": "Boeing",
    "HON": "Honeywell",
    "UPS": "United Parcel Service",
    "RTX": "RTX Raytheon",
    "DE": "John Deere",
    "LMT": "Lockheed Martin",
    "LIN": "Linde",
    "APD": "Air Products",
    "NEE": "NextEra Energy",
    "AMT": "American Tower",
    "SPG": "Simon Property Group",
}

# ── Scanner thresholds ─────────────────────────────────────────────────────────
SCANNER_MIN_VOLUME_20D_AVG = 1_000_000   # shares/day — avoid illiquid names
SCANNER_MIN_PRICE = 10.0
SCANNER_MAX_PRICE = 1_000.0
SCANNER_RSI_MIN = 40                      # not deeply oversold
SCANNER_RSI_MAX = 75                      # not extended / overbought
SCANNER_TOP_N = 10                        # candidates passed to analyst

# ── Technical indicator periods ────────────────────────────────────────────────
MA_SHORT = 20
MA_LONG = 50
MA_TREND = 200
RSI_PERIOD = 14
ATR_PERIOD = 14
LOOKBACK_DAYS = 252   # 1 year of daily bars

# ── Models ─────────────────────────────────────────────────────────────────────
ANALYST_MODEL = "claude-sonnet-4-6"       # trade decision brain
FILTER_MODEL = "claude-haiku-4-5"         # news sentiment tagging (cheap)

# ── API keys ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
POLYGON_API_KEY = os.getenv("POLYGON_API_KEY")
FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")
MARKETAUX_API_KEY = os.getenv("MARKETAUX_API_KEY")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ── Storage / logging ──────────────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "data/trades.db")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_DIR = "logs"
