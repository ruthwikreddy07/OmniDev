import os
import re
import sys
import subprocess
from pathlib import Path
from typing import Any

_SECRET_ENV_KEYS = (
    "DATABASE_URL", "GROQ_API_KEY", "GITHUB_TOKEN", "GEMINI_API_KEY",
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "N8N_WEBHOOK_URL"
)

_BLOCKED_PATTERNS = re.compile(
    r"(^|\s|;|&|\|)(rm\s+-rf|del\s+/|format\s+|mkfs|dd\s+if=|curl\s+|wget\s+|printenv|env(\s|$)|set(\s|$)|sudo\s+|shutdown|reboot)",
    re.IGNORECASE,
)


def _safe_subprocess_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items() if k not in _SECRET_ENV_KEYS}


def _normalize_command(command: str) -> str:
    cmd = command.strip()
    if cmd.startswith("python "):
        return f'"{sys.executable}" ' + cmd[7:]
    if cmd == "pytest" or cmd.startswith("pytest "):
        rest = cmd[6:].strip()
        return f'"{sys.executable}" -m pytest {rest}'.strip()
    return cmd


def _validate_command(command: str) -> str | None:
    if not command or not command.strip():
        return "Empty test command"
    if _BLOCKED_PATTERNS.search(command):
        return "Blocked potentially unsafe command in sandboxed test runner"
    return None


def run_tests(
    project_dir: str | Path,
    test_command: str = "python -m unittest discover -s src/sample_app",
    timeout: int = 15
) -> dict[str, Any]:
    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    err = _validate_command(test_command)
    if err:
        return {'exit_code': -1, 'passed': False, 'stdout': '', 'stderr': err}

    cmd = _normalize_command(test_command)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(project_path),
            env=_safe_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            'exit_code': result.returncode,
            'passed': result.returncode == 0,
            'stdout': result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            'stderr': result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            'exit_code': -1,
            'passed': False,
            'stdout': '',
            'stderr': f'Test execution timed out after {timeout}s',
        }


def run_command_sandboxed(
    command: str,
    cwd: str | Path = ".",
    timeout: int = 15
) -> dict[str, Any]:
    err = _validate_command(command)
    if err:
        return {'exit_code': -1, 'passed': False, 'stdout': '', 'stderr': err}

    cmd = _normalize_command(command)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(Path(cwd).resolve()),
            env=_safe_subprocess_env(),
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            'exit_code': result.returncode,
            'stdout': result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout,
            'stderr': result.stderr[-2000:] if len(result.stderr) > 2000 else result.stderr,
        }
    except subprocess.TimeoutExpired:
        return {
            'exit_code': -1,
            'stdout': '',
            'stderr': f'Command timed out after {timeout}s',
        }
