# PROGRESS.md — Build Log

> Updated after every working step. Most recent at top.

---

## 📍 Current Status

**Phase:** Dashboard — Step 6.5 complete (live prices + full stub pages + analytics)
**Next step:** Step 7 — TBD (Telegram alerts? Mobile polish? Deploy to Railway?)

---

## 📝 Log

### 2026-05-20 — Dashboard Step 6.5: Live prices + bot/trades/insights pages

**Live Prices (Part A)**
- `dashboard/live_price.py`: Polygon primary + yfinance fallback, 30s cache, is_market_open(), get_price_or_none()
- `/api/live-price/{symbol}` JSON endpoint, security-guarded to open positions only
- Home page polls every 60s (pauses when tab hidden); updates LAST, Live P&L, progress rail dot, status bar POS %, hero equity, breakdown sub-line; 300ms mint/red flash on price change
- Status bar NEXT SCAN now a live countdown ticking every minute (client-side JS)

**Bot Status Page — /bot (Part B)**
- `queries.get_bot_status()`: last run info, next Sunday 16:00 UTC, runtime env, version
- `templates/bot.html`: ONLINE indicator, 3-section layout (Last Run / Next Scan / Config), countdown ticking per second
- `⚡ MANUAL SCAN NOW` amber button with confirmation dialog → POST /bot/trigger-scan → runs full pipeline → HTMX swaps Last Run section with updated data + ✓ SCAN COMPLETE
- `partials/bot_last_run.html`: HTMX partial for scan result swap

**Trades History Page — /trades (Part C)**
- `queries.get_all_trades_filtered()`: server-side tier + days filter, status filter in Python
- `templates/trades.html`: Tier/Status/Days dropdowns (auto-submit), ticker search (client-side), clickable rows, ↓ CSV export
- `GET /trades/export`: returns filtered trades as downloadable CSV

**Insights Page — /insights (Part D)**
- `queries.get_insights_data()`: win_rate_by_tier, win_rate_by_confidence, R:R scatter, 84-day calendar_data, 30-day drawdown_curve
- `templates/insights.html`: graceful empty state; tier/confidence bars, R:R scatter (min 3 trades), 84-day calendar heatmap (CSS grid, mint/red gradient), equity+drawdown dual-axis chart

**Settings + Edit-Close + Equity Math (Step 6.5 Part 1 — shipped earlier)**
- `user_settings` SQLite table seeded at startup
- /settings page: set starting capital, saves to DB
- Edit-close HTMX form on trade detail State C
- account_value = starting + closed_pnl; cash_position = account_value − open_cost
- Hero breakdown: "Cash $0.12 · Open $269.88 in MCHP"

### 2026-05-20 — Dashboard Step 6: Trade detail + action panel
- `dashboard/commands.py`: mark_taken, mark_skipped, log_outcome, reopen_trade, unskip_trade
- `templates/trade_detail.html`: full detail page (bot levels, rationale, no-trade reason)
- `partials/action_panel.html`: 4-state HTMX machine (pending→open→closed→skipped), all transitions wired
- `partials/take_form.html`, `skip_form.html`, `close_form.html`: inline forms
- Fixed: home page showing actual_entry/shares; stub pages for nav links

### 2026-05-19 — Dashboard Step 5: Full home dashboard
- `templates/home.html`: hero (account value + delta pill), 4-col stats grid (Win Rate / Avg R:R / Best Week / You vs Bot), active position card (pos-cells, progress rail, thesis), 160px equity curve (Chart.js v4), trade log table
- Fixed: TemplateResponse new Starlette signature (request as first arg); CSS specificity on MTD/POS colors; win rate / best week / you-vs-bot display logic; python-multipart dependency

### 2026-05-19 — Dashboard Step 4: Base template + design system
- `templates/base.html`: sticky status bar (LIVE/ACCT/MTD/POS/NEXT SCAN), header + nav, CDN fonts (Inter + JetBrains Mono), Chart.js v4, HTMX 1.9.10
- `static/dashboard.css`: Bloomberg Terminal dark mode (--bg #0a0a0a, --mint #00d4aa, --red #ff4545), 800 lines of design tokens + component styles

### 2026-05-19 — Dashboard Step 3: Database read layer
- `dashboard/migrations.py`, `dashboard/queries.py`, wired into FastAPI lifespan
- `src/database.py`: quality fields added; `main.py`: passes them from analyst result

### 2026-05-15 — Dashboard Steps 1–2: Skeleton + Auth
- FastAPI skeleton, HTTP Basic Auth, /health unauthenticated

### 2026-05-15 — Bot complete and running live
- All 10 bot modules, 101-ticker watchlist, Telegram working, R:R floor 2.5


### 2026-05-15 — Dashboard Step 2: HTTP Basic Auth
- `dashboard/auth.py`: HTTPBasic dependency, username="saaqib", password from DASHBOARD_PASSWORD env var
- Fails loudly at startup if DASHBOARD_PASSWORD is missing (no silent defaults)
- `GET /` gated — wrong credentials → 401 + browser auth prompt
- `GET /health` unauthenticated (Railway health checks need this open)
- `GET /logout` returns 401 to force browser to clear stored credentials
- Added DASHBOARD_PASSWORD=changeme to .env.example
- Tested: correct creds → 200, wrong creds → 401, wrong user → 401

### 2026-05-15 — Dashboard Step 1: FastAPI skeleton
- Created `dashboard/` folder with `__init__.py` and `main.py`
- Two routes: `GET /` (HTML hello world) and `GET /health` (JSON)
- Added `fastapi>=0.111.0` and `uvicorn[standard]>=0.29.0` to requirements.txt
- Run locally: `uvicorn dashboard.main:app --reload --port 8000`

### 2026-05-15 — Bot complete and running live
- All 10 bot modules built and pushed
- Watchlist at 101 tickers with tiered price filter ($8-$175 hard, $10-$150 green)
- Live Telegram messages working (≈ escaping fix applied)
- R:R floor 2.5, PREMIUM tier at 3.0+, graduated target move search
- Buffer zone enforcement: $150-$175 picks require PREMIUM setup

### [Date TBD] — Project kickoff
- Created repo `swing-bot`
- Added `CLAUDE.md`, `PLAN.md`, `PROGRESS.md`
- Ready for Phase 1
