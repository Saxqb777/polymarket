# PLAN.md — The Swing Trading Bot, Step by Step

> **Read `CLAUDE.md` first. Then this file. We build in order. No skipping.**

---

## 🎯 What We're Building (in one paragraph)

A cloud-hosted Python bot that runs every **Sunday at 8 PM Gulf time**. It scans ~100 liquid US stocks, pulls the last 7 days of news and the earnings calendar, runs technical analysis (trend, momentum, support/resistance), and sends all of that to Claude as an analyst. Claude picks **one stock** with the best risk/reward for the upcoming week, writes a complete trade plan (entry zone, stop-loss, target, position size, reasoning), and the bot delivers it to my Telegram. Every pick is logged to SQLite so we can track performance, refine the system, and learn.

---

## 🧱 The Architecture (the flow, visually)

```
SUNDAY 8 PM GULF TIME
        │
        ▼
┌─────────────────────┐
│ 1. SCANNER          │  Reads watchlist.py → filters by volume, trend, not crashing
│                     │  Output: top 10 candidates
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ 2. NEWS + EARNINGS  │  For each of the 10:
│                     │   - Last 7 days of news (NewsAPI + Marketaux)
│                     │   - Earnings in next 7 days? → drop the stock
│                     │   - Sentiment score
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ 3. TECHNICALS       │  For each survivor:
│                     │   - RSI, 20/50 MA, ATR (volatility)
│                     │   - Recent support/resistance levels
│                     │   - Volume trend
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ 4. CLAUDE ANALYST   │  All data → Claude Sonnet
│                     │  Prompt: "Pick ONE. Give entry, stop, target, reasoning."
│                     │  Claude can also say: "No trade this week."
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ 5. TRADE PLAN       │  Calculate position size based on:
│                     │   - My capital (from settings)
│                     │   - Stop distance (risk per share)
│                     │   - Max 5% position rule
└──────────┬──────────┘
           ▼
┌─────────────────────┐
│ 6. LOG + ALERT      │  Save to SQLite
│                     │  Send formatted message to Telegram
└─────────────────────┘
```

---

## 📋 The Build Plan — 10 Phases

Each phase is a chunk we complete and test before moving on. Claude Code: **after each phase, update `PROGRESS.md` and ask me to verify before continuing.**

---

### **PHASE 1 — Foundation & Local Setup** *(Day 1, ~1 hour)*

**Goal:** I have a working Python project on my laptop and Claude Code can run code in it.

