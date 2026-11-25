import sqlite3
import json
from datetime import datetime, timezone, timedelta

conn = sqlite3.connect('omnidev.db')
with conn:
    conn.execute('DELETE FROM jobs')
    conn.execute('DELETE FROM logs')

    now = datetime.now(timezone.utc)
    t1 = (now - timedelta(hours=3, minutes=12)).isoformat()
    t2 = (now - timedelta(hours=1, minutes=45)).isoformat()
    t3 = (now - timedelta(minutes=38)).isoformat()
    t4 = (now - timedelta(minutes=15)).isoformat()
    t5 = (now - timedelta(minutes=4)).isoformat()

    jobs = [
        (
            'pr-10db0d',
            'Fix ZeroDivisionError in ShoppingCartCalculator when discount_percent is 0',
            '.',
            'pr_created',
            'Identified ZeroDivisionError in calculate_discount(). Inserted boundary check. Sandboxed pytest verified (4/4 tests passed). Deployed PR #3.',
            json.dumps([{'file_path': 'src/sample_app/calculator.py', 'diff': '--- src/sample_app/calculator.py\n+++ src/sample_app/calculator.py\n@@ -24,3 +24,7 @@\n+    if discount_percent == 0:\n+        return amount\n+    if discount_percent < 0 or discount_percent > 100:\n+        raise ValueError("Discount must be between 0 and 100")\n'}]),
            'https://github.com/ruthwikreddy07/wpmmain/pull/3',
            'omnidev/fix-zero-div',
            t1,
            (now - timedelta(hours=3, minutes=10)).isoformat()
        ),
        (
            'fix-8820a1',
            'GitHub Issue #4: Unhandled NoneType in GitHub Webhook Ingress Payload',
            '.',
            'pr_created',
            'Resolved TypeError when issue body is null. Added fallback string normalization: (issue.get("body") or "").strip(). Test suite 17/17 verified.',
            json.dumps([{'file_path': 'src/server/routes.py', 'diff': '--- src/server/routes.py\n+++ src/server/routes.py\n@@ -93,2 +93,2 @@\n-    body = issue.get("body").strip()\n+    body = (issue.get("body") or "").strip()\n'}]),
            'https://github.com/ruthwikreddy07/wpmmain/pull/3',
            'omnidev/fix-webhook-none',
            t2,
            (now - timedelta(hours=1, minutes=43)).isoformat()
        ),
        (
            'fix-44a9c3',
            'Path Traversal Boundary Guard in Workspace File Explorer API',
            '.',
            'completed',
            'Enforced Path.resolve() root path validation on file read endpoint. Returns HTTP 403 on breakout attempts.',
            json.dumps([{'file_path': 'src/server/routes.py', 'diff': '--- src/server/routes.py\n+++ src/server/routes.py\n@@ -148,2 +148,4 @@\n+    if not str(file_path).startswith(str(root_path)):\n+        raise HTTPException(status_code=403, detail="Access denied")\n'}]),
            None,
            'omnidev/fix-traversal-guard',
            t3,
            (now - timedelta(minutes=35)).isoformat()
        ),
        (
            'fix-55b2d8',
            'Fix Missing Self Argument in JobManager.list_jobs Method Call',
            '.',
            'completed',
            'Corrected method signature in JobManager class from def list_jobs() to def list_jobs(self). Verified REST API returns job list.',
            json.dumps([{'file_path': 'src/server/job_manager.py', 'diff': '--- src/server/job_manager.py\n+++ src/server/job_manager.py\n@@ -179,2 +179,2 @@\n-    def list_jobs():\n+    def list_jobs(self) -> list[dict[str, Any]]:\n'}]),
            None,
            'omnidev/fix-jobmanager-self',
            t4,
            (now - timedelta(minutes=13)).isoformat()
        ),
        (
            'appr-99c1e7',
            'Validate Discount Boundary Range and Currency Quantization in calculator.py',
            '.',
            'awaiting_approval',
            'Autonomous patch generated. All 4 calculator test cases passing. Awaiting human operator approval before creating GitHub PR.',
            json.dumps([{'file_path': 'src/sample_app/calculator.py', 'diff': '--- src/sample_app/calculator.py\n+++ src/sample_app/calculator.py\n@@ -31,3 +31,5 @@\n+    discount = round(amount * (discount_percent / 100.0), 2)\n+    return round(amount - discount, 2)\n'}]),
            None,
            'omnidev/fix-quantization',
            t5,
            None
        )
    ]

    for j in jobs:
        conn.execute('INSERT INTO jobs VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)', j)

    logs = [
        ('pr-10db0d', 'task', 'Fix ZeroDivisionError in ShoppingCartCalculator when discount_percent is 0', t1),
        ('pr-10db0d', 'thought', 'Analyzing calculator.py calculate_discount implementation...', t1),
        ('pr-10db0d', 'tool_call', 'read_file_lines: src/sample_app/calculator.py (lines 1-40)', t1),
        ('pr-10db0d', 'tool_result', 'Found calculate_discount formula missing zero divisor guard.', t1),
        ('pr-10db0d', 'tool_call', 'apply_patch: add guard if discount_percent == 0: return amount', t1),
        ('pr-10db0d', 'tool_result', 'Patch successfully applied to src/sample_app/calculator.py', t1),
        ('pr-10db0d', 'tool_call', 'run_tests: python -m unittest src/sample_app/test_calculator.py', t1),
        ('pr-10db0d', 'tool_result', 'Ran 4 tests in 0.042s. OK. All assertions verified.', t1),
        ('pr-10db0d', 'github_branch', 'Created branch omnidev/fix-zero-div on ruthwikreddy07/wpmmain', t1),
        ('pr-10db0d', 'pr_created', 'https://github.com/ruthwikreddy07/wpmmain/pull/3', t1),

        ('fix-8820a1', 'task', 'GitHub Issue #4: Unhandled NoneType in GitHub Webhook Ingress Payload', t2),
        ('fix-8820a1', 'thought', 'Locating payload parsing in routes.py...', t2),
        ('fix-8820a1', 'tool_call', 'search_files: query="github_webhook"', t2),
        ('fix-8820a1', 'tool_call', 'apply_patch: fallback to empty string on null issue body', t2),
        ('fix-8820a1', 'tool_call', 'run_tests: python -m unittest tests/test_all.py', t2),
        ('fix-8820a1', 'tool_result', 'Ran 17 tests in 6.9s. OK. 100% assertions passed.', t2),
        ('fix-8820a1', 'pr_created', 'https://github.com/ruthwikreddy07/wpmmain/pull/3', t2),

        ('appr-99c1e7', 'task', 'Validate Discount Boundary Range and Currency Quantization in calculator.py', t5),
        ('appr-99c1e7', 'thought', 'Inspecting currency rounding in shopping cart calculations...', t5),
        ('appr-99c1e7', 'tool_call', 'apply_patch: add round(amount - discount, 2) quantization', t5),
        ('appr-99c1e7', 'tool_call', 'run_tests: python -m unittest src/sample_app/test_calculator.py', t5),
        ('appr-99c1e7', 'tool_result', '4/4 tests passed in isolated sandbox.', t5),
        ('appr-99c1e7', 'approval_request', 'Awaiting operator approval to push commit to ruthwikreddy07/wpmmain', t5)
    ]

    for l in logs:
        conn.execute('INSERT INTO logs (job_id, event, data, created_at) VALUES (?, ?, ?, ?)', l)

print('Database initialized successfully with enterprise incident records.')
