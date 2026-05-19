"""
SwingBot Dashboard — FastAPI web app.

Run locally:
    uvicorn dashboard.main:app --reload --port 8000

Environment variables (add to .env):
    DASHBOARD_PASSWORD=yourpassword   (required — no default)
"""
import pathlib
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.auth import require_auth
from dashboard import migrations, queries, commands

_HERE = pathlib.Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))
import config as _config


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrations.run()
    yield


app = FastAPI(title="SwingBot Dashboard", docs_url=None, redoc_url=None, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

templates = Jinja2Templates(directory=str(_HERE / "templates"))


# ── Helpers ───────────────────────────────────────────────────────────────────

def _trade_state(trade: dict) -> str:
    """Derive the action-panel state from a trade row."""
    if trade.get("outcome") is not None:
        return "closed"
    if trade.get("taken") == 1:
        return "open"
    if trade.get("taken") == 0:
        return "skipped"
    return "pending"


def _trade_ctx(trade: dict, run_id: int) -> dict:
    """Context dict shared by all action-panel partial renders."""
    return {
        "trade":       trade,
        "run_id":      run_id,
        "trade_state": _trade_state(trade),
    }


# ── Unauthenticated routes ────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Railway health check — intentionally unauthenticated."""
    return {"status": "ok", "service": "swingbot-dashboard"}


@app.get("/logout", response_class=Response)
async def logout():
    return Response(
        content="Logged out — close this tab or navigate back to re-authenticate.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="SwingBot Dashboard"'},
    )


# ── Home ──────────────────────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request, _user: str = Depends(require_auth)):
    stats         = queries.get_account_stats()
    active        = queries.get_active_position()
    equity_curve  = queries.get_equity_curve(30)
    recent_trades = queries.get_recent_trades(10)
    active_company = (
        _config.SYMBOL_TO_COMPANY.get(active["symbol"], active["symbol"])
        if active else None
    )
    return templates.TemplateResponse(request, "home.html", {
        "stats":             stats,
        "active":            active,
        "active_company":    active_company,
        "equity_curve":      equity_curve,
        "recent_trades":     recent_trades,
        "username":          "SAAQIB",
        "days_since_blowup": stats["days_since_inception"],
    })


# ── Trade detail ──────────────────────────────────────────────────────────────

@app.get("/trade/{run_id}")
async def trade_detail(run_id: int, request: Request, _user: str = Depends(require_auth)):
    trade = queries.get_trade_by_id(run_id)
    if not trade:
        raise HTTPException(status_code=404, detail="Trade not found")
    symbol = trade.get("symbol") or ""
    company_name = _config.SYMBOL_TO_COMPANY.get(symbol, symbol)
    # Status bar needs stats + active
    stats  = queries.get_account_stats()
    active = queries.get_active_position()
    return templates.TemplateResponse(request, "trade_detail.html", {
        "trade":             trade,
        "run_id":            run_id,
        "company_name":      company_name,
        "trade_state":       _trade_state(trade),
        "stats":             stats,
        "active":            active,
        "username":          "SAAQIB",
        "days_since_blowup": stats["days_since_inception"],
    })


# ── Action panel HTMX endpoints ───────────────────────────────────────────────

@app.get("/trade/{run_id}/take-form")
async def take_form(run_id: int, request: Request, _user: str = Depends(require_auth)):
    trade = queries.get_trade_by_id(run_id)
    if not trade:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "partials/take_form.html",
                                      {"trade": trade, "run_id": run_id})


@app.get("/trade/{run_id}/skip-form")
async def skip_form(run_id: int, request: Request, _user: str = Depends(require_auth)):
    trade = queries.get_trade_by_id(run_id)
    if not trade:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "partials/skip_form.html",
                                      {"trade": trade, "run_id": run_id})


@app.get("/trade/{run_id}/close-form")
async def close_form(run_id: int, request: Request, _user: str = Depends(require_auth)):
    trade = queries.get_trade_by_id(run_id)
    if not trade:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "partials/close_form.html",
                                      {"trade": trade, "run_id": run_id})


# ── Action POSTs ──────────────────────────────────────────────────────────────

@app.post("/trade/{run_id}/take")
async def post_take(run_id: int, request: Request,
                    actual_entry:  float = Form(...),
                    actual_shares: float = Form(...),
                    notes: str = Form(""),
                    _user: str = Depends(require_auth)):
    trade = commands.mark_taken(run_id, actual_entry, actual_shares, notes or None)
    return templates.TemplateResponse(request, "partials/action_panel.html",
                                      _trade_ctx(trade, run_id))


@app.post("/trade/{run_id}/skip")
async def post_skip(run_id: int, request: Request,
                    skip_reason: str = Form(""),
                    _user: str = Depends(require_auth)):
    trade = commands.mark_skipped(run_id, skip_reason or None)
    return templates.TemplateResponse(request, "partials/action_panel.html",
                                      _trade_ctx(trade, run_id))


@app.post("/trade/{run_id}/close")
async def post_close(run_id: int, request: Request,
                     exit_price:    float = Form(...),
                     outcome:       str   = Form(...),
                     closed_method: str   = Form("manual"),
                     notes:         str   = Form(""),
                     _user: str = Depends(require_auth)):
    trade = commands.log_outcome(run_id, exit_price, outcome, closed_method, notes or None)
    return templates.TemplateResponse(request, "partials/action_panel.html",
                                      _trade_ctx(trade, run_id))


@app.post("/trade/{run_id}/reopen")
async def post_reopen(run_id: int, request: Request,
                      _user: str = Depends(require_auth)):
    trade = commands.reopen_trade(run_id)
    return templates.TemplateResponse(request, "partials/action_panel.html",
                                      _trade_ctx(trade, run_id))


@app.post("/trade/{run_id}/unskip")
async def post_unskip(run_id: int, request: Request,
                      _user: str = Depends(require_auth)):
    trade = commands.unskip_trade(run_id)
    return templates.TemplateResponse(request, "partials/action_panel.html",
                                      _trade_ctx(trade, run_id))
