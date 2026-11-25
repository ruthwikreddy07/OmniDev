import os
import sqlite3
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

def get_db_path():
    custom = os.environ.get("OMNIDEV_DB_PATH")
    if custom:
        return Path(custom)
    return Path(__file__).resolve().parent.parent.parent / "omnidev.db"


def get_db():
    conn = sqlite3.connect(str(get_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                task TEXT NOT NULL,
                project_dir TEXT NOT NULL,
                status TEXT NOT NULL,
                result TEXT,
                diffs TEXT,
                pr_url TEXT,
                branch_name TEXT,
                created_at TEXT NOT NULL,
                completed_at TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id TEXT NOT NULL,
                event TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
    conn.close()


def save_job(job: dict[str, Any]):
    conn = get_db()
    with conn:
        conn.execute("""
            INSERT OR REPLACE INTO jobs 
            (id, task, project_dir, status, result, diffs, pr_url, branch_name, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job["id"],
            job["task"],
            job.get("project_dir", "."),
            job["status"],
            job.get("result"),
            json.dumps(job.get("diffs", [])),
            job.get("pr_url"),
            job.get("branch_name"),
            job.get("created_at", datetime.now(timezone.utc).isoformat()),
            job.get("completed_at")
        ))
    conn.close()


def add_log(job_id: str, event: str, data: str):
    conn = get_db()
    with conn:
        conn.execute("""
            INSERT INTO logs (job_id, event, data, created_at)
            VALUES (?, ?, ?, ?)
        """, (job_id, event, data, datetime.now(timezone.utc).isoformat()))
    conn.close()


def list_jobs() -> list[dict[str, Any]]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, task, status, created_at, pr_url FROM jobs ORDER BY created_at DESC")
    rows = cur.fetchall()
    conn.close()
    return [
        {
            "id": r["id"],
            "job_id": r["id"],
            "task": r["task"][:120],
            "status": r["status"],
            "created_at": r["created_at"],
            "pr_url": r["pr_url"]
        }
        for r in rows
    ]


def get_job(job_id: str) -> dict[str, Any] | None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM jobs WHERE id = ?", (job_id,))
    row = cur.fetchone()
    if not row:
        conn.close()
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

    # Synthesize patch string for convenience
    job["patch"] = "\n".join(d.get("diff", "") for d in job.get("diffs", [])) if job.get("diffs") else ""

    cur.execute("SELECT event, data, created_at FROM logs WHERE job_id = ? ORDER BY id ASC", (job_id,))
    job["logs"] = [{"event": r["event"], "data": r["data"], "created_at": r["created_at"]} for r in cur.fetchall()]
    conn.close()
    return job


def get_telemetry_stats() -> dict[str, Any]:
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM jobs")
    total_jobs = cur.fetchone()[0]

    cur.execute("SELECT status, COUNT(*) FROM jobs GROUP BY status")
    status_counts = dict(cur.fetchall())

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

    cur.execute("SELECT COUNT(*) FROM jobs WHERE pr_url IS NOT NULL AND pr_url != ''")
    pr_count = cur.fetchone()[0]

    conn.close()

    completed_or_pr = status_counts.get("pr_created", 0) + status_counts.get("completed", 0) + status_counts.get("awaiting_approval", 0)
    success_rate = round((completed_or_pr / total_jobs * 100), 1) if total_jobs > 0 else 100.0

    return {
        "total_jobs": total_jobs,
        "success_rate": success_rate,
        "status_counts": status_counts,
        "pr_count": pr_count,
        "recent_jobs": recent_jobs,
        "recent_logs": recent_logs
    }



init_db()
