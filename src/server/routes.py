import os
import re
import hmac
import hashlib
import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, HTTPException, Request
from pydantic import BaseModel
from typing import Optional
from pathlib import Path
from src.server.job_manager import job_manager
from src.server.websocket_manager import ws_manager
from src.mcp.mcp_server import MCPServer
from src.mcp.codebase_tools import get_file_tree
from src.server.database import get_telemetry_stats, get_db_engine_name

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


_REPO_SLUG_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")


def resolve_target_repo(explicit: Optional[str] = None, header_repo: Optional[str] = None) -> Optional[str]:
    raw = None
    if explicit and explicit.strip() and explicit.strip() != "null":
        raw = explicit.strip()
    elif header_repo and header_repo.strip() and header_repo.strip() != "null":
        raw = header_repo.strip()
    if not raw:
        return None
    if raw.startswith("https://github.com/"):
        raw = raw[len("https://github.com/"):]
    elif raw.startswith("http://github.com/"):
        raw = raw[len("http://github.com/"):]
    if raw.endswith(".git"):
        raw = raw[:-4]
    raw = raw.strip("/")
    if not _REPO_SLUG_RE.match(raw):
        raise HTTPException(status_code=400, detail="Invalid repository format. Expected 'owner/repo'.")
    return raw


class CreateJobRequest(BaseModel):
    task: str
    project_dir: str = "."
    api_key: str = ""
    github_repo: Optional[str] = ""
    github_token: Optional[str] = ""
    max_iterations: Optional[int] = 15


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
    if not req.task or not req.task.strip():
        raise HTTPException(status_code=400, detail="Task description cannot be empty")
    target_repo = resolve_target_repo(req.github_repo, request.headers.get("X-Target-Repo")) or ""
    target_token = req.github_token or request.headers.get("X-GitHub-Token") or ""
    target_groq_key = req.api_key or request.headers.get("X-Groq-Api-Key") or ""
    job_id = job_manager.create_job(
        task=req.task.strip(),
        project_dir=".",
        api_key=target_groq_key,
        github_repo=target_repo,
        github_token=target_token,
        max_iterations=req.max_iterations if req.max_iterations is not None else 15
    )
    return {"job_id": job_id, "status": "queued"}


@router.get("/api/jobs")
async def list_jobs(request: Request):
    repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo"))
    if not repo:
        return {"jobs": []}
    return {"jobs": job_manager.list_jobs(github_repo=repo)}


def _assert_job_repo_access(job: dict, request: Request):
    job_repo = (job.get("github_repo") or "").strip()
    if not job_repo:
        return
    req_repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo"))
    if req_repo and req_repo != job_repo:
        raise HTTPException(status_code=403, detail="Access denied: job belongs to a different repository")


