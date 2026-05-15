# PROGRESS.md — Build Log

> Updated after every working step. Most recent at top.

---

## 📍 Current Status

**Phase:** Dashboard — Step 2 complete (HTTP Basic Auth)
**Next step:** Dashboard Step 3 — database read layer (queries.py)

---

## 📝 Log

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
