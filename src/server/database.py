import os
import sqlite3
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone
from urllib.parse import urlparse

try:
    import psycopg
    from psycopg.rows import dict_row
except ImportError:
    psycopg = None
    dict_row = None


def _use_postgres() -> bool:
    if os.environ.get("OMNIDEV_DB_PATH"):
        return False
    db_url = os.environ.get("DATABASE_URL", "").strip()
    return bool(db_url)


def get_db_engine_name() -> str:
    return "PostgreSQL" if _use_postgres() else "SQLite"


def _normalize_pg_url(url: str) -> str:
    clean = url.strip()
    if clean.startswith("postgres://"):
        clean = "postgresql://" + clean[len("postgres://"):]
    parsed = urlparse(clean)
    host = (parsed.hostname or "").lower()
    if host not in ("localhost", "127.0.0.1", "::1", "") and "sslmode=" not in clean:
        sep = "&" if "?" in clean else "?"
        clean = f"{clean}{sep}sslmode=require"
    return clean


def get_db_path() -> Path:
    custom = os.environ.get("OMNIDEV_DB_PATH")
    if custom:
        return Path(custom)
    return Path(__file__).resolve().parent.parent.parent / "omnidev.db"


def get_db():
    if _use_postgres():
        if psycopg is None:
            raise RuntimeError("psycopg is required when DATABASE_URL is set. Install psycopg[binary].")
        url = _normalize_pg_url(os.environ["DATABASE_URL"])
        return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _ph() -> str:
    return "%s" if _use_postgres() else "?"


def init_db():
    is_pg = _use_postgres()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                github_repo TEXT DEFAULT '',
                status TEXT NOT NULL,
                result TEXT,
                diffs TEXT,
                pr_url TEXT,
                branch_name TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        if is_pg:
            cur.execute("ALTER TABLE jobs ADD COLUMN IF NOT EXISTS github_repo TEXT DEFAULT ''")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id SERIAL PRIMARY KEY,
                    job_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        else:
            cur.execute("PRAGMA table_info(jobs)")
            cols = {row["name"] for row in cur.fetchall()}
            if "github_repo" not in cols:
                cur.execute("ALTER TABLE jobs ADD COLUMN github_repo TEXT DEFAULT ''")
            cur.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    job_id TEXT NOT NULL,
                    event TEXT NOT NULL,
                    data TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
            """)
        cur.execute("CREATE INDEX IF NOT EXISTS idx_logs_job_id ON logs(job_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at DESC)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_jobs_repo ON jobs(github_repo)")
        conn.commit()
    finally:
        conn.close()


def save_job(job: dict[str, Any]):
    p = _ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO jobs
            (id, task, project_dir, github_repo, status, result, diffs, pr_url, branch_name, created_at, completed_at)
            VALUES ({p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p}, {p})
            ON CONFLICT (id) DO UPDATE SET
                task = EXCLUDED.task,
                project_dir = EXCLUDED.project_dir,
                github_repo = EXCLUDED.github_repo,
                status = EXCLUDED.status,
                result = EXCLUDED.result,
                diffs = EXCLUDED.diffs,
                pr_url = EXCLUDED.pr_url,
                branch_name = EXCLUDED.branch_name,
                completed_at = EXCLUDED.completed_at
        """, (
            job["id"],
            job["task"],
            job.get("project_dir", "."),
            job.get("github_repo", "") or "",
            job["status"],
            job.get("result"),
            json.dumps(job.get("diffs", [])),
            job.get("pr_url"),
            job.get("branch_name"),
            job.get("created_at", datetime.now(timezone.utc).isoformat()),
            job.get("completed_at")
        ))
        conn.commit()
    finally:
        conn.close()


def add_log(job_id: str, event: str, data: str):
    p = _ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"""
            INSERT INTO logs (job_id, event, data, created_at)
            VALUES ({p}, {p}, {p}, {p})
        """, (job_id, event, data, datetime.now(timezone.utc).isoformat()))
        conn.commit()
    finally:
        conn.close()


def list_jobs(github_repo: str | None = None) -> list[dict[str, Any]]:
    p = _ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if github_repo is not None:
            cur.execute(
                f"SELECT id, task, github_repo, status, created_at, pr_url FROM jobs WHERE github_repo = {p} ORDER BY created_at DESC",
                (github_repo,)
            )
        else:
            cur.execute("SELECT id, task, github_repo, status, created_at, pr_url FROM jobs ORDER BY created_at DESC")
        rows = cur.fetchall()
        return [
            {
                "id": r["id"],
                "job_id": r["id"],
                "task": r["task"][:120],
                "github_repo": r["github_repo"] or "",
                "status": r["status"],
                "created_at": r["created_at"],
                "pr_url": r["pr_url"]
            }
            for r in rows
        ]
    finally:
        conn.close()


