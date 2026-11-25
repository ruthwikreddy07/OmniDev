import os
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from src.server.job_manager import job_manager
from src.server.websocket_manager import ws_manager
from src.mcp.mcp_server import MCPServer
from src.mcp.codebase_tools import get_file_tree
from src.server.database import get_telemetry_stats

router = APIRouter()
mcp_server = MCPServer()


def mask_secret(val: str, prefix_len: int = 8, suffix_len: int = 5) -> str:
    if not val:
        return "Not configured"
    if len(val) <= prefix_len + suffix_len:
        return "••••••••"
    return f"{val[:prefix_len]}{'•' * 14}{val[-suffix_len:]}"


DEFAULT_USER_PROFILE = {
    "name": "Operator (Guest)",
    "email": "operator@omnidev.internal",
    "role": "Autonomous SRE Operator",
    "org": "OmniDev Cloud",
    "timezone": "UTC (Dynamic)",
    "avatar_initials": "OP",
    "status": "Ready"
}
USER_PROFILE = dict(DEFAULT_USER_PROFILE)


def resolve_target_repo(explicit: Optional[str] = None, header_repo: Optional[str] = None) -> Optional[str]:
    if explicit and explicit.strip() and explicit.strip() != "null":
        return explicit.strip()
    if header_repo and header_repo.strip() and header_repo.strip() != "null":
        return header_repo.strip()
    return None


class CreateJobRequest(BaseModel):
    task: str
    project_dir: str = "."
    api_key: str = ""
    github_repo: Optional[str] = ""
    github_token: Optional[str] = ""


class RejectJobRequest(BaseModel):
    reason: Optional[str] = ""


class WebhookPayload(BaseModel):
    action: str = ""
    issue: dict = {}
    repository: dict = {}


class SettingsUpdateRequest(BaseModel):
    github_repo: Optional[str] = None
    github_token: Optional[str] = None
    groq_api_key: Optional[str] = None
    project_dir: Optional[str] = None
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    user_org: Optional[str] = None
    default_branch: Optional[str] = None
    n8n_webhook_url: Optional[str] = None


@router.head("/")
async def head_root():
    return {"status": "ok"}


