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

# ── Watchlist (147 tickers, expanded 2026-05-14) ──────────────────────────────
WATCHLIST = [
    # Technology (15)
    "AAPL", "MSFT", "NVDA", "AMD", "GOOGL", "META", "AMZN", "CRM", "ADBE", "ORCL",
    "QCOM", "INTC", "MU", "AMAT", "LRCX",
    # High-volatility growth (6)
    "PLTR", "COIN", "SNOW", "UBER", "PANW", "AVGO",
    # Healthcare (10)
    "JNJ", "UNH", "PFE", "ABBV", "MRK", "LLY", "TMO", "DHR", "ABT", "ISRG",
    # Financials (10)
    "JPM", "BAC", "GS", "MS", "V", "MA", "AXP", "BLK", "SCHW", "C",
    # Energy (6)
    "XOM", "CVX", "COP", "SLB", "EOG", "FANG",
    # Consumer Discretionary (8)
    "TSLA", "HD", "MCD", "NKE", "SBUX", "TGT", "LOW", "BKNG",
    # Consumer Staples (6)
    "WMT", "PG", "KO", "PEP", "COST", "PM",
    # Industrials (7)
    "CAT", "BA", "HON", "UPS", "RTX", "DE", "LMT",
    # Materials / Utilities / Real Estate (5)
    "LIN", "APD", "NEE", "AMT", "SPG",
    # Momentum mid/large caps (31)
    "NOW", "ANET", "MRVL", "ON", "KLAC", "ASML", "ARM", "SMCI", "DELL", "HPQ",
    "SHOP", "NET", "DDOG", "CRWD", "ZS", "SNPS", "CDNS", "FTNT", "TEAM", "WDAY",
    "ABNB", "DASH", "RBLX", "U", "ROKU", "SNAP", "PINS", "SQ", "HOOD", "DKNG",
    "AFRM",
    # China ADRs (8)
    "BABA", "PDD", "JD", "NIO", "LI", "XPEV", "BIDU", "BILI",
    # Speculative / high-volatility (27)
    "RGTI", "IONQ", "QBTS", "RKLB", "ASTS", "LUNR", "ACHR", "JOBY", "PLUG", "BBAI",
    "SOUN", "IREN", "RIOT", "MARA", "OKLO", "SMR", "CIFR", "CLSK", "WULF", "APLD",
    "AI", "LCID", "RIVN", "CHPT", "RUN", "ENPH", "FSLR",
    # Active sector (8)
    "MRNA", "VRTX", "GILD", "REGN", "OXY", "DVN", "MPC", "PSX",
]

