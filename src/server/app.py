import os
import time
import logging
import html as html_lib
from collections import defaultdict, deque
from pathlib import Path
from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from src.server.routes import router
from src.server.database import get_db, get_db_engine_name

logger = logging.getLogger("omnidev")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")

app = FastAPI(
    title="OmniDev Backend API",
    description="Autonomous Agentic Software Engineering Backend Gateway",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
_allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

# Enable Cross-Origin Resource Sharing (CORS) for Vercel frontend & local dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$|^https://[a-zA-Z0-9-]+\.vercel\.app$",
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "HEAD"],
    allow_headers=["*"],
)


_RATE_BUCKETS: dict[str, deque[float]] = defaultdict(deque)


@app.middleware("http")
async def rate_limit_and_security_headers(request: Request, call_next):
    if request.url.path.startswith("/api/"):
        limit = int(os.environ.get("RATE_LIMIT_PER_MIN", "120"))
        if limit > 0:
            client_ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            bucket = _RATE_BUCKETS[client_ip]
            while bucket and now - bucket[0] > 60.0:
                bucket.popleft()
            if len(bucket) >= limit:
                return JSONResponse({"detail": "Rate limit exceeded. Please retry shortly."}, status_code=429)
            bucket.append(now)

    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(router)

_STATIC_DIR = Path(__file__).resolve().parent.parent.parent / "static"
if _STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


def _check_backend_health() -> dict:
    db_engine = get_db_engine_name()
    db_ok = True
    db_error = ""
    try:
        conn = get_db()
        try:
            cur = conn.cursor()
            cur.execute("SELECT 1")
            cur.fetchone()
        finally:
            conn.close()
    except Exception as e:
        db_ok = False
        db_error = str(e)

    overall_ok = db_ok
    return {
        "status": "operational" if overall_ok else "degraded",
        "api": "online",
        "db_engine": db_engine,
        "db_status": "connected" if db_ok else "error",
        "db_error": db_error,
        "websocket": "active",
        "groq_fallback": "configured" if os.environ.get("GROQ_API_KEY", "").strip() else "per-user-header",
    }


@app.get("/status", response_class=HTMLResponse)
async def backend_status_page():
    h = _check_backend_health()
    is_ok = h["status"] == "operational"
    badge_bg = "rgba(16,185,129,0.14)" if is_ok else "rgba(239,68,68,0.14)"
    badge_border = "#10b981" if is_ok else "#ef4444"
    badge_color = "#34d399" if is_ok else "#f87171"
    status_title = "All Systems Active & Operational" if is_ok else "Backend Issue Reported"
    db_badge_color = "#34d399" if h["db_status"] == "connected" else "#f87171"
    issue_block = (
        f'<div class="issue-box"><strong>Reported Issue:</strong> {html_lib.escape(h["db_error"])}</div>'
        if h["db_error"] else ""
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>OmniDev Backend — Status</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #070a12; color: #e2e8f0; min-height: 100vh;
    display: flex; align-items: center; justify-content: center; padding: 24px;
  }}
  .card {{
    width: 100%; max-width: 560px; background: #0d1322;
    border: 1px solid rgba(255,255,255,0.08); border-radius: 16px;
    padding: 32px; box-shadow: 0 24px 60px rgba(0,0,0,0.65);
  }}
  .header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 22px; gap: 12px; flex-wrap: wrap; }}
  .brand {{ font-size: 20px; font-weight: 800; color: #fff; letter-spacing: -0.02em; }}
  .sub {{ font-size: 12.5px; color: #94a3b8; margin-top: 2px; }}
  .pill {{
    display: inline-flex; align-items: center; gap: 8px; padding: 6px 14px;
    border-radius: 999px; font-size: 12.5px; font-weight: 700;
    background: {badge_bg}; border: 1px solid {badge_border}; color: {badge_color};
  }}
  .dot {{ width: 8px; height: 8px; border-radius: 50%; background: {badge_color}; }}
  .rows {{ display: flex; flex-direction: column; gap: 10px; margin-bottom: 20px; }}
  .row {{
    display: flex; align-items: center; justify-content: space-between;
    background: #121a2e; border: 1px solid rgba(255,255,255,0.06);
    border-radius: 10px; padding: 12px 16px; font-size: 13.5px;
  }}
  .label {{ color: #94a3b8; font-weight: 600; }}
  .val {{ font-family: monospace; font-weight: 700; color: #fff; }}
  .issue-box {{
    background: rgba(239,68,68,0.1); border: 1px solid rgba(239,68,68,0.4);
    color: #fca5a5; padding: 12px 14px; border-radius: 10px;
    font-size: 12.5px; font-family: monospace; margin-bottom: 18px; word-break: break-word;
  }}
  .footer {{ display: flex; gap: 12px; flex-wrap: wrap; font-size: 12.5px; color: #64748b; border-top: 1px solid rgba(255,255,255,0.07); padding-top: 16px; }}
  a {{ color: #818cf8; text-decoration: none; font-weight: 600; }}
  a:hover {{ text-decoration: underline; }}
</style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div>
        <div class="brand">OmniDev Backend API</div>
        <div class="sub">API &amp; WebSocket Gateway (Connect via Vercel Frontend)</div>
      </div>
      <div class="pill"><span class="dot"></span>{status_title}</div>
    </div>
    {issue_block}
    <div class="rows">
      <div class="row"><span class="label">FastAPI Server</span><span class="val" style="color:#34d399;">Online</span></div>
      <div class="row"><span class="label">Database ({h["db_engine"]})</span><span class="val" style="color:{db_badge_color};">{h["db_status"].upper()}</span></div>
      <div class="row"><span class="label">WebSocket Gateway</span><span class="val" style="color:#34d399;">Active (/ws/{{job_id}})</span></div>
      <div class="row"><span class="label">LLM Key Mode</span><span class="val">{h["groq_fallback"]}</span></div>
    </div>
    <div class="footer">
      <a href="/api/docs">Swagger API Docs ↗</a>
      <span>•</span>
      <a href="/health">Health JSON ↗</a>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=html, status_code=200 if is_ok else 503)


@app.get("/health")
async def health():
    h = _check_backend_health()
    code = 200 if h["status"] == "operational" else 503
    return JSONResponse(content=h, status_code=code)


@app.get("/", include_in_schema=False)
async def serve_index():
    index_file = _STATIC_DIR / "index.html"
    if index_file.is_file():
        return FileResponse(str(index_file))
    return await backend_status_page()


@app.get("/robots.txt", include_in_schema=False)
async def serve_robots():
    f = _STATIC_DIR / "robots.txt"
    if f.is_file():
        return FileResponse(str(f), media_type="text/plain")
    return JSONResponse({"detail": "Not found"}, status_code=404)


@app.get("/sitemap.xml", include_in_schema=False)
async def serve_sitemap():
    f = _STATIC_DIR / "sitemap.xml"
    if f.is_file():
        return FileResponse(str(f), media_type="application/xml")
    return JSONResponse({"detail": "Not found"}, status_code=404)


for _page in ("console", "workspace", "analytics", "integrations", "rules", "docs", "settings", "auth"):
    def _make_page_handler(page_name: str):
        async def _handler():
            target = _STATIC_DIR / f"{page_name}.html"
            if target.is_file():
                return FileResponse(str(target))
            return JSONResponse({"detail": "Not found"}, status_code=404)
        return _handler
    app.add_api_route(f"/{_page}", _make_page_handler(_page), methods=["GET"], include_in_schema=False)
