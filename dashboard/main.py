"""
SwingBot Dashboard — FastAPI web app.

Run locally:
    uvicorn dashboard.main:app --reload --port 8000

Environment variables (add to .env):
    DASHBOARD_PASSWORD=yourpassword   (required — no default)
"""
import pathlib
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Request
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from dashboard.auth import require_auth
from dashboard import migrations, queries

_HERE = pathlib.Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    migrations.run()
    yield


app = FastAPI(title="SwingBot Dashboard", docs_url=None, redoc_url=None, lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(_HERE / "static")), name="static")

templates = Jinja2Templates(directory=str(_HERE / "templates"))


# ── Unauthenticated routes ────────────────────────────────────────────────────

@app.get("/health")
async def health():
    """Railway health check — intentionally unauthenticated."""
    return {"status": "ok", "service": "swingbot-dashboard"}


@app.get("/logout", response_class=Response)
async def logout():
    """
    Return a 401 to force the browser to clear its stored Basic Auth credentials.
    After hitting this endpoint the browser will prompt for credentials again.
    """
    return Response(
        content="Logged out — close this tab or navigate back to re-authenticate.",
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="SwingBot Dashboard"'},
    )


# ── Authenticated routes ──────────────────────────────────────────────────────

@app.get("/")
async def home(request: Request, _user: str = Depends(require_auth)):
    stats = queries.get_account_stats()
    active = queries.get_active_position()
    return templates.TemplateResponse(request, "home.html", {
        "stats":            stats,
        "active":           active,
        "username":         "SAAQIB",
        "days_since_blowup": stats["days_since_inception"],
    })
