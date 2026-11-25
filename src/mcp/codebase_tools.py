from pathlib import Path
from typing import Any
import difflib


def search_files(root_dir: str | Path, query: str) -> list[dict[str, str]]:
    root_path = Path(root_dir).resolve()
    matches: list[dict[str, str]] = []
    ignored_dirs = {'.venv', 'node_modules', '.git', '__pycache__', 'dist', '.gemini'}

    for path in root_path.rglob('*'):
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.is_file():
            if query.lower() in path.name.lower():
                matches.append({'type': 'filename_match', 'path': str(path.relative_to(root_path))})
            else:
                try:
                    content = path.read_text(encoding='utf-8', errors='ignore')
                    if query in content:
                        matches.append({'type': 'content_match', 'path': str(path.relative_to(root_path))})
                except Exception:
                    pass
    return matches


def read_file_lines(file_path: str | Path, start_line: int = 1, end_line: int = 50) -> str:
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    content = path.read_text(encoding='utf-8')
    lines = content.replace('\r\n', '\n').splitlines()
    start_line = max(1, start_line)
    selected = lines[start_line - 1:end_line]
    return '\n'.join(f"{start_line + i}: {line}" for i, line in enumerate(selected))


def apply_patch(file_path: str | Path, target_code: str, replacement_code: str) -> dict[str, Any]:
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    content = path.read_text(encoding='utf-8')
    normalized = content.replace('\r\n', '\n')
    norm_target = target_code.replace('\r\n', '\n')
    norm_replacement = replacement_code.replace('\r\n', '\n')
    
    if norm_target not in normalized:
        raise ValueError(f"Target code not found in {file_path}")
        
    updated = normalized.replace(norm_target, norm_replacement, 1)
    
    # Generate unified git-style diff
    diff_lines = list(difflib.unified_diff(
        normalized.splitlines(keepends=True),
        updated.splitlines(keepends=True),
        fromfile=f"a/{path.name}",
        tofile=f"b/{path.name}",
        n=3
    ))
    diff_text = "".join(diff_lines)
    
    path.write_text(updated, encoding='utf-8')
    return {
        'success': True,
        'message': f'Patched {file_path}',
        'file_path': str(file_path),
        'diff': diff_text,
        'old_content': normalized,
        'new_content': updated
    }


def get_file_tree(root_dir: str | Path, max_depth: int = 3) -> list[str]:
    root_path = Path(root_dir).resolve()
    ignored_dirs = {'.venv', 'node_modules', '.git', '__pycache__', 'dist', '.gemini'}
    tree: list[str] = []

    def walk(dir_path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in ignored_dirs:
                continue
            rel = str(entry.relative_to(root_path))
            if entry.is_dir():
                tree.append(f"{rel}/")
                walk(entry, depth + 1)
            else:
                tree.append(rel)

    walk(root_path, 0)
    return tree
