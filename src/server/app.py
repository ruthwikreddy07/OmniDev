from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from src.server.routes import router

app = FastAPI(
    title="OmniDev",
    description="Autonomous Agentic Software Engineering Platform",
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# Enable Cross-Origin Resource Sharing (CORS) for external frontend deployments (Vercel, etc.)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)

static_dir = Path(__file__).parent.parent.parent / "static"
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")


def serve_page(filename: str):
    p = static_dir / filename
    if p.exists():
        return FileResponse(str(p))
    return {"message": f"{filename} not found"}


@app.get("/")
async def page_index():
    return serve_page("index.html")


@app.get("/auth")
async def page_auth():
    return serve_page("auth.html")


@app.get("/console")
async def page_console():
    return serve_page("console.html")


@app.get("/workspace")
async def page_workspace():
    return serve_page("workspace.html")


@app.get("/analytics")
async def page_analytics():
    return serve_page("analytics.html")


@app.get("/rules")
async def page_rules():
    return serve_page("rules.html")


@app.get("/integrations")
async def page_integrations():
    return serve_page("integrations.html")


@app.get("/docs")
async def page_docs():
    return serve_page("docs.html")


@app.get("/settings")
async def page_settings():
    return serve_page("settings.html")


@app.get("/health")
async def health():
    return {"status": "ok"}
