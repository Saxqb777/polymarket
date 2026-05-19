"""
SwingBot Dashboard — FastAPI web app.

Run locally:
    uvicorn dashboard.main:app --reload --port 8000

Environment variables (add to .env):
    DASHBOARD_PASSWORD=yourpassword   (required — no default)
"""
import asyncio
import importlib
import pathlib
import sys
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.auth import require_auth
from dashboard import migrations, queries, commands
from dashboard.queries import get_user_settings
from dashboard.live_price import get_price_or_none, is_market_open

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


# ── Stub pages (future steps) ─────────────────────────────────────────────────

def _stub_ctx(request: Request) -> dict:
    stats  = queries.get_account_stats()
    active = queries.get_active_position()
    return {"stats": stats, "active": active, "username": "SAAQIB",
            "days_since_blowup": stats["days_since_inception"]}


@app.get("/trades")
async def trades_page(
    request: Request,
    tier: str = "", status: str = "", days: str = "",
    _user: str = Depends(require_auth),
):
    all_trades = queries.get_all_trades_filtered(
        tier   or None,
        status or None,
        int(days) if days else None,
    )
    ctx = _stub_ctx(request)
    ctx.update({
        "trades":        all_trades,
        "filter_tier":   tier,
        "filter_status": status,
        "filter_days":   days,
    })
    return templates.TemplateResponse(request, "trades.html", ctx)


@app.get("/trades/export")
async def trades_export(
    tier: str = "", status: str = "", days: str = "",
    _user: str = Depends(require_auth),
):
    trades = queries.get_all_trades_filtered(
        tier   or None,
        status or None,
        int(days) if days else None,
    )
    lines = ["Date,Symbol,Tier,Confidence,Entry,Stop,Target,RR,Status,ExitPrice,PnL$,PnL%"]
    for t in trades:
        lines.append(",".join(str(t.get(k) or "") for k in [
            "run_date", "symbol", "quality_tier", "confidence",
            "entry_price", "stop_loss", "target_price", "risk_reward",
            "status", "exit_price", "pnl_dollars", "pnl_pct",
        ]))
    return PlainTextResponse(
        "\n".join(lines),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=swingbot_trades.csv"},
    )


@app.get("/insights")
async def insights_page(request: Request, _user: str = Depends(require_auth)):
    ctx = _stub_ctx(request)
    ctx["insights"] = queries.get_insights_data()
    return templates.TemplateResponse(request, "insights.html", ctx)


@app.get("/bot")
async def bot_page(request: Request, _user: str = Depends(require_auth)):
    ctx = _stub_ctx(request)
    ctx["bot"] = queries.get_bot_status()
    return templates.TemplateResponse(request, "bot.html", ctx)


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


# ── Edit-close HTMX endpoints ─────────────────────────────────────────────────

@app.get("/trade/{run_id}/edit-close-form")
async def edit_close_form(run_id: int, request: Request, _user: str = Depends(require_auth)):
    trade = queries.get_trade_by_id(run_id)
    if not trade:
        raise HTTPException(status_code=404)
    return templates.TemplateResponse(request, "partials/edit_close_form.html",
                                      {"trade": trade, "run_id": run_id})


@app.post("/trade/{run_id}/edit-close")
async def post_edit_close(run_id: int, request: Request,
                          exit_price:  float = Form(...),
                          pnl_dollars: float = Form(...),
                          outcome:     str   = Form(...),
                          notes:       str   = Form(""),
                          _user: str = Depends(require_auth)):
    trade = commands.edit_outcome(run_id, exit_price, pnl_dollars, outcome, notes or None)
    return templates.TemplateResponse(request, "partials/action_panel.html",
                                      _trade_ctx(trade, run_id))


# ── Settings page ─────────────────────────────────────────────────────────────

@app.get("/settings")
async def settings_page(request: Request, _user: str = Depends(require_auth)):
    settings = get_user_settings()
    stats    = queries.get_account_stats()
    active   = queries.get_active_position()
    return templates.TemplateResponse(request, "settings.html", {
        "settings":          settings,
        "stats":             stats,
        "active":            active,
        "username":          "SAAQIB",
        "days_since_blowup": stats["days_since_inception"],
        "saved":             False,
    })


@app.post("/settings")
async def post_settings(request: Request,
                        starting_capital: float = Form(...),
                        _user: str = Depends(require_auth)):
    commands.update_settings(starting_capital)
    settings = get_user_settings()
    stats    = queries.get_account_stats()
    active   = queries.get_active_position()
    return templates.TemplateResponse(request, "settings.html", {
        "settings":          settings,
        "stats":             stats,
        "active":            active,
        "username":          "SAAQIB",
        "days_since_blowup": stats["days_since_inception"],
        "saved":             True,
    })


# ── Live price JSON API ───────────────────────────────────────────────────────

@app.get("/api/live-price/{symbol}")
async def api_live_price(symbol: str, _user: str = Depends(require_auth)):
    """Returns live price for an open position symbol only (security guard)."""
    active = queries.get_active_position()
    if not active or (active.get("symbol") or "").upper() != symbol.upper():
        raise HTTPException(status_code=404, detail="No open position for this symbol")
    data = get_price_or_none(symbol.upper())
    if not data:
        raise HTTPException(status_code=503, detail="Price temporarily unavailable")
    return {**data, "market_open": is_market_open()}


# ── Bot manual scan trigger ───────────────────────────────────────────────────

@app.post("/bot/trigger-scan")
async def trigger_scan(request: Request, _user: str = Depends(require_auth)):
    """Run the full bot pipeline once. Blocks until complete, then returns last-run partial."""
    def _run_pipeline():
        # Import lazily to avoid polluting module namespace
        bot_main = importlib.import_module("main")
        bot_main.run_pipeline(dry_run=False)

    await asyncio.to_thread(_run_pipeline)
    bot = queries.get_bot_status()
    return templates.TemplateResponse(request, "partials/bot_last_run.html", {"bot": bot})
