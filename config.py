import os
import pytz
from dotenv import load_dotenv

load_dotenv()

# ── Account ────────────────────────────────────────────────────────────────────
ACCOUNT_CAPITAL = float(os.getenv("ACCOUNT_CAPITAL", 650))
RISK_PER_TRADE_PCT = float(os.getenv("RISK_PER_TRADE_PCT", 0.02))
MAX_POSITION_SIZE_PCT = float(os.getenv("MAX_POSITION_SIZE_PCT", 0.20))
PAPER_TRADING = os.getenv("PAPER_TRADING", "true").lower() == "true"

# ── Conviction-based position sizing ───────────────────────────────────────────
# "Buy big when the setup earns it." The size ceiling scales with the analyst's
# own quality_tier + confidence rating. The actual share count is still the
# TIGHTER of (a) this conviction cap and (b) the per-trade risk rule above, so a
# wide stop will shrink the position even on an A+ setup — risk stays controlled.
# Percentages are of ACCOUNT_CAPITAL.
CONVICTION_SIZING = {
    "A_PLUS":     0.20,   # PREMIUM + HIGH confidence — full conviction, buy big
    "PREMIUM":    0.14,   # PREMIUM (any confidence) or STANDARD + HIGH
    "STANDARD":   0.09,   # STANDARD setup
    "ACCEPTABLE": 0.05,   # ACCEPTABLE — small starter position
    "BELOW_BAR":  0.03,   # below bar — token size only, bot doesn't recommend it
}
# Expected holding horizon (trading days). Drives the reachability check: a target
# the stock realistically can't travel to within this window is a poor swing.
HOLD_DAYS = int(os.getenv("HOLD_DAYS", 5))

# ── Run cadence ────────────────────────────────────────────────────────────────
# The bot now runs on a configurable cadence (Railway cron drives the real
# schedule; this controls the copy + the dashboard countdown so everything stays
# coherent). Default = every 2 days. Set RUN_CADENCE_DAYS=7 to go back to weekly.
RUN_CADENCE_DAYS = int(os.getenv("RUN_CADENCE_DAYS", 2))
RUN_HOUR_UTC = int(os.getenv("RUN_HOUR_UTC", 16))   # 16:00 UTC = 20:00 Gulf


def _cadence_label(days: int) -> str:
    if days <= 1:
        return "daily"
    if days == 7:
        return "weekly"
    return f"every {days} days"


CADENCE_LABEL = _cadence_label(RUN_CADENCE_DAYS)   # e.g. "every 2 days"

# ── Risk Rules (hardcoded — never change these) ────────────────────────────────
MIN_RISK_REWARD = 2.5
EARNINGS_BLACKOUT_DAYS = 7
MONTHLY_DRAWDOWN_CAP_PCT = 0.08
PAPER_TRADE_WEEKS_MIN = 4
# Quality discipline: because the bot now scans frequently (every 2 days), it is
# NOT forced to trade every run. When STRICT_QUALITY is on, any pick that lands
# BELOW_BAR is converted to NO_TRADE — another scan comes in 2 days. Frequency up,
# quality up. Set to "false" to send below-bar picks anyway (old behaviour).
STRICT_QUALITY = os.getenv("STRICT_QUALITY", "true").lower() == "true"

