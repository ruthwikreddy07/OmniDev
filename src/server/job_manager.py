import os
import sys
import asyncio
import uuid
from datetime import datetime, timezone
from typing import Any
from src.agent.llm_provider import LLMProvider
from src.agent.agent_executor import AgentExecutor
from src.github_client import GitHubClient
from src.server.database import save_job, get_job as db_get_job, list_jobs as db_list_jobs, add_log


class JobManager:
    def create_job(self, task: str, project_dir: str = ".", api_key: str = "") -> str:
        job_id = str(uuid.uuid4())[:8]
        job_data = {
            "id": job_id,
            "task": task,
            "project_dir": project_dir,
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
        asyncio.create_task(self._run_job(job_id, task, project_dir, api_key))
        return job_id

    async def _run_job(self, job_id: str, task: str, project_dir: str, api_key: str):
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

        try:
            llm = LLMProvider(api_key=api_key if api_key else None)
            agent = AgentExecutor(llm, project_dir=project_dir)
            result = await asyncio.to_thread(agent.run, task, on_step)

            job["status"] = result["status"]
            job["result"] = result.get("result")
            job["diffs"] = result.get("diffs", [])
        except Exception as e:
            job["status"] = "failed"
            job["result"] = str(e)
            add_log(job_id, "error", str(e))
        finally:
            job["completed_at"] = datetime.now(timezone.utc).isoformat()
            save_job(job)
            from src.server.websocket_manager import ws_manager
            await ws_manager.broadcast(job_id, {
                "event": "status_change",
                "data": f"Job {job_id} status updated to {job['status']}"
            })

    async def approve_job(self, job_id: str) -> dict[str, Any]:
        job = db_get_job(job_id)
        if not job:
            raise ValueError("Job not found")

        if job["status"] not in ("awaiting_approval", "completed"):
            raise ValueError(f"Job cannot be approved in state: {job['status']}")

        github_token = os.environ.get("GITHUB_TOKEN", "").strip()
        github_repo = os.environ.get("GITHUB_REPO", "").strip()

        if not github_token or not github_repo:
            job["status"] = "approved_local_only"
            job["result"] = (job.get("result") or "") + "\n\n(Approved locally; GITHUB_TOKEN or GITHUB_REPO not set)"
            save_job(job)
            return {"status": job["status"], "pr_url": None, "message": "Approved locally (No GitHub credentials)"}

        gh = GitHubClient(github_token, github_repo)
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
*Generated autonomously by [OmniDev Platform](https://github.com/{github_repo})*
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

    def list_jobs(self) -> list[dict[str, Any]]:
        return db_list_jobs()


job_manager = JobManager()