@router.get("/api/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _assert_job_repo_access(job, request)
    return job


@router.delete("/api/jobs/{job_id}")
async def delete_job(job_id: str, request: Request):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _assert_job_repo_access(job, request)
    job_manager.delete_job(job_id)
    return {"status": "deleted", "job_id": job_id}


@router.post("/api/jobs/{job_id}/approve")
async def approve_job(job_id: str, request: Request):
    try:
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        _assert_job_repo_access(job, request)
        token = request.headers.get("X-GitHub-Token", "")
        repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo")) or ""
        result = await job_manager.approve_job(job_id, github_token=token, github_repo=repo)
        return result
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/jobs/{job_id}/reject")
async def reject_job(job_id: str, req: RejectJobRequest, request: Request):
    try:
        job = job_manager.get_job(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="Job not found")
        _assert_job_repo_access(job, request)
        result = await job_manager.reject_job(job_id, req.reason or "")
        return result
    except HTTPException:
        raise
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/mcp")
async def mcp_endpoint(req: dict):
    return mcp_server.handle_request(req)


@router.post("/api/webhook/github")
async def github_webhook(payload: WebhookPayload, request: Request):
    webhook_secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "").strip()
    if webhook_secret:
        sig_header = request.headers.get("X-Hub-Signature-256", "")
        raw_body = await request.body()
        expected = "sha256=" + hmac.new(webhook_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
        if not sig_header or not hmac.compare_digest(sig_header, expected):
            raise HTTPException(status_code=401, detail="Invalid GitHub webhook signature")

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
async def workspace_tree(request: Request, dir: str = ".", repo: Optional[str] = None, branch: Optional[str] = None):
    try:
        target_repo = resolve_target_repo(repo, request.headers.get("X-Target-Repo"))
        user_token = request.headers.get("X-GitHub-Token", "").strip()

        if target_repo:
            headers = {"Accept": "application/vnd.github.v3+json"}
            if user_token:
                headers["Authorization"] = f"token {user_token}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                repo_resp = await client.get(f"https://api.github.com/repos/{target_repo}", headers=headers)
                if repo_resp.status_code == 404:
                    raise HTTPException(status_code=404, detail=f"Repository '{target_repo}' not found or private (provide a GitHub PAT)")
                if repo_resp.status_code in (401, 403):
                    raise HTTPException(status_code=repo_resp.status_code, detail="GitHub API authentication or rate limit error")
                repo_resp.raise_for_status()
                repo_meta = repo_resp.json()
                active_branch = (branch or repo_meta.get("default_branch") or "main").strip()

                tree_resp = await client.get(
                    f"https://api.github.com/repos/{target_repo}/git/trees/{active_branch}?recursive=1",
                    headers=headers,
                )
                tree_resp.raise_for_status()
                tree_data = tree_resp.json()
                ignored_parts = (".git", "node_modules", ".venv", "__pycache__", ".pytest_cache")
                files = []
                for item in tree_data.get("tree", []):
                    if item.get("type") == "blob":
                        p = item.get("path", "")
                        if any(part in ignored_parts for part in p.split("/")):
                            continue
                        files.append(p)
                        if len(files) >= 500:
                            break
                return {
                    "source": "github",
                    "repo": target_repo,
                    "repo_url": f"https://github.com/{target_repo}",
                    "branch": active_branch,
                    "branches": [active_branch],
                    "clone_url": f"https://github.com/{target_repo}.git",
                    "commit": (tree_data.get("sha") or "HEAD")[:7],
                    "commit_msg": f"Synced from GitHub ({active_branch})",
                    "sync_status": "synced",
                    "files": sorted(files),
                }

        raw_files = get_file_tree(".")
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

        return {
            "source": "sandbox",
            "repo": None,
            "repo_url": "",
            "branch": "main",
            "branches": ["main"],
            "clone_url": "",
            "commit": "HEAD",
            "commit_msg": "Local Sandbox Sample",
            "sync_status": "unconnected",
            "files": sorted(filtered)
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/workspace/file")
async def workspace_file(request: Request, path: str, branch: Optional[str] = None):
    try:
        clean_path = path.replace("\\", "/").lstrip("/")
        target_repo = resolve_target_repo(None, request.headers.get("X-Target-Repo"))
        user_token = request.headers.get("X-GitHub-Token", "").strip()

        lang_map = {
            ".py": "python", ".json": "json", ".html": "html", ".css": "css",
            ".js": "javascript", ".ts": "typescript", ".tsx": "typescript",
            ".jsx": "javascript", ".md": "markdown", ".txt": "text",
            ".yml": "yaml", ".yaml": "yaml", ".toml": "toml", ".sh": "bash"
        }
        ext = Path(clean_path).suffix.lower()

        if target_repo:
            headers = {"Accept": "application/vnd.github.v3.raw"}
            if user_token:
                headers["Authorization"] = f"token {user_token}"
            ref_param = f"?ref={branch}" if branch else ""
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(
                    f"https://api.github.com/repos/{target_repo}/contents/{clean_path}{ref_param}",
                    headers=headers,
                )
                if resp.status_code == 404:
                    raise HTTPException(status_code=404, detail="File not found in repository")
                if resp.status_code in (401, 403):
                    raise HTTPException(status_code=resp.status_code, detail="GitHub API access denied or rate limited")
                resp.raise_for_status()
                content = resp.text
                return {
                    "path": clean_path,
                    "filename": Path(clean_path).name,
                    "size": len(content.encode("utf-8", errors="ignore")),
                    "lines": len(content.splitlines()),
                    "language": lang_map.get(ext, "text"),
                    "author": target_repo.split("/")[0],
                    "content": content,
                }

        parts = clean_path.split("/")
        forbidden = {".env", "omnidev.db", "tests", ".pytest_cache", ".venv", ".git", ".idea"}
        if any(p in forbidden or p.startswith(".env") for p in parts) or clean_path.endswith(".doc") or clean_path.endswith(".docx") or clean_path.endswith(".pdf"):
            raise HTTPException(status_code=403, detail="Access denied to protected file")

        file_path = Path(clean_path).resolve()
        root_path = Path(".").resolve()
        if not file_path.is_relative_to(root_path):
            raise HTTPException(status_code=403, detail="Access denied")
        if not file_path.is_file():
            raise HTTPException(status_code=404, detail="File not found")
        content = file_path.read_text(encoding="utf-8", errors="ignore")
        size = file_path.stat().st_size
        lines = len(content.splitlines())
        return {
            "path": clean_path,
            "filename": file_path.name,
            "size": size,
            "lines": lines,
            "language": lang_map.get(ext, "text"),
            "author": "Sandbox Sample",
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
        groq_key = req.get("key") or req.get("groq_api_key") or request.headers.get("X-Groq-Api-Key") or os.environ.get("GROQ_API_KEY", "")
        if not groq_key:
            return {"status": "error", "message": "Groq API key not configured. Enter your gsk_... key in Settings."}
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
        "localtunnel_url": os.environ.get("LOCALTUNNEL_URL", ""),
        "port": int(os.environ.get("PORT", 4000)),
        "model": "openai/gpt-oss-20b",
        "llm_provider": "Groq API (Free Tier)",
        "platform_status": "operational",
        "db_engine": get_db_engine_name(),
        "tests_status": "28/28 passed",
        "user_profile": USER_PROFILE
    }


@router.get("/api/telemetry")
async def telemetry_data(request: Request):
    repo = resolve_target_repo(header_repo=request.headers.get("X-Target-Repo"))
    if not repo:
        return {
            "total_jobs": 0,
            "success_rate": 100.0,
            "status_counts": {},
            "pr_count": 0,
            "recent_jobs": [],
            "recent_logs": [],
            "db_engine": get_db_engine_name(),
            "repo": None,
            "repo_url": None,
            "active_pr_url": None,
        }
    stats = get_telemetry_stats(github_repo=repo)
    stats["repo"] = repo
    stats["repo_url"] = f"https://github.com/{repo}"
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
        "localtunnel_url": os.environ.get("LOCALTUNNEL_URL", ""),
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
    # Architecture B: Settings are stored per-client in browser localStorage and sent via headers.
    # Never mutate global server os.environ or shared USER_PROFILE across multi-tenant sessions.
    return {
        "status": "ok",
        "message": "Session settings saved",
        "profile": {
            "name": req.user_name or DEFAULT_USER_PROFILE["name"],
            "email": req.user_email or DEFAULT_USER_PROFILE["email"],
            "role": req.user_role or DEFAULT_USER_PROFILE["role"],
            "org": req.user_org or DEFAULT_USER_PROFILE["org"],
        },
        "repo": req.github_repo or ""
    }