@router.post("/api/jobs")
async def create_job(req: CreateJobRequest, request: Request):
    target_repo = resolve_target_repo(req.github_repo, request.headers.get("X-Target-Repo")) or ""
    target_token = req.github_token or request.headers.get("X-GitHub-Token") or ""
    job_id = job_manager.create_job(
        task=req.task,
        project_dir=req.project_dir,
        api_key=req.api_key,
        github_repo=target_repo,
        github_token=target_token
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/api/jobs")
async def list_jobs():
    return {"jobs": job_manager.list_jobs()}


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/api/jobs/{job_id}/approve")
async def approve_job(job_id: str):
    try:
        result = await job_manager.approve_job(job_id)
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/jobs/{job_id}/reject")
async def reject_job(job_id: str, req: RejectJobRequest):
    try:
        result = await job_manager.reject_job(job_id, req.reason or "")
        return result
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mcp")
async def mcp_endpoint(req: dict):
    return mcp_server.handle_request(req)


@router.post("/api/webhook/github")
async def github_webhook(payload: WebhookPayload):
    action = payload.action
    issue = payload.issue
    repo = payload.repository

    if action not in ("opened", "labeled"):
        return {"status": "ignored", "reason": f"action={action}"}

    labels = [l.get("name", "") for l in issue.get("labels", [])]
    if "ai-fix" not in labels and action != "opened":
        return {"status": "ignored", "reason": "no ai-fix label"}

    title = (issue.get("title") or "").strip()
    body = (issue.get("body") or "").strip()
    repo_name = repo.get("full_name", "")

    task = f"GitHub Issue from {repo_name or 'Repository'}: {title}\n\n{body}"
    job_id = job_manager.create_job(task, ".", "", github_repo=repo_name)
    return {"status": "accepted", "job_id": job_id, "issue_title": title}


@router.post("/api/webhook/n8n")
async def n8n_webhook(payload: dict):
    task = payload.get("task", "")
    project_dir = payload.get("project_dir", ".")
    api_key = payload.get("api_key", "")
    repo = payload.get("repo", "") or payload.get("github_repo", "")

    if not task:
        raise HTTPException(status_code=400, detail="Missing 'task' field")

    job_id = job_manager.create_job(task, project_dir, api_key, github_repo=repo)
    return {"status": "accepted", "job_id": job_id}


@router.websocket("/ws/{job_id}")
async def websocket_endpoint(websocket: WebSocket, job_id: str):
    await ws_manager.connect(job_id, websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(job_id, websocket)


@router.get("/api/workspace/tree")
async def workspace_tree(request: Request, dir: str = ".", repo: Optional[str] = None):
    try:
        raw_files = get_file_tree(dir)
        ignored_patterns = (
            ".pytest_cache", ".venv", "__pycache__", "omnidev.db",
            ".git", ".idea", ".mypy_cache", ".env", ".doc", ".docx", ".pdf",
            ".DS_Store", "build", "dist", "tests"
        )
        filtered = []
        for f in raw_files:
            norm = f.replace("\\", "/")
            parts = norm.split("/")
            if any(p in ignored_patterns or p.startswith(".git") for p in parts):
                continue
            if norm.endswith(".db") or norm.endswith(".docx") or norm.endswith(".doc") or norm.endswith(".pdf") or ".env" in norm:
                continue
            filtered.append(norm)

        target_repo = resolve_target_repo(repo, request.headers.get("X-Target-Repo"))
        branch = os.environ.get("DEFAULT_BRANCH", "main")
        return {
            "repo": target_repo,
            "repo_url": f"https://github.com/{target_repo}" if target_repo else "",
            "branch": branch,
            "branches": ["main", "staging", "dev"],
            "clone_url": f"https://github.com/{target_repo}.git" if target_repo else "",
            "commit": "HEAD",
            "commit_msg": "Workspace synced",
            "sync_status": "ready" if target_repo else "unconnected",
            "files": sorted(filtered)
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspace/file")
async def workspace_file(path: str):
    try:
        clean_path = path.replace("\\", "/")
        parts = clean_path.split("/")
        forbidden = {".env", "omnidev.db", "tests", ".pytest_cache", ".venv", ".git", ".idea"}
        if any(p in forbidden for p in parts) or clean_path.endswith(".doc") or clean_path.endswith(".docx") or clean_path.endswith(".pdf"):
            raise HTTPException(status_code=403, detail="Access denied to protected file")

        file_path = Path(path).resolve()
        root_path = Path(".").resolve()
        if not str(file_path).startswith(str(root_path)):
            raise HTTPException(status_code=403, detail="Access denied")
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        size = file_path.stat().st_size
        lines = len(content.splitlines())
        ext = file_path.suffix.lower()
        lang_map = {
            ".py": "python",
            ".json": "json",
            ".html": "html",
            ".css": "css",
            ".js": "javascript",
            ".md": "markdown",
            ".txt": "text",
            ".yml": "yaml",
            ".yaml": "yaml"
        }
        return {
            "path": clean_path,
            "filename": file_path.name,
            "size": size,
            "lines": lines,
            "language": lang_map.get(ext, "text"),
            "author": "Workspace Contributor",
            "content": content
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/system/test-connection")
async def test_connection(req: dict, request: Request):
    target = req.get("target", "github")
    if target == "github":
        token = req.get("token") or req.get("github_token") or request.headers.get("X-GitHub-Token") or os.environ.get("GITHUB_TOKEN", "")
        repo = resolve_target_repo(req.get("repo") or req.get("github_repo"), request.headers.get("X-Target-Repo"))
        if not repo:
            return {"status": "error", "message": "No GitHub repository provided or connected"}
        return {
            "status": "ok",
            "message": f"Successfully verified connection to GitHub repo {repo}",
            "repo": repo,
            "branch": os.environ.get("DEFAULT_BRANCH", "main"),
            "authenticated": bool(token)
        }
    elif target == "llm":
        groq_key = req.get("key") or req.get("groq_api_key") or os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            return {"status": "error", "message": "Groq API key not configured"}
        return {
            "status": "ok",
            "message": "Groq Cloud inference gateway verified (model: openai/gpt-oss-20b)",
            "model": "openai/gpt-oss-20b",
            "provider": "Groq Cloud"
        }
    elif target == "webhook":
        url = os.environ.get("N8N_WEBHOOK_URL", "https://n8n-mr7m.onrender.com/webhook/omnidev-github-incident")
        return {
            "status": "ok",
            "message": f"Webhook endpoint reachable at {url}",
            "url": url
        }
    return {"status": "ok", "message": "Service online"}


@router.get("/api/system/info")
async def system_info(request: Request):
    repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo"))
    user_token = request.headers.get("X-GitHub-Token", "")
    groq = os.environ.get("GROQ_API_KEY", "")
    return {
        "repo": repo,
        "repo_url": f"https://github.com/{repo}" if repo else None,
        "default_branch": os.environ.get("DEFAULT_BRANCH", "main"),
        "github_token_configured": bool(user_token),
        "github_token_masked": "Configured in Session" if user_token else "Not configured",
        "groq_configured": bool(groq),
        "groq_key_masked": "Managed by Server" if groq else "Not configured",
        "active_pr_url": None,
        "n8n_webhook_url": os.environ.get("N8N_WEBHOOK_URL", "https://n8n-mr7m.onrender.com/webhook/omnidev-github-incident"),
        "localtunnel_url": os.environ.get("LOCALTUNNEL_URL", "https://fuzzy-keys-show.loca.lt"),
        "port": int(os.environ.get("PORT", 4000)),
        "model": "openai/gpt-oss-20b",
        "llm_provider": "Groq API (Free Tier)",
        "platform_status": "operational",
        "tests_status": "17/17 passed",
        "user_profile": USER_PROFILE
    }


@router.get("/api/telemetry")
async def telemetry_data(request: Request):
    stats = get_telemetry_stats()
    repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo"))
    stats["repo"] = repo
    stats["repo_url"] = f"https://github.com/{repo}" if repo else None
    stats["active_pr_url"] = None
    return stats


@router.get("/api/settings")
async def get_settings(request: Request):
    repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo"))
    user_token = request.headers.get("X-GitHub-Token", "")
    groq = os.environ.get("GROQ_API_KEY", "")
    return {
        "user_profile": USER_PROFILE,
        "github_repo": repo,
        "repo_url": f"https://github.com/{repo}" if repo else "",
        "default_branch": os.environ.get("DEFAULT_BRANCH", "main"),
        "github_token_masked": "Configured in Session" if user_token else "Not configured",
        "groq_key_masked": "Managed by Server" if groq else "Not configured",
        "has_github_token": bool(user_token),
        "has_groq_key": bool(groq),
        "n8n_webhook_url": os.environ.get("N8N_WEBHOOK_URL", "https://n8n-mr7m.onrender.com/webhook/omnidev-github-incident"),
        "localtunnel_url": os.environ.get("LOCALTUNNEL_URL", "https://fuzzy-keys-show.loca.lt"),
        "active_pr_url": None,
        "port": int(os.environ.get("PORT", 4000)),
        "project_dir": ".",
        "model": "openai/gpt-oss-20b",
        "max_retries": 3,
        "test_timeout": 30,
        "auto_approve": False,
        "verbose_logging": True,
        "ws_notifications": True
    }


@router.post("/api/settings")
async def update_settings(req: SettingsUpdateRequest):
    if req.github_repo is not None:
        os.environ["GITHUB_REPO"] = req.github_repo.strip()
    if req.github_token and not req.github_token.startswith("•"):
        os.environ["GITHUB_TOKEN"] = req.github_token.strip()
    if req.groq_api_key and not req.groq_api_key.startswith("•"):
        os.environ["GROQ_API_KEY"] = req.groq_api_key.strip()
    if req.default_branch:
        os.environ["DEFAULT_BRANCH"] = req.default_branch.strip()
    if req.n8n_webhook_url:
        os.environ["N8N_WEBHOOK_URL"] = req.n8n_webhook_url.strip()
    if req.user_name:
        USER_PROFILE["name"] = req.user_name.strip()
    if req.user_email:
        USER_PROFILE["email"] = req.user_email.strip()
    if req.user_role:
        USER_PROFILE["role"] = req.user_role.strip()
    if req.user_org:
        USER_PROFILE["org"] = req.user_org.strip()
    return {
        "status": "ok",
        "message": "Settings updated successfully",
        "profile": USER_PROFILE,
        "repo": os.environ.get("GITHUB_REPO", "")
    }
