"""
SwingBot Dashboard — FastAPI web app.

Run locally:
    uvicorn dashboard.main:app --reload --port 8000

Environment variables (add to .env):
    DASHBOARD_PASSWORD=yourpassword   (required — no default)
"""
from fastapi import Depends, FastAPI
from fastapi.responses import HTMLResponse, Response

from dashboard.auth import require_auth

app = FastAPI(title="SwingBot Dashboard", docs_url=None, redoc_url=None)


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

@app.get("/", response_class=HTMLResponse)
async def home(_user: str = Depends(require_auth)):
    return f"""
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SwingBot Dashboard</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: system-ui, -apple-system, sans-serif;
      background: #f8fafc;
      color: #1e293b;
    }}
    header {{
      background: #0f172a;
      color: #f1f5f9;
      padding: 14px 24px;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }}
    header h1 {{ font-size: 1.1rem; font-weight: 700; letter-spacing: -0.01em; }}
    header a  {{ color: #94a3b8; font-size: 0.8rem; text-decoration: none; }}
    header a:hover {{ color: #f1f5f9; }}
    main {{
      max-width: 680px;
      margin: 48px auto;
      padding: 0 20px;
    }}
    .card {{
      background: #fff;
      border: 1px solid #e2e8f0;
      border-radius: 12px;
      padding: 28px;
    }}
    .tag {{
      display: inline-block;
      background: #d1fae5;
      color: #065f46;
      padding: 2px 10px;
      border-radius: 99px;
      font-size: 0.75rem;
      font-weight: 700;
      margin-bottom: 16px;
    }}
    h2   {{ font-size: 1.5rem; margin-bottom: 8px; }}
    p    {{ color: #64748b; line-height: 1.6; }}
    code {{ background: #f1f5f9; padding: 2px 6px; border-radius: 4px; font-size: 0.85em; }}
    .routes {{ margin-top: 20px; font-size: 0.85rem; color: #94a3b8; }}
    .routes code {{ margin-right: 8px; }}
  </style>
</head>
<body>
  <header>
    <h1>📈 SwingBot</h1>
    <a href="/logout">Logout</a>
  </header>
  <main>
    <div class="card">
      <div class="tag">Step 2 — auth working</div>
      <h2>Welcome, {_user}</h2>
      <p>You're authenticated. Database read layer and trade history come next.</p>
      <div class="routes">
        Routes so far: &nbsp;
        <code>GET /</code>
        <code>GET /health</code>
        <code>GET /logout</code>
      </div>
    </div>
  </main>
</body>
</html>
"""
