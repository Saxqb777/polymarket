"""
SwingBot Dashboard — FastAPI web app.

Run locally:
    uvicorn dashboard.main:app --reload --port 8000

Environment variables (add to .env):
    DASHBOARD_PASSWORD=yourpassword   (required in later steps)
"""
from fastapi import FastAPI
from fastapi.responses import HTMLResponse

app = FastAPI(title="SwingBot Dashboard", docs_url=None, redoc_url=None)


@app.get("/", response_class=HTMLResponse)
async def home():
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SwingBot Dashboard</title>
  <style>
    body { font-family: system-ui, sans-serif; max-width: 600px; margin: 60px auto; padding: 0 20px; color: #1a1a1a; }
    h1   { font-size: 2rem; margin-bottom: 0.25rem; }
    p    { color: #555; }
    .tag { display: inline-block; background: #d1fae5; color: #065f46; padding: 2px 10px; border-radius: 99px; font-size: 0.8rem; font-weight: 600; }
  </style>
</head>
<body>
  <h1>📈 SwingBot Dashboard</h1>
  <p><span class="tag">Step 1 — skeleton</span></p>
  <p>Server is running. Auth, database, and trade views come next.</p>
  <hr>
  <p style="font-size:0.85rem;color:#999">Routes so far: <code>GET /</code> &nbsp;·&nbsp; <code>GET /health</code></p>
</body>
</html>
"""


@app.get("/health")
async def health():
    return {"status": "ok", "service": "swingbot-dashboard"}