def get_job(job_id: str) -> dict[str, Any] | None:
    p = _ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        cur.execute(f"SELECT * FROM jobs WHERE id = {p}", (job_id,))
        row = cur.fetchone()
        if not row:
            return None

        job = dict(row)
        job["job_id"] = job["id"]
        if job.get("diffs"):
            try:
                job["diffs"] = json.loads(job["diffs"])
            except Exception:
                job["diffs"] = []
        else:
            job["diffs"] = []

        job["patch"] = "\n".join(d.get("diff", "") for d in job.get("diffs", [])) if job.get("diffs") else ""

        cur.execute(f"SELECT event, data, created_at FROM logs WHERE job_id = {p} ORDER BY id ASC", (job_id,))
        job["logs"] = [{"event": r["event"], "data": r["data"], "created_at": r["created_at"]} for r in cur.fetchall()]
        return job
    finally:
        conn.close()


def get_telemetry_stats(github_repo: str | None = None) -> dict[str, Any]:
    p = _ph()
    conn = get_db()
    try:
        cur = conn.cursor()
        if github_repo is not None:
            cur.execute(f"SELECT COUNT(*) AS cnt FROM jobs WHERE github_repo = {p}", (github_repo,))
            total_jobs = cur.fetchone()["cnt"]

            cur.execute(f"SELECT status, COUNT(*) AS cnt FROM jobs WHERE github_repo = {p} GROUP BY status", (github_repo,))
            status_counts = {r["status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute(
                f"SELECT id, task, status, pr_url, created_at FROM jobs WHERE github_repo = {p} ORDER BY created_at DESC LIMIT 10",
                (github_repo,)
            )
            recent_jobs = [
                {
                    "id": r["id"],
                    "job_id": r["id"],
                    "task": r["task"][:120],
                    "status": r["status"],
                    "pr_url": r["pr_url"],
                    "created_at": r["created_at"]
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                f"""SELECT l.event, l.data, l.created_at, l.job_id
                    FROM logs l JOIN jobs j ON l.job_id = j.id
                    WHERE j.github_repo = {p}
                    ORDER BY l.id DESC LIMIT 15""",
                (github_repo,)
            )
            recent_logs = [
                {
                    "event": r["event"],
                    "data": r["data"][:150],
                    "created_at": r["created_at"],
                    "job_id": r["job_id"]
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                f"SELECT COUNT(*) AS cnt FROM jobs WHERE github_repo = {p} AND pr_url IS NOT NULL AND pr_url != ''",
                (github_repo,)
            )
            pr_count = cur.fetchone()["cnt"]
        else:
            cur.execute("SELECT COUNT(*) AS cnt FROM jobs")
            total_jobs = cur.fetchone()["cnt"]

            cur.execute("SELECT status, COUNT(*) AS cnt FROM jobs GROUP BY status")
            status_counts = {r["status"]: r["cnt"] for r in cur.fetchall()}

            cur.execute("SELECT id, task, status, pr_url, created_at FROM jobs ORDER BY created_at DESC LIMIT 10")
            recent_jobs = [
                {
                    "id": r["id"],
                    "job_id": r["id"],
                    "task": r["task"][:120],
                    "status": r["status"],
                    "pr_url": r["pr_url"],
                    "created_at": r["created_at"]
                }
                for r in cur.fetchall()
            ]

            cur.execute("SELECT event, data, created_at, job_id FROM logs ORDER BY id DESC LIMIT 15")
            recent_logs = [
                {
                    "event": r["event"],
                    "data": r["data"][:150],
                    "created_at": r["created_at"],
                    "job_id": r["job_id"]
                }
                for r in cur.fetchall()
            ]

            cur.execute("SELECT COUNT(*) AS cnt FROM jobs WHERE pr_url IS NOT NULL AND pr_url != ''")
            pr_count = cur.fetchone()["cnt"]
    finally:
        conn.close()

    completed_or_pr = status_counts.get("pr_created", 0) + status_counts.get("completed", 0) + status_counts.get("awaiting_approval", 0)
    success_rate = round((completed_or_pr / total_jobs * 100), 1) if total_jobs > 0 else 100.0

    return {
        "total_jobs": total_jobs,
        "success_rate": success_rate,
        "status_counts": status_counts,
        "pr_count": pr_count,
        "recent_jobs": recent_jobs,
        "recent_logs": recent_logs,
        "db_engine": get_db_engine_name()
    }


try:
    init_db()
except Exception as _init_err:
    print(f"[OmniDev DB Warning] Deferred init_db(): {_init_err}")