**Substeps:**
1.1. Verify Python 3.11+ is installed (if not, walk me through installing it)
1.2. Create the folder structure from `CLAUDE.md`
1.3. Set up a Python virtual environment (`venv`) and explain what it is
1.4. Create `.gitignore` with proper entries (`.env`, `__pycache__`, `data/`, `logs/`, `venv/`)
1.5. Create `.env.example` with placeholders for all API keys we'll need
1.6. Create `requirements.txt` (empty for now; we'll add as we go)
1.7. Initialize git, make first commit
1.8. Create GitHub repo and push (private repo)

**Done when:** I can run `python --version` and `pip list` in the activated venv and the repo is on GitHub.

---

### **PHASE 2 — API Keys & Connections** *(Day 1, ~45 min)*

**Goal:** All 5 services are signed up for, keys are in `.env`, and we have a tiny script that proves each one works.

**Substeps:**
2.1. Walk me through signing up for **Polygon.io** free tier → save key
2.2. Walk me through **NewsAPI** signup → save key
2.3. Walk me through **Marketaux** signup → save key
2.4. Walk me through **Finnhub** signup (for earnings calendar) → save key
2.5. Walk me through creating a **Telegram bot** via @BotFather, get bot token + my chat ID
2.6. Confirm my **Anthropic API key** is in `.env`
2.7. Build `tests/test_connections.py` — pings each API, prints ✅ or ❌

**Done when:** Running the test script shows all 5 services responding.

---

### **PHASE 3 — The Watchlist & Settings** *(Day 2, ~30 min)*

**Goal:** Configuration files are set up so we can tune the bot without touching code.

**Substeps:**
3.1. Build `config/watchlist.py` — start with ~80 liquid US stocks:
     - Mega caps (AAPL, MSFT, GOOGL, AMZN, META, NVDA, TSLA, etc.)
     - Popular swing names (AMD, PLTR, COIN, SOFI, etc.)
     - Sector ETFs as context (XLF, XLK, SPY for market regime)
3.2. Build `config/settings.py`:
     - Trading capital (I'll tell you the number)
     - Max position % (5%)
     - Min risk/reward (1.8)
     - Monthly drawdown cap (-8%)
     - Telegram chat ID
     - Timezone (Asia/Dubai)
3.3. Add docstrings explaining each setting

**Done when:** I can edit either file and the bot will use the new values next run.

---

### **PHASE 4 — The Scanner Module** *(Day 2-3, ~2 hours)*

**Goal:** Given the watchlist, return the top 10 candidates based on simple filters.

**Substeps:**
4.1. Build `src/scanner.py` with these filters:
     - Average daily volume > 1M shares (liquidity)
     - Price > $5 (no penny stocks)
     - Not down more than 10% in last 5 days (no falling knives)
     - Above 50-day moving average OR within 3% of breaking above it
4.2. Rank survivors by a composite score:
     - Momentum (1-month return)
     - Volume surge (recent vs average)
     - Proximity to breakout
4.3. Return top 10
4.4. Build `tests/test_scanner.py` — runs scanner, prints the 10 names

**Done when:** Scanner outputs a sensible list of 10 stocks I'd actually consider trading.

---

### **PHASE 5 — News & Earnings Intelligence** *(Day 3-4, ~3 hours)* — *The Edge*

**Goal:** For each of the 10 candidates, build a rich news + earnings profile.

**Substeps:**
5.1. Build `src/news.py`:
     - For each ticker, fetch last 7 days of headlines from NewsAPI
     - Cross-reference with Marketaux for coverage gaps
     - Deduplicate (same story from multiple outlets)
     - Tag each headline: bullish / bearish / neutral (via Claude Haiku — cheap)
     - Identify catalysts: earnings beat, upgrades, product news, M&A, FDA, etc.
5.2. Fetch earnings calendar from Finnhub:
     - **Drop any stock with earnings in the next 7 days** — non-negotiable rule
5.3. Build a "news summary" object per stock:
     ```
     {
       ticker: "AMD",
       headline_count: 12,
       sentiment: "bullish",
       key_catalysts: ["AI chip launch", "analyst upgrade"],
       earnings_next_7d: false,
       most_important_headline: "..."
     }
     ```
5.4. Test on 5 known stocks to confirm news quality

**Done when:** I can see real, recent news context per candidate, and earnings-risk stocks are filtered out.

---

### **PHASE 6 — Technical Analysis** *(Day 4-5, ~2 hours)*

**Goal:** Compute the key technical metrics for each remaining candidate.

**Substeps:**
6.1. Build `src/technicals.py`:
     - **Trend:** 20-day MA, 50-day MA, are they aligned bullish?
     - **Momentum:** RSI(14) — flag overbought (>70) or oversold (<30)
     - **Volatility:** ATR(14) — used later for stop-loss sizing
     - **Levels:** Recent swing high, swing low (last 30 days) → support & resistance
     - **Volume:** Last 5 days vs 20-day average
6.2. Output per stock:
     ```
     {
       ticker: "AMD",
       price: 152.34,
       trend: "bullish",
       rsi: 62,
       atr: 4.12,
       support: 148.00,
       resistance: 158.50,
       volume_surge: 1.4
     }
     ```
6.3. Use the `ta` Python library (cleaner than rolling our own)

**Done when:** Numbers match what I'd see on TradingView for the same stocks.

---

### **PHASE 7 — The Claude Analyst** *(Day 5-6, ~3 hours)* — *The Brain*

**Goal:** Send a beautifully structured prompt to Claude Sonnet, get back the one pick with full reasoning.

**Substeps:**
7.1. Build `src/analyst.py`
7.2. Craft the system prompt — Claude is a "disciplined swing trader, 5-day holding period, focused on risk-adjusted returns, willing to say 'no trade this week' if setups are weak"
7.3. Construct the user prompt with all 10 candidates' news + technicals in a clean structured format
7.4. Request a JSON-formatted response:
     ```json
     {
       "pick": "AMD" or null,
       "confidence": "high|medium|low",
       "entry_zone": [148.00, 150.00],
       "stop_loss": 144.00,
       "target": 158.00,
       "thesis": "2-3 sentence why",
       "key_risks": ["earnings of competitor on Tuesday", "..."],
       "no_trade_reason": null
     }
     ```
7.5. Validate the JSON, recompute risk/reward, reject if below 1.8
7.6. If no valid pick → bot reports "No trade this week" with reasoning

**Done when:** I can run the analyst on real data and get a thoughtful, well-reasoned pick (or a justified no-trade).

---

### **PHASE 8 — Trade Plan & Position Sizing** *(Day 6, ~1 hour)*

**Goal:** Turn Claude's pick into a complete trade plan with exact share count.

**Substeps:**
8.1. Build `src/trade_plan.py`
8.2. Calculate position size:
     - Risk per trade = 1% of capital (so a -3% stop on the trade = max -1% to portfolio)
     - Shares = (capital × 0.01) / (entry − stop)
     - Cap at 5% of capital position size
8.3. Format the final trade plan:
     ```
     📊 SWING TRADE — Week of May 18
     
     🎯 Pick: AMD
     Confidence: HIGH
     
     📈 Entry zone: $148.00 – $150.00
     🛑 Stop-loss: $144.00 (-3.4%)
     🏁 Target: $158.00 (+5.4%)
     ⚖️ Risk/Reward: 1:1.6
     
     💰 Position size: 33 shares (~$4,950)
     🎲 Risk on trade: $198 (1% of capital)
     
     💡 Thesis:
     [Claude's 2-3 sentence reasoning]
     
     ⚠️ Watch out for:
     [Key risks]
     
     ✅ Plan: Buy in entry zone Mon/Tue morning.
        Place stop immediately.
        Hold until Friday close or target hit.
     ```

**Done when:** Output is clear enough that I can execute the trade without thinking.

---

### **PHASE 9 — Telegram Delivery + Logging** *(Day 7, ~1.5 hours)*

**Goal:** Message lands on my phone every Sunday, every pick is saved.

**Substeps:**
9.1. Build `src/telegram_bot.py` — sends formatted message to my chat ID
9.2. Build `src/storage.py` — SQLite database with table:
     - id, week_of, ticker, entry_low, entry_high, stop, target, shares, thesis, status, actual_pnl, notes
9.3. Build `src/main.py` — orchestrates the whole flow end-to-end
9.4. Run it manually, confirm message arrives + pick is logged
9.5. Add a `/status` Telegram command — I can text the bot to ask "how are we doing?" and it replies with paper trade record

**Done when:** I get a real trade plan on my phone from running `python src/main.py`.

---

### **🎬 FIRST-RUN EXCEPTION** *(Right after Phase 9 completes)*

**Before deploying to Railway**, we do one manual end-to-end run on whatever day it is so Saaqib gets to see a real, live trade plan and validate everything works.

- Run: `python src/main.py`
- Confirm: Telegram message arrives with a real pick (or a justified "no trade this week")
- Log: Save this first pick to SQLite like any other
- **Important:** This is still paper-trade. No real money goes in. Saaqib watches it play out over the week and we learn from it.
- **Heads up to Saaqib:** A mid-week first run may correctly return "no trade" because most setups are best on Mondays. That's the bot doing its job, not a failure.

After this one-time run, the bot is **Sunday-only**. No on-demand `/pick` command. No mid-week runs. Discipline > convenience.

---

### **PHASE 10 — Deploy to Cloud (Railway) + Automation** *(Day 7-8, ~1.5 hours)*

**Goal:** The bot runs every Sunday automatically without my laptop being on.

**Substeps:**
10.1. Sign up for Railway.app (free tier)
10.2. Connect GitHub repo
10.3. Set environment variables (API keys) in Railway dashboard
10.4. Configure cron schedule: every Sunday 8 PM Gulf time (= Sunday 4 PM UTC)
10.5. Push code, watch first cloud run succeed
10.6. Confirm Telegram message arrives from cloud-run job

**Done when:** I close my laptop, wait until Sunday, and the message arrives anyway.

---

## 🧪 PHASE 11 — Paper Trading Period *(4 weeks minimum)*

**No code changes during this phase unless something is broken.** We let the bot run, I track results, and we learn.

Weekly review (Claude Code helps):
- Did the pick hit target / stop / neither?
- Was Claude's thesis right? Wrong? Lucky?
- Update a "lessons" file in the repo

After 4 weeks:
- If win rate > 50% AND avg R:R > 1.5 → consider going live with small size
- If results are weak → we tune. Maybe better filters, different prompt, different watchlist.

---

## 🚀 PHASE 12 — Going Live *(Only when we've earned it)*

When (and only when) paper results justify it:
- Start with 1% capital risk per trade (already the default)
- I execute manually — bot never connects to a brokerage
- Bot continues logging everything
- Hard rule: hit the -8% monthly drawdown cap → bot pauses for the month

---

## 🔮 Future Ideas (DON'T BUILD THESE YET — listed so we don't forget)

- Market regime filter (don't trade in a falling SPY environment)
- Sector rotation awareness
- Options-based hedging suggestions
- Weekly performance report auto-generated
- Backtesting framework on historical data
- Multiple pick "portfolio mode" (3 stocks/week)

Park these. We earn the right to add them by getting the v1 right first.

---

## 🧭 How We Stay On Track

- **`PROGRESS.md`** is updated after every phase — date, what we did, gotchas.
- If we hit a wall, we don't hack around it — we pause, discuss, decide.
- I'm the product owner. You (Claude Code) are the engineer. I approve, you build.

Let's go. 🚀
