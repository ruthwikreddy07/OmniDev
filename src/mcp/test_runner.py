import sys
import subprocess
from pathlib import Path
from typing import Any


def _normalize_command(command: str) -> str:
    cmd = command.strip()
    if cmd.startswith("python "):
        return f'"{sys.executable}" ' + cmd[7:]
    elif cmd.startswith("pytest") or "pytest" in cmd:
        # If pytest command is given, invoke unittest or pytest via sys.executable
        return f'"{sys.executable}" -m unittest discover -s src/sample_app'
    return cmd


def run_tests(
    project_dir: str | Path,
    test_command: str = "python -m unittest discover -s src/sample_app",
    timeout: int = 15
) -> dict[str, Any]:
    project_path = Path(project_dir).resolve()
    if not project_path.is_dir():
        raise FileNotFoundError(f"Project directory not found: {project_dir}")

    cmd = _normalize_command(test_command)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(project_path),
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
    cmd = _normalize_command(command)
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            cwd=str(Path(cwd).resolve()),
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
