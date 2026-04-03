"""Tool implementations for the coding agent CLI."""

import json
import os
import subprocess
import time
from typing import Any, Optional

from rich.console import Console

console = Console()


def _sanitize_path(path: str) -> str:
    """Prevent escaping the working directory."""
    base = os.path.abspath(os.getcwd())
    target = os.path.abspath(os.path.join(base, path))
    # Allow paths within the current working tree
    if not target.startswith(base):
        raise ValueError(f"Path {path} is outside the allowed workspace")
    return target


def read_file(path: str, offset: int = 1, limit: int = 100) -> str:
    try:
        target = _sanitize_path(path)
        if not os.path.exists(target):
            return f"Error: file not found: {path}"
        if os.path.isdir(target):
            return f"Error: {path} is a directory"
        with open(target, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
        start = max(0, offset - 1)
        end = min(len(lines), start + limit)
        selected = lines[start:end]
        header = f"--- {path} (lines {start+1}-{end} of {len(lines)}) ---\n"
        return header + "".join(selected)
    except Exception as exc:
        return f"Error reading {path}: {exc}"


def write_file(path: str, content: str, mode: str = "overwrite") -> str:
    try:
        target = _sanitize_path(path)
        os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
        file_mode = "a" if mode == "append" else "w"
        with open(target, file_mode, encoding="utf-8") as f:
            f.write(content)
        return f"Success: wrote to {path} ({mode})"
    except Exception as exc:
        return f"Error writing {path}: {exc}"


def shell(command: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=os.getcwd(),
        )
        out = result.stdout or ""
        err = result.stderr or ""
        lines = []
        if out:
            lines.append("STDOUT:\n" + out)
        if err:
            lines.append("STDERR:\n" + err)
        if not lines:
            lines.append("(no output)")
        lines.append(f"Exit code: {result.returncode}")
        return "\n".join(lines)
    except subprocess.TimeoutExpired:
        return f"Error: command timed out after {timeout}s"
    except Exception as exc:
        return f"Error running command: {exc}"


def list_directory(path: str = ".") -> str:
    try:
        target = _sanitize_path(path)
        if not os.path.isdir(target):
            return f"Error: {path} is not a directory"
        entries = os.listdir(target)
        lines = [f"Directory: {path}"]
        for e in sorted(entries):
            full = os.path.join(target, e)
            kind = "dir" if os.path.isdir(full) else "file"
            size = os.path.getsize(full) if kind == "file" else "-"
            lines.append(f"  [{kind:4}] {e:<40} {size}")
        return "\n".join(lines)
    except Exception as exc:
        return f"Error listing {path}: {exc}"


def grep(pattern: str, path: str = ".", glob: Optional[str] = None) -> str:
    try:
        import fnmatch
        target = _sanitize_path(path)
        matches = []
        if os.path.isfile(target):
            files = [target]
        else:
            files = []
            for root, _, filenames in os.walk(target):
                for name in filenames:
                    if glob and not fnmatch.fnmatch(name, glob):
                        continue
                    files.append(os.path.join(root, name))
        for fp in files[:50]:  # limit scanned files
            try:
                with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                    for i, line in enumerate(f, 1):
                        if pattern in line:
                            rel = os.path.relpath(fp, os.getcwd())
                            matches.append(f"{rel}:{i}: {line.rstrip()}")
                            if len(matches) >= 100:
                                break
            except Exception:
                continue
            if len(matches) >= 100:
                break
        if not matches:
            return f"No matches for '{pattern}'"
        return "\n".join(matches[:100])
    except Exception as exc:
        return f"Error searching: {exc}"


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file. Returns the specified range of lines.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "offset": {"type": "integer", "description": "Line number to start from (1-indexed)", "default": 1},
                    "limit": {"type": "integer", "description": "Max lines to read", "default": 100},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or append text to a file. Creates parent directories if needed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the file"},
                    "content": {"type": "string", "description": "Text content to write"},
                    "mode": {"type": "string", "enum": ["overwrite", "append"], "default": "overwrite"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "shell",
            "description": "Execute a shell command in the current working directory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to run"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": "List files and subdirectories in a given path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path to the directory", "default": "."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "grep",
            "description": "Search for a text pattern in files under a path.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string", "description": "Text pattern to search for"},
                    "path": {"type": "string", "description": "Relative path to search in", "default": "."},
                    "glob": {"type": "string", "description": "Optional file glob filter, e.g. *.py", "default": None},
                },
                "required": ["pattern"],
            },
        },
    },
]


TOOL_MAP = {
    "read_file": read_file,
    "write_file": write_file,
    "shell": shell,
    "list_directory": list_directory,
    "grep": grep,
}


def execute_tool(name: str, arguments: dict) -> str:
    func = TOOL_MAP.get(name)
    if not func:
        return f"Error: unknown tool {name}"
    try:
        return func(**arguments)
    except Exception as exc:
        return f"Error executing {name}: {exc}"