# ── Company name mapping (for news queries) ────────────────────────────────────
SYMBOL_TO_COMPANY = {
    # Technology
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "Nvidia",
    "AMD": "Advanced Micro Devices",
    "GOOGL": "Alphabet Inc",
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
    # High-volatility growth
    "PLTR": "Palantir",
    "COIN": "Coinbase",
    "SNOW": "Snowflake",
    "UBER": "Uber",
    "PANW": "Palo Alto Networks",
    "AVGO": "Broadcom",
    # Healthcare
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
    # Financials
    "JPM": "JPMorgan Chase",
    "BAC": "Bank of America",
    "GS": "Goldman Sachs",
    "MS": "Morgan Stanley",
    "V": "Visa Inc",
    "MA": "Mastercard",
    "AXP": "American Express",
    "BLK": "BlackRock",
    "SCHW": "Charles Schwab",
    "C": "Citigroup",
    # Energy
    "XOM": "ExxonMobil",
    "CVX": "Chevron",
    "COP": "ConocoPhillips",
    "SLB": "Schlumberger",
    "EOG": "EOG Resources",
    "FANG": "Diamondback Energy",
    # Consumer Discretionary
    "TSLA": "Tesla",
    "HD": "Home Depot",
    "MCD": "McDonald's",
    "NKE": "Nike",
    "SBUX": "Starbucks",
    "TGT": "Target",
    "LOW": "Lowe's",
    "BKNG": "Booking Holdings",
    # Consumer Staples
    "WMT": "Walmart",
    "PG": "Procter Gamble",
    "KO": "Coca-Cola",
    "PEP": "PepsiCo",
    "COST": "Costco",
    "PM": "Philip Morris",
    # Industrials
    "CAT": "Caterpillar",
    "BA": "Boeing",
    "HON": "Honeywell",
    "UPS": "United Parcel Service",
    "RTX": "RTX Raytheon",
    "DE": "John Deere",
    "LMT": "Lockheed Martin",
    # Materials / Utilities / Real Estate
    "LIN": "Linde",
    "APD": "Air Products",
    "NEE": "NextEra Energy",
    "AMT": "American Tower",
    "SPG": "Simon Property Group",
    # Momentum mid/large caps
    "NOW": "ServiceNow",
    "ANET": "Arista Networks",
    "MRVL": "Marvell Technology",
    "ON": "ON Semiconductor",
    "KLAC": "KLA Corporation",
    "ASML": "ASML Holding",
    "ARM": "Arm Holdings",
    "SMCI": "Super Micro Computer",
    "DELL": "Dell Technologies",
    "HPQ": "HP Inc",
    "SHOP": "Shopify",
    "NET": "Cloudflare",
    "DDOG": "Datadog",
    "CRWD": "CrowdStrike",
    "ZS": "Zscaler",
    "SNPS": "Synopsys",
    "CDNS": "Cadence Design Systems",
    "FTNT": "Fortinet",
    "TEAM": "Atlassian",
    "WDAY": "Workday",
    "ABNB": "Airbnb",
    "DASH": "DoorDash",
    "RBLX": "Roblox",
    "U": "Unity Software",
    "ROKU": "Roku",
    "SNAP": "Snap",
    "PINS": "Pinterest",
    "SQ": "Block Inc",
    "HOOD": "Robinhood",
    "DKNG": "DraftKings",
    "AFRM": "Affirm",
    # China ADRs
    "BABA": "Alibaba",
    "PDD": "PDD Holdings",
    "JD": "JD.com",
    "NIO": "NIO Inc",
    "LI": "Li Auto",
    "XPEV": "XPeng",
    "BIDU": "Baidu",
    "BILI": "Bilibili",
    # Speculative / high-volatility
    "RGTI": "Rigetti Computing",
    "IONQ": "IonQ",
    "QBTS": "D-Wave Quantum",
    "RKLB": "Rocket Lab",
    "ASTS": "AST SpaceMobile",
    "LUNR": "Intuitive Machines",
    "ACHR": "Archer Aviation",
    "JOBY": "Joby Aviation",
    "PLUG": "Plug Power",
    "BBAI": "BigBear.ai",
    "SOUN": "SoundHound AI",
    "IREN": "IREN Ltd",
    "RIOT": "Riot Platforms",
    "MARA": "Marathon Digital Holdings",
    "OKLO": "Oklo Inc",
    "SMR": "NuScale Power",
    "CIFR": "Cipher Mining",
    "CLSK": "CleanSpark",
    "WULF": "TeraWulf",
    "APLD": "Applied Digital",
    "AI": "C3.ai",
    "LCID": "Lucid Group",
    "RIVN": "Rivian",
    "CHPT": "ChargePoint",
    "RUN": "Sunrun",
    "ENPH": "Enphase Energy",
    "FSLR": "First Solar",
    # Active sector
    "MRNA": "Moderna",
    "VRTX": "Vertex Pharmaceuticals",
    "GILD": "Gilead Sciences",
    "REGN": "Regeneron Pharmaceuticals",
    "OXY": "Occidental Petroleum",
    "DVN": "Devon Energy",
    "MPC": "Marathon Petroleum",
    "PSX": "Phillips 66",
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
