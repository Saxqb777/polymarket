# CLAUDE.md — Standing Instructions for This Project

> **Read this file at the start of every session. Then read `PLAN.md`. Then `PROGRESS.md` to see where we are.**

---

## 👤 About Me (Saaqib)

- **I do not code.** I have zero programming background. Treat me as a smart non-technical user.
- I'm building this because I want to swing trade US stocks weekly with discipline, not gut feel.
- I have an Anthropic API budget and I'm fine spending on Claude calls — quality of reasoning matters more than saving pennies.
- I live in Abu Dhabi (Gulf Standard Time, UTC+4). All schedules should respect my timezone.
- I have a day job and an MBA going on. I want this bot to do the thinking so I just follow the plan.

---

## 🎯 The One-Line Goal

**Every Sunday evening (Gulf time), I receive a Telegram message with ONE US stock to swing trade for the upcoming week — including entry zone, stop-loss, target, position size, and the reasoning behind it.**

That's it. Everything we build serves that outcome.

---

## 🧠 How You (Claude Code) Should Work With Me

### Rule 1: Explain like I'm new
- No unexplained jargon. If you say "virtual environment," tell me what it is in one line.
- When you write code, tell me **what it does** in plain English before showing it.
- When I need to run a command, tell me **exactly** which terminal, which folder, what to type.

### Rule 2: One step at a time
- Never dump 5 steps on me at once. Do ONE substep, wait for me to confirm it worked, then move on.
- If you're about to do something that takes more than 2 minutes of my attention, pause and check in.

### Rule 3: Always confirm before destructive or costly actions
Ask me before:
- Installing anything (`pip install`, `npm install`, system packages)
- Running scripts that hit paid APIs
- Pushing to GitHub
- Deploying to cloud
- Deleting files

### Rule 4: Update `PROGRESS.md` after every working step
- Mark what we completed, the date, any gotchas we hit.
- This way if we resume next week, you know exactly where we left off.

### Rule 5: When I hit an error
- Don't just give me a fix — tell me **what went wrong and why** in one sentence first.
- Then give me the fix.
- This helps me learn instead of feeling lost.

### Rule 6: Be opinionated
- I asked you to be creative. If you see a smarter way than what's in `PLAN.md`, say so.
- But don't change the plan silently. Flag it: *"I suggest we do X instead of Y because Z. Okay?"*

### Rule 7: Be honest about risk
- This is a trading bot. It can lose money.
- Never overstate what backtests prove. Never pretend the bot has an edge it hasn't earned through testing.
- If something looks like overfitting or curve-fitting, tell me.

---

## 🛠 Tech Stack (locked in)

| Layer | Tool | Why |
|---|---|---|
| Language | **Python 3.11+** | Easier for beginners than JS; best data libraries |
| LLM | **Anthropic Claude API** (Sonnet for analysis, Haiku for cheap filtering) | I already have API budget |
| Price data | **yfinance** (free) + **Polygon.io free tier** as backup | Free, reliable enough for weekly swings |
| News | **NewsAPI** + **Marketaux** (both free tiers) | News is the BIG edge for this bot — use both |
| Earnings calendar | **Finnhub** free tier | Avoid stocks with earnings this week |
| Alerts | **Telegram Bot API** | Free, instant, on my phone |
| Scheduling | **Railway.app cron** (free tier) | Runs every Sunday automatically |
| Storage | **SQLite** (single file) | No database server needed |
| Version control | **GitHub** | Standard, also enables Railway deploy |

---

## 📂 Project Structure (target)

```
swing-bot/
├── CLAUDE.md              ← you're reading it
├── PLAN.md                ← the full build plan
├── PROGRESS.md            ← running log of what's done
├── README.md              ← human-readable summary
├── .env.example           ← template for API keys (committed)
├── .env                   ← actual keys (NEVER committed)
├── .gitignore
├── requirements.txt       ← Python dependencies
├── config/
│   ├── watchlist.py       ← list of stocks to scan
│   └── settings.py        ← risk rules, position sizing, etc.
├── src/
│   ├── __init__.py
│   ├── main.py            ← entry point, runs the whole flow
│   ├── scanner.py         ← filters watchlist → top 10
│   ├── news.py            ← pulls news + earnings for candidates
│   ├── technicals.py      ← RSI, MAs, support/resistance, etc.
│   ├── analyst.py         ← sends everything to Claude, gets the pick
│   ├── trade_plan.py      ← formats entry/stop/target/sizing
│   ├── telegram_bot.py    ← sends the message
│   └── storage.py         ← saves every pick to SQLite for tracking
├── tests/
│   └── (we'll add as we go)
├── data/
│   └── picks.db           ← SQLite file, gitignored
└── logs/
    └── (gitignored)
```

---

## 💰 Risk Rules (HARD-CODED — don't let me override on impulse)

These are baked into the bot. If I ask you to remove them mid-session, push back and remind me they exist for a reason.

1. **One trade per week. No more.** This is a swing bot, not a day-trade machine.
2. **Skip stocks with earnings in the next 7 days.** Earnings = gap risk.
3. **Minimum risk/reward of 1:1.8.** If the math doesn't work, the bot reports "no trade this week" — and that's a valid output.
4. **Max position size = 5% of stated trading capital.** I'll tell you my capital figure in `config/settings.py`.
5. **Stop-loss is non-negotiable.** Every pick must have one. No "mental stops."
6. **Paper trade for 4 weeks minimum before real money.** Bot logs paper results to SQLite. We review before going live.
7. **Monthly drawdown cap: -8% of trading capital.** If hit, bot pauses for the rest of the month and tells me to review.

---

## 🧪 Quality Bar

- Every module gets a docstring explaining what it does.
- Every API call has error handling — no crashes on a flaky NewsAPI response.
- All secrets in `.env`, never in code.
- Logs everything to `logs/` so we can debug week-to-week.

---

## 🚫 Things NOT to do

- Don't use technical indicators you can't explain to me.
- Don't add features that aren't in `PLAN.md` without flagging first.
- Don't optimize prematurely — get it working end-to-end, then improve.
- Don't connect to a real brokerage. This bot **suggests** trades. I execute manually. Period.

---

## 🗣 First message of every new session

When I start a new Claude Code session, your first reply should be:

> *"Read CLAUDE.md, PLAN.md, and PROGRESS.md. We're currently on Step X. Last session we did Y. Ready to continue with Z — should I proceed?"*

That's the handshake. It tells me you have full context.
