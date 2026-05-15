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

# ── Watchlist (~95 tickers, $20-$100 range, updated 2026-05-15) ───────────────
WATCHLIST = [
    # Tech / Semis (14)
    "INTC", "MU", "AMAT", "LRCX", "QCOM", "ORCL", "CRM", "ADBE",
    "MRVL", "ON", "CSCO", "HPQ", "DELL", "NET",
    # Fintech / Brokers (8) — XYZ is Block Inc's ticker (changed from SQ on NYSE Jan 2025)
    "SOFI", "HOOD", "PYPL", "AFRM", "XYZ", "UPST", "LC", "RKT",
    # EVs / Auto (5)
    "F", "GM", "RIVN", "LI", "XPEV",
    # Speculative / High-volatility (9) — only $20+ names
    "RGTI", "IONQ", "QBTS", "RKLB", "ASTS", "IREN", "MARA", "OKLO", "SMR",
    # Consumer / Travel / Retail (12)
    "UBER", "ABNB", "DASH", "DKNG", "EBAY", "TGT", "KO", "KHC",
    "PINS", "SNAP", "RBLX", "U",
    # Energy / Materials / Industrials (9)
    "XOM", "OXY", "DVN", "MPC", "HAL", "SLB", "KMI", "ENPH", "FSLR",
    # Healthcare / Biotech (7)
    "PFE", "MRNA", "BMY", "GILD", "CVS", "TEVA", "HIMS",
    # China ADRs (2)
    "JD", "PDD",
    # Media / Entertainment (4)
    "DIS", "T", "VZ", "CMCSA",
]

# ── Company name mapping (for news queries) ────────────────────────────────────
SYMBOL_TO_COMPANY = {
    # Tech / Semis
    "INTC": "Intel",
    "MU": "Micron Technology",
    "AMAT": "Applied Materials",
    "LRCX": "Lam Research",
    "QCOM": "Qualcomm",
    "ORCL": "Oracle",
    "CRM": "Salesforce",
    "ADBE": "Adobe",
    "MRVL": "Marvell Technology",
    "ON": "ON Semiconductor",
    "CSCO": "Cisco Systems",
    "HPQ": "HP Inc",
    "DELL": "Dell Technologies",
    "NET": "Cloudflare",
    # Fintech / Brokers
    "SOFI": "SoFi Technologies",
    "HOOD": "Robinhood",
    "PYPL": "PayPal",
    "AFRM": "Affirm",
    "XYZ": "Block Inc",
    "UPST": "Upstart Holdings",
    "LC": "LendingClub",
    "RKT": "Rocket Companies",
    # EVs / Auto
    "F": "Ford Motor",
    "GM": "General Motors",
    "RIVN": "Rivian Automotive",
    "LI": "Li Auto",
    "XPEV": "XPeng",
    # Speculative / High-volatility
    "RGTI": "Rigetti Computing",
    "IONQ": "IonQ",
    "QBTS": "D-Wave Quantum",
    "RKLB": "Rocket Lab",
    "ASTS": "AST SpaceMobile",
    "IREN": "IREN Limited",
    "MARA": "MARA Holdings",
    "OKLO": "Oklo Inc",
    "SMR": "NuScale Power",
    # Consumer / Travel / Retail
    "UBER": "Uber",
    "ABNB": "Airbnb",
    "DASH": "DoorDash",
    "DKNG": "DraftKings",
    "EBAY": "eBay",
    "TGT": "Target",
    "KO": "Coca-Cola",
    "KHC": "Kraft Heinz",
    "PINS": "Pinterest",
    "SNAP": "Snap Inc",
    "RBLX": "Roblox",
    "U": "Unity Software",
    # Energy / Materials / Industrials
    "XOM": "ExxonMobil",
    "OXY": "Occidental Petroleum",
    "DVN": "Devon Energy",
    "MPC": "Marathon Petroleum",
    "HAL": "Halliburton",
    "SLB": "Schlumberger",
    "KMI": "Kinder Morgan",
    "ENPH": "Enphase Energy",
    "FSLR": "First Solar",
    # Healthcare / Biotech
    "PFE": "Pfizer",
    "MRNA": "Moderna",
    "BMY": "Bristol Myers Squibb",
    "GILD": "Gilead Sciences",
    "CVS": "CVS Health",
    "TEVA": "Teva Pharmaceutical",
    "HIMS": "Hims and Hers Health",
    # China ADRs
    "JD": "JD.com",
    "PDD": "PDD Holdings",
    # Media / Entertainment
    "DIS": "Walt Disney",
    "T": "AT&T",
    "VZ": "Verizon",
    "CMCSA": "Comcast",
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
