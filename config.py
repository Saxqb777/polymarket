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
MIN_RISK_REWARD = 2.5
EARNINGS_BLACKOUT_DAYS = 7
MONTHLY_DRAWDOWN_CAP_PCT = 0.08
PAPER_TRADE_WEEKS_MIN = 4

# ── Timezone ───────────────────────────────────────────────────────────────────
GULF_TZ = pytz.timezone("Asia/Dubai")  # UTC+4, no DST

# ── Watchlist (101 tickers, tiered $8-$175, updated 2026-05-15) ───────────────
# GREEN ZONE ($10-$150): picked freely by the analyst
# BUFFER ZONE ($8-$10 or $150-$175): analyst may only pick if setup is PREMIUM
# Tickers above $175 or below $8 are excluded at scanner hard-filter time
WATCHLIST = [
    # Tech / Semis (11) — CRM and AKAM are BUFFER ($150-$175)
    "INTC", "ON", "CSCO", "HPQ",
    "PSTG", "SWKS", "MCHP", "LSCC", "BOX",
    "CRM", "AKAM",
    # Fintech / Brokers / Payments (12)
    "SOFI", "HOOD", "PYPL", "AFRM", "XYZ", "UPST", "LC", "RKT",
    "BILL", "FOUR", "TOST", "SSNC",
    # EVs / Auto (5)
    "F", "GM", "RIVN", "LI", "XPEV",
    # Speculative / High-volatility (9)
    "RGTI", "IONQ", "QBTS", "RKLB", "ASTS", "IREN", "MARA", "OKLO", "SMR",
    # Consumer / Travel / Leisure / Retail (17) — DASH is BUFFER ($150-$175)
    "UBER", "ABNB", "DASH", "DKNG", "EBAY", "TGT", "KO", "KHC",
    "PINS", "RBLX", "U",
    "CCL", "NCLH", "MGM", "LVS", "WYNN", "PLAY",
    # Energy / Materials / Industrials (18)
    "XOM", "OXY", "DVN", "HAL", "SLB", "KMI", "ENPH",
    "APA", "EQT", "CTRA", "FCX", "CF", "NEM", "MOS",
    "FTV", "KTOS", "DRS", "OLN",
    # Healthcare / Biotech (13)
    "PFE", "MRNA", "BMY", "GILD", "CVS", "TEVA", "HIMS",
    "DXCM", "HOLX", "EXAS", "INCY", "CRSP", "EXEL",
    # China ADRs (7)
    "JD", "PDD",
    "FUTU", "EDU", "HTHT", "BZ", "MNSO",
    # Media / Entertainment (4)
    "DIS", "T", "VZ", "CMCSA",
    # Momentum / Misc (5)
    "CELH", "LMND", "FLNC", "AMKR", "FORM",
]

# ── Company name mapping (for news queries) ────────────────────────────────────
SYMBOL_TO_COMPANY = {
    # Tech / Semis
    "INTC": "Intel",
    "CRM": "Salesforce",
    "ON": "ON Semiconductor",
    "CSCO": "Cisco Systems",
    "HPQ": "HP Inc",
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
    "RBLX": "Roblox",
    "U": "Unity Software",
    "CCL": "Carnival Corporation",
    "NCLH": "Norwegian Cruise Line",
    "MGM": "MGM Resorts International",
    "LVS": "Las Vegas Sands",
    "WYNN": "Wynn Resorts",
    "PLAY": "Dave and Busters Entertainment",
    # Energy / Materials / Industrials
    "XOM": "ExxonMobil",
    "OXY": "Occidental Petroleum",
    "DVN": "Devon Energy",
    "HAL": "Halliburton",
    "SLB": "Schlumberger",
    "KMI": "Kinder Morgan",
    "ENPH": "Enphase Energy",
    "APA": "APA Corporation",
    "EQT": "EQT Corporation",
    "CTRA": "Coterra Energy",
    "FCX": "Freeport-McMoRan",
    "CF": "CF Industries",
    "NEM": "Newmont Corporation",
    "MOS": "Mosaic Company",
    "FTV": "Fortive Corporation",
    "KTOS": "Kratos Defense and Security",
    "DRS": "Leonardo DRS",
    "OLN": "Olin Corporation",
    # Healthcare / Biotech
    "PFE": "Pfizer",
    "MRNA": "Moderna",
    "BMY": "Bristol Myers Squibb",
    "GILD": "Gilead Sciences",
    "CVS": "CVS Health",
    "TEVA": "Teva Pharmaceutical",
    "HIMS": "Hims and Hers Health",
    "DXCM": "Dexcom",
    "HOLX": "Hologic",
    "EXAS": "Exact Sciences",
    "INCY": "Incyte Corporation",
    "CRSP": "CRISPR Therapeutics",
    "EXEL": "Exelixis",
    # China ADRs
    "JD": "JD.com",
    "PDD": "PDD Holdings",
    "FUTU": "Futu Holdings",
    "EDU": "New Oriental Education",
    "HTHT": "H World Group",
    "BZ": "Kanzhun BOSS Zhipin",
    "MNSO": "MINISO Group",
    # Media / Entertainment
    "DIS": "Walt Disney",
    "T": "AT&T",
    "VZ": "Verizon",
    "CMCSA": "Comcast",
    # Tech / Semis (extended)
    "PSTG": "Pure Storage",
    "SWKS": "Skyworks Solutions",
    "MCHP": "Microchip Technology",
    "LSCC": "Lattice Semiconductor",
    "BOX": "Box Inc",
    "AKAM": "Akamai Technologies",
    # Payments / Fintech (extended)
    "BILL": "Bill.com Holdings",
    "FOUR": "Shift4 Payments",
    "TOST": "Toast Inc",
    "SSNC": "SS&C Technologies",
    # Momentum / Misc
    "CELH": "Celsius Holdings",
    "LMND": "Lemonade Inc",
    "FLNC": "Fluence Energy",
    "AMKR": "Amkor Technology",
    "FORM": "FormFactor",
}

# ── Scanner thresholds ─────────────────────────────────────────────────────────
SCANNER_MIN_VOLUME_20D_AVG = 1_000_000   # shares/day — avoid illiquid names
SCANNER_MIN_PRICE = 8.0                  # hard floor — below this, skip entirely
SCANNER_MAX_PRICE = 175.0               # hard ceiling — above this, skip entirely
PRICE_GREEN_MIN = 10.0                   # green zone lower bound
PRICE_GREEN_MAX = 150.0                  # green zone upper bound
PRICE_BUFFER_MIN = 8.0                   # buffer zone lower bound (= SCANNER_MIN_PRICE)
PRICE_BUFFER_MAX = 175.0                 # buffer zone upper bound (= SCANNER_MAX_PRICE)
# Buffer zone ($8-$10 or $150-$175): candidate passes hard filter but analyst may
# only pick it if the setup qualifies as PREMIUM (R:R >= 3.0 AND target_move >= 10%).
SCANNER_RSI_MIN = 40                     # not deeply oversold
SCANNER_RSI_MAX = 75                     # not extended / overbought
SCANNER_TOP_N = 10                       # candidates passed to analyst

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