# ── Market regime filter ───────────────────────────────────────────────────────
# Before picking, the bot checks the broad market (SPY + QQQ). Going long into a
# falling market is a losing game. In RISK_OFF the analyst is told to demand a
# stronger setup or sit out.
REGIME_INDICES = ["SPY", "QQQ"]
REGIME_ENABLED = os.getenv("REGIME_ENABLED", "true").lower() == "true"

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
    # ── 2026-06 expansion: liquid $10–100 names (sweet spot) ──────────────────
    # Banks / Financials (7)
    "BAC", "WFC", "C", "USB", "KEY", "SCHW", "ALLY",
    # Airlines (4)
    "AAL", "UAL", "DAL", "LUV",
    # Metals / Mining (7)
    "CLF", "X", "AA", "VALE", "GOLD", "KGC", "HL",
    # Energy (5)
    "COP", "MPC", "PSX", "SU", "ET",
    # Consumer / Retail / Media (12)
    "NKE", "SBUX", "M", "KSS", "BBY", "GME", "WBA", "PARA", "WBD", "SNAP", "LYFT", "CNK",
    # China ADRs (4)
    "BABA", "BIDU", "TCOM", "TME",
    # Crypto miners (3)
    "RIOT", "CLSK", "WULF",
    # Semis / Hardware (3)
    "MU", "DELL", "STX",
    # ── 2026-06 low-price expansion: $10–$50 sweet spot ───────────────────────
    # Pharma / Biotech ($10–$40)
    "DNLI", "ARVN", "BEAM", "ARRY",
    # Fintech / Lending ($10–$50)
    "UWMC", "PFSI",
    # EV / Clean Energy ($10–$30)
    "CHPT", "STEM",
    # Tech / Software / AI ($10–$40)
    "AI", "BBAI",
    # Banks / Regional ($10–$25)
    "HBAN", "RF", "FITB", "ZION",
    # Industrials / Aerospace
    "JOBY", "ACHR",
    # Consumer turnaround / momentum
    "OPEN", "LAZR",
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
    # ── 2026-06 expansion ─────────────────────────────────────────────────────
    # Banks / Financials
    "BAC": "Bank of America",
    "WFC": "Wells Fargo",
    "C": "Citigroup",
    "USB": "U.S. Bancorp",
    "KEY": "KeyCorp",
    "SCHW": "Charles Schwab",
    "ALLY": "Ally Financial",
    # Airlines
    "AAL": "American Airlines",
    "UAL": "United Airlines",
    "DAL": "Delta Air Lines",
    "LUV": "Southwest Airlines",
    # Metals / Mining
    "CLF": "Cleveland-Cliffs",
    "X": "United States Steel",
    "AA": "Alcoa",
    "VALE": "Vale",
    "GOLD": "Barrick Gold",
    "KGC": "Kinross Gold",
    "HL": "Hecla Mining",
    # Energy
    "COP": "ConocoPhillips",
    "MPC": "Marathon Petroleum",
    "PSX": "Phillips 66",
    "SU": "Suncor Energy",
    "ET": "Energy Transfer",
    # Consumer / Retail / Media
    "NKE": "Nike",
    "SBUX": "Starbucks",
    "M": "Macy's",
    "KSS": "Kohl's",
    "BBY": "Best Buy",
    "GME": "GameStop",
    "WBA": "Walgreens Boots Alliance",
    "PARA": "Paramount Global",
    "WBD": "Warner Bros Discovery",
    "SNAP": "Snap",
    "LYFT": "Lyft",
    "CNK": "Cinemark",
    # China ADRs
    "BABA": "Alibaba",
    "BIDU": "Baidu",
    "TCOM": "Trip.com",
    "TME": "Tencent Music Entertainment",
    # Crypto miners
    "RIOT": "Riot Platforms",
    "CLSK": "CleanSpark",
    "WULF": "TeraWulf",
    # Semis / Hardware
    "MU": "Micron Technology",
    "DELL": "Dell Technologies",
    "STX": "Seagate Technology",
    # ── 2026-06 low-price expansion ($10–$50 sweet spot) ─────────────────────
    # Pharma / Biotech
    "ZYME": "Zymeworks",
    "DNLI": "Denali Therapeutics",
    "ARVN": "Arvinas",
    "BEAM": "Beam Therapeutics",
    "ARRY": "Array Technologies",
    # Fintech / Lending
    "OPEN": "Opendoor Technologies",
    "UWMC": "UWM Holdings",
    "PFSI": "PennyMac Financial Services",
    # EV / Clean Energy
    "CHPT": "ChargePoint",
    "BLNK": "Blink Charging",
    "STEM": "Stem Inc",
    # Industrials / Defense
    "JOBY": "Joby Aviation",
    "ACHR": "Archer Aviation",
    "LILM": "Lilium",
    # Tech / Software
    "AI": "C3.ai",
    "BBAI": "BigBear.ai",
    "CLOV": "Clover Health",
    "PRCT": "Procept BioRobotics",
    # Banks / Regional
    "HBAN": "Huntington Bancshares",
    "RF": "Regions Financial",
    "FITB": "Fifth Third Bancorp",
    "ZION": "Zions Bancorporation",
    # Consumer
    "NKLA": "Nikola Corporation",
    "LAZR": "Luminar Technologies",
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
SCANNER_TOP_N = 12                       # candidates passed to analyst

# ── Relative strength ──────────────────────────────────────────────────────────
# Stocks are scored on how much they OUTPERFORM SPY over RS_PERIOD trading days.
# Trade leaders, not laggards. Outperformance adds to the scanner score so strong
# relative-strength names rise to the top 10.
RS_BENCHMARK = "SPY"
RS_PERIOD = 60                           # ~3 months of trading days
RS_MIN_PCT = -5.0                        # soft floor — below this RS, no score bonus

# ── Trend strength (ADX) ───────────────────────────────────────────────────────
ADX_PERIOD = 14
ADX_STRONG = 25                          # ADX above this = strong, tradeable trend
ADX_CHOPPY = 20                          # ADX below this = choppy, analyst should be wary

# ── Technical indicator periods ────────────────────────────────────────────────
MA_SHORT = 20
MA_LONG = 50
MA_TREND = 200
RSI_PERIOD = 14
ATR_PERIOD = 14
LOOKBACK_DAYS = 252   # 1 year of daily bars

# ── Models ─────────────────────────────────────────────────────────────────────
# The analyst (the "brain") runs on Opus 4.8 with ADAPTIVE thinking. Opus 4.8 no
# longer uses a fixed thinking-token budget — instead it decides how deeply to
# reason, and the `effort` knob controls how hard it works. We run it at high
# effort so it reasons deeply (taking minutes if needed) to find the single best
# trade. Quality of reasoning > saving pennies. The call streams so a long
# deep-thinking request never hits a timeout.
#   effort options: "low" | "medium" | "high" | "max"  ("max" = hardest, slowest)
ANALYST_MODEL = os.getenv("ANALYST_MODEL", "claude-opus-4-8")  # trade decision brain
ANALYST_EFFORT = os.getenv("ANALYST_EFFORT", "high")           # thinking depth knob
ANALYST_MAX_TOKENS = int(os.getenv("ANALYST_MAX_TOKENS", 16000))  # hard output ceiling
ANALYST_TIMEOUT_SECS = int(os.getenv("ANALYST_TIMEOUT_SECS", 900))  # 15 min ceiling
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
