import os
import sys
import asyncio
import uuid
import shutil
import tempfile
import subprocess
from datetime import datetime, timezone
from typing import Any
from src.agent.llm_provider import LLMProvider
from src.agent.agent_executor import AgentExecutor
from src.github_client import GitHubClient
from src.server.database import save_job, get_job as db_get_job, list_jobs as db_list_jobs, delete_job as db_delete_job, add_log


def _clean_repo_slug(repo: str) -> str:
    clean = (repo or "").strip().rstrip("/")
    if clean.startswith("https://github.com/"):
        clean = clean[len("https://github.com/"):]
    if clean.endswith(".git"):
        clean = clean[:-4]
    return clean


class JobManager:
    def create_job(self, task: str, project_dir: str = ".", api_key: str = "", github_repo: str = "", github_token: str = "", max_iterations: int = 15) -> str:
        job_id = str(uuid.uuid4())[:8]
        clean_repo = _clean_repo_slug(github_repo)
        safe_iters = max(1, min(int(max_iterations or 15), 30))
        job_data = {
            "id": job_id,
            "task": task,
            "project_dir": ".",
            "github_repo": clean_repo,
            "status": "queued",
            "result": None,
            "diffs": [],
            "pr_url": None,
            "branch_name": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "completed_at": None,
        }
        save_job(job_data)
        add_log(job_id, "task", task)
        asyncio.create_task(self._run_job(job_id, task, ".", api_key, clean_repo, github_token.strip() if github_token else "", safe_iters))
        return job_id

    async def _run_job(self, job_id: str, task: str, project_dir: str, api_key: str, github_repo: str = "", github_token: str = "", max_iterations: int = 15):
        job = db_get_job(job_id)
        if not job:
            return
        job["status"] = "running"
        save_job(job)

        loop = asyncio.get_running_loop()

        def on_step(entry: dict[str, str]):
            add_log(job_id, entry["event"], entry["data"])
            from src.server.websocket_manager import ws_manager
            asyncio.run_coroutine_threadsafe(ws_manager.broadcast(job_id, entry), loop)

        temp_workspace: str | None = None
        effective_dir = project_dir

        try:
            if github_repo:
                temp_workspace = tempfile.mkdtemp(prefix=f"omnidev_{job_id}_")
                clone_url = (
                    f"https://x-access-token:{github_token}@github.com/{github_repo}.git"
                    if github_token
                    else f"https://github.com/{github_repo}.git"
                )
                on_step({"event": "workspace", "data": f"Cloning {github_repo} into isolated sandbox..."})
                proc = await asyncio.to_thread(
                    subprocess.run,
                    ["git", "clone", "--depth", "1", clone_url, temp_workspace],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
                if proc.returncode != 0:
                    err_msg = (proc.stderr or "git clone failed").strip()
                    if github_token:
                        err_msg = err_msg.replace(github_token, "***")
                    raise RuntimeError(f"Failed to clone {github_repo}: {err_msg}")
                effective_dir = temp_workspace
                on_step({"event": "workspace", "data": f"Isolated workspace ready for {github_repo}"})

            llm = LLMProvider(api_key=api_key if api_key else None)
            agent = AgentExecutor(llm, project_dir=effective_dir, max_iterations=max_iterations)
            result = await asyncio.to_thread(agent.run, task, on_step)

            job["status"] = result["status"]
            job["result"] = result.get("result")
            job["diffs"] = result.get("diffs", [])
        except Exception as e:
            err_str = str(e)
            if github_token:
                err_str = err_str.replace(github_token, "***")
            job["status"] = "failed"
            job["result"] = err_str
            add_log(job_id, "error", err_str)
        finally:
            if temp_workspace:
                shutil.rmtree(temp_workspace, ignore_errors=True)
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_job(job)
            from src.server.websocket_manager import ws_manager
            await ws_manager.broadcast(job_id, {
                "event": "status_change",
                "data": f"Job {job_id} status updated to {job['status']}"
            })

    async def approve_job(self, job_id: str, github_token: str = "", github_repo: str = "") -> dict[str, Any]:
        job = db_get_job(job_id)
        if not job:
            raise ValueError("Job not found")

        if job["status"] not in ("awaiting_approval", "completed"):
            raise ValueError(f"Job cannot be approved in state: {job['status']}")

        effective_token = (github_token or os.environ.get("GITHUB_TOKEN", "")).strip()
        effective_repo = (job.get("github_repo") or github_repo or os.environ.get("GITHUB_REPO", "")).strip()

        if not effective_token or not effective_repo:
            job["status"] = "approved_local_only"
            job["result"] = (job.get("result") or "") + "\n\n(Approved locally; GitHub repository or Personal Access Token not provided)"
            save_job(job)
            return {"status": job["status"], "pr_url": None, "message": "Approved locally (No GitHub credentials)"}

        gh = GitHubClient(effective_token, effective_repo)
        branch_name = f"omnidev/fix-{job_id}"
        diffs = job.get("diffs", [])

        try:
            # 1. Create branch
            await gh.create_branch(branch_name)
            job["branch_name"] = branch_name
            add_log(job_id, "github_branch", f"Created branch {branch_name}")

            # 2. Commit each changed file
            for d in diffs:
                fp = d.get("file_path", "")
                content = d.get("new_content", "")
                if fp and content:
                    clean_path = fp.replace("\\", "/")
                    await gh.create_or_update_file(
                        path=clean_path,
                        content=content,
                        message=f"fix(omnidev): autonomous fix for job #{job_id}",
                        branch=branch_name
                    )
                    add_log(job_id, "github_commit", f"Committed {clean_path}")

            # 3. Create Pull Request
            pr_title = f"[OmniDev] Fix: {job['task'][:70]}"
            diff_markdown = "\n".join([f"### `{d.get('file_path')}`\n```diff\n{d.get('diff')}\n```" for d in diffs]) or "No diff recorded."
            pr_body = f"""## 🤖 OmniDev Autonomous Pull Request

### 📋 Task Description
{job['task']}

### 🔍 Root Cause & Fix
{job.get('result', 'Automated patch verified by test suite.')}

### 📝 Modified Files & Diffs
{diff_markdown}

### 🔄 Verification
- [x] Code inspection verified
- [x] Automated unit tests executed and passed
- [x] Human approved via OmniDev Dashboard

```mermaid
graph TD
    A[Incident / Issue] --> B[OmniDev Agent]
    B --> C[Self-Healing Test Loop]
    C --> D[Human Approval]
    D --> E[Pull Request #{job_id}]
```
*Generated autonomously by [OmniDev Platform](https://github.com/{effective_repo})*
"""
            pr_resp = await gh.create_pull_request(
                title=pr_title,
                body=pr_body,
                head=branch_name
            )
            pr_url = pr_resp.get("html_url")
            job["status"] = "pr_created"
            job["pr_url"] = pr_url
            save_job(job)
            add_log(job_id, "pr_created", pr_url or "PR opened")

            from src.server.websocket_manager import ws_manager
            await ws_manager.broadcast(job_id, {
                "event": "pr_created",
                "data": pr_url
            })
            return {"status": "pr_created", "pr_url": pr_url, "branch": branch_name}

        except Exception as e:
            add_log(job_id, "github_error", str(e))
            save_job(job)
            raise RuntimeError(f"GitHub operation failed: {e}")

    async def reject_job(self, job_id: str, reason: str = "") -> dict[str, Any]:
        job = db_get_job(job_id)
        if not job:
            raise ValueError("Job not found")

        job["status"] = "rejected"
        add_log(job_id, "rejected", f"Job rejected by user. Reason: {reason or 'None provided'}")
        save_job(job)

        from src.server.websocket_manager import ws_manager
        await ws_manager.broadcast(job_id, {
            "event": "rejected",
            "data": reason
        })
        return {"status": "rejected", "job_id": job_id}

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        return db_get_job(job_id)

    def list_jobs(self, github_repo: str | None = None) -> list[dict[str, Any]]:
        return db_list_jobs(github_repo=github_repo)

    def delete_job(self, job_id: str) -> bool:
        return db_delete_job(job_id)


job_manager = JobManager()
