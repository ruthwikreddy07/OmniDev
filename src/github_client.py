import os
import httpx
from typing import Any


class GitHubClient:
    def __init__(self, token: str, repo: str):
        self.token = token
        clean_repo = repo.strip().rstrip("/")
        if clean_repo.startswith("https://github.com/"):
            clean_repo = clean_repo[len("https://github.com/"):]
        if clean_repo.endswith(".git"):
            clean_repo = clean_repo[:-4]
        self.repo = clean_repo
        self.base_url = f"https://api.github.com/repos/{self.repo}"
        self.headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }

    async def get_default_branch(self) -> str:
        async with httpx.AsyncClient() as client:
            resp = await client.get(self.base_url, headers=self.headers)
            resp.raise_for_status()
            return resp.json().get("default_branch", "main")

    async def get_file_sha(self, path: str, branch: str) -> str | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/contents/{path}?ref={branch}",
                headers=self.headers
            )
            if resp.status_code == 200:
                return resp.json().get("sha")
            return None

    async def create_branch(self, branch_name: str, from_branch: str | None = None) -> dict[str, Any]:
        if not from_branch:
            from_branch = await self.get_default_branch()

        async with httpx.AsyncClient() as client:
            ref_resp = await client.get(f"{self.base_url}/git/ref/heads/{from_branch}", headers=self.headers)
            ref_resp.raise_for_status()
            sha = ref_resp.json()["object"]["sha"]

            create_resp = await client.post(
                f"{self.base_url}/git/refs",
                headers=self.headers,
                json={"ref": f"refs/heads/{branch_name}", "sha": sha}
            )
            create_resp.raise_for_status()
            return create_resp.json()

    async def create_or_update_file(
        self, path: str, content: str, message: str, branch: str, sha: str | None = None
    ) -> dict[str, Any]:
        import base64
        if sha is None:
            sha = await self.get_file_sha(path, branch)

        payload: dict[str, Any] = {
            "message": message,
            "content": base64.b64encode(content.encode()).decode(),
            "branch": branch,
        }
        if sha:
            payload["sha"] = sha

        async with httpx.AsyncClient() as client:
            resp = await client.put(f"{self.base_url}/contents/{path}", headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    async def create_pull_request(
        self, title: str, body: str, head: str, base: str | None = None
    ) -> dict[str, Any]:
        if not base:
            base = await self.get_default_branch()

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/pulls",
                headers=self.headers,
                json={"title": title, "body": body, "head": head, "base": base}
            )
            resp.raise_for_status()
            return resp.json()

    async def add_comment(self, issue_number: int, body: str) -> dict[str, Any]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/issues/{issue_number}/comments",
                headers=self.headers,
                json={"body": body}
            )
            resp.raise_for_status()
            return resp.json()
