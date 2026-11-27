import re
from pathlib import Path
from typing import Any
import difflib


def search_files(root_dir: str | Path, query: str) -> list[dict[str, str]]:
    root_path = Path(root_dir).resolve()
    matches: list[dict[str, str]] = []
    ignored_dirs = {
        '.venv', 'node_modules', '.git', '__pycache__', 'dist', '.gemini',
        '.pytest_cache', '.mypy_cache', '.idea', 'build', 'tests'
    }
    ignored_extensions = {'.db', '.doc', '.docx', '.pdf', '.pyc', '.env'}

    for path in root_path.rglob('*'):
        if any(part in ignored_dirs for part in path.parts):
            continue
        if path.is_file():
            if path.suffix in ignored_extensions or path.name.startswith('.env'):
                continue
            if query.lower() in path.name.lower():
                matches.append({'type': 'filename_match', 'path': str(path.relative_to(root_path)).replace('\\', '/')})
            else:
                try:
                    content = path.read_text(encoding='utf-8', errors='ignore')
                    if query in content:
                        matches.append({'type': 'content_match', 'path': str(path.relative_to(root_path)).replace('\\', '/')})
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


def _decode_unicode_escapes(text: str) -> str:
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), text)


def apply_patch(file_path: str | Path, target_code: str, replacement_code: str) -> dict[str, Any]:
    path = Path(file_path).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    content = path.read_text(encoding='utf-8')
    normalized = content.replace('\r\n', '\n')
    norm_target = target_code.replace('\r\n', '\n')
    norm_replacement = replacement_code.replace('\r\n', '\n')

    if norm_target in normalized:
        updated = normalized.replace(norm_target, norm_replacement, 1)
    else:
        decoded_target = _decode_unicode_escapes(norm_target)
        decoded_replacement = _decode_unicode_escapes(norm_replacement)
        if decoded_target in normalized:
            updated = normalized.replace(decoded_target, decoded_replacement, 1)
        else:
            # Indentation/whitespace-tolerant contiguous line match
            file_lines = normalized.splitlines()
            target_lines = [l.strip() for l in decoded_target.splitlines()]
            match_idx = -1
            if target_lines and any(target_lines):
                n_t = len(target_lines)
                for i in range(len(file_lines) - n_t + 1):
                    if [file_lines[i + j].strip() for j in range(n_t)] == target_lines:
                        match_idx = i
                        break
            if match_idx == -1:
                raise ValueError(f"Target code not found in {file_path}")
            rep_lines = decoded_replacement.splitlines()
            new_lines = file_lines[:match_idx] + rep_lines + file_lines[match_idx + len(target_lines):]
            updated = "\n".join(new_lines) + ("\n" if normalized.endswith("\n") else "")
    
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
    ignored_dirs = {
        '.venv', 'node_modules', '.git', '__pycache__', 'dist', '.gemini',
        '.pytest_cache', '.mypy_cache', '.idea', 'build', 'tests'
    }
    ignored_extensions = {'.db', '.doc', '.docx', '.pdf', '.pyc', '.env'}
    tree: list[str] = []

    def walk(dir_path: Path, depth: int):
        if depth > max_depth:
            return
        try:
            entries = sorted(dir_path.iterdir(), key=lambda p: (p.is_file(), p.name))
        except PermissionError:
            return
        for entry in entries:
            if entry.name in ignored_dirs or any(part in ignored_dirs for part in entry.parts):
                continue
            if entry.suffix in ignored_extensions or entry.name.startswith('.env'):
                continue
            rel = str(entry.relative_to(root_path)).replace('\\', '/')
            if entry.is_dir():
                tree.append(f"{rel}/")
                walk(entry, depth + 1)
            else:
                tree.append(rel)

    walk(root_path, 0)
    return tree
