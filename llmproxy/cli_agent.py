from __future__ import annotations

"""Agent loop for the coding CLI."""

import asyncio
import json
import os
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx
from openai import OpenAI
from rich.console import Console
from rich.prompt import Prompt

from .tools import TOOL_DEFINITIONS, execute_tool

console = Console()

# Debug logging - set LLM_AGENT_DEBUG=1 to see raw LLM interactions
DEBUG = os.getenv("LLM_AGENT_DEBUG", "").lower() in ("1", "true", "yes", "on")

# Default AGENT.md content for /init command
DEFAULT_AGENT_MD = """# Project Agent Configuration

This file contains project-specific instructions for the coding agent.
Edit this file to customize how the agent works with your project.

## Project Context

<!--
Describe what this project does, its purpose, and high-level architecture.
Example: "A web API for managing user data with FastAPI and PostgreSQL"
-->

[Your project description here]

## Technology Stack

<!--
List the main technologies, frameworks, and versions the project uses.
This helps the agent use correct syntax and patterns.
-->

- **Language**: [e.g., Python 3.11, TypeScript 5.0, etc.]
- **Framework**: [e.g., FastAPI, React, Django, etc.]
- **Database**: [e.g., PostgreSQL, MongoDB, etc.]
- **Key Dependencies**: [e.g., pydantic, sqlalchemy, etc.]

## Code Style Guidelines

<!--
Project-specific coding conventions not covered by general guidelines.
-->

- [e.g., Use dependency injection for database sessions]
- [e.g., All API routes must have response models]
- [e.g., Prefer async/await for I/O operations]

## Common Tasks

<!--
Typical workflows or patterns for this project.
The agent will follow these when appropriate.
-->

1. [e.g., Run migrations before committing schema changes]
2. [e.g., Update tests when modifying API endpoints]
3. [e.g., Check AGENT.md for project context]

## Important Files/Directories

<!--
Key files or directories the agent should know about.
-->

- `src/` - Main source code
- `tests/` - Test files
- `docs/` - Documentation
- `[other important paths]`

## Project-Specific Notes

<!--
Any other context that would help the agent work effectively with this codebase.
-->

- [Any specific conventions, gotchas, or preferences]
"""


def _load_agent_md() -> str:
    """Load AGENT.md from current directory if it exists."""
    agent_md_path = Path("AGENT.md")
    if agent_md_path.exists():
        try:
            content = agent_md_path.read_text(encoding="utf-8")
            return f"\n\n# PROJECT-SPECIFIC CONTEXT (from AGENT.md)\n\n{content}"
        except Exception:
            return ""
    return ""


def _init_agent_md() -> bool:
    """Create default AGENT.md if it doesn't exist. Returns True if created."""
    agent_md_path = Path("AGENT.md")
    if agent_md_path.exists():
        return False
    try:
        agent_md_path.write_text(DEFAULT_AGENT_MD, encoding="utf-8")
        return True
    except Exception:
        return False


def _fetch_proxy_savings(base_url: str) -> dict:
    """Fetch token savings from proxy metrics endpoint."""
    try:
        # Extract base URL without /v1 path
        metrics_url = base_url.replace("/v1", "").rstrip("/") + "/metrics"
        resp = httpx.get(metrics_url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            metrics = data.get("metrics", {})
            return {
                "upstream_tokens": metrics.get("tokens_upstream", 0),
                "downstream_tokens": metrics.get("tokens_downstream", 0),
                "tokens_saved": metrics.get("tokens_saved", 0),
                "cache_hits": metrics.get("cache_hits", 0),
                "cache_hit_rate": metrics.get("cache_hit_rate", 0),
                "requests_total": metrics.get("requests_total", 0),
            }
    except Exception:
        pass
    return {}


SYSTEM_PROMPT_BASE = """You are a helpful coding assistant with direct access to the user's local filesystem.
You can read files, write files, run shell commands, list directories, and search code.

CURRENT VERSIONS (as of 2026-04-04):
- Python: 3.14 is the current version (3.14.0 released Oct 2025)
- Docker base images: python:3.14-slim is available and recommended
- Node.js: 22 LTS is current
- Key Python packages: FastAPI 0.115+, Pydantic 2.10+, pytest 8.3+, ruff 0.9+
- Ubuntu: 24.04 LTS is current (noble)

Guidelines:
- **EXPLAIN YOUR REASONING**: Before taking action, briefly explain what you plan to do and why.
- **SUMMARIZE CHANGES**: When writing code, don't dump large blocks. Instead, explain what changed and why, showing only the key parts.
- Prefer reading files before editing them.
- When writing code, produce complete, working files.
- Keep shell commands safe and relevant.
- If a task spans multiple steps, use tools iteratively and confirm each step.
- Always summarize what you did in your final response.
- When creating reports or documentation, use the current date (ask if unsure).
- Do not invent or hallucinate file contents - always read files first.
- Be concise in your responses and tool usage.
- Use CURRENT versions from the list above, not outdated knowledge from your training data.

When making code changes:
1. First explain the approach and what files you'll modify
2. Describe the key changes (not line-by-line)
3. Show a brief diff-style summary of the most important changes
4. Confirm the file was written successfully
"""

# Build full system prompt with AGENT.md if it exists
SYSTEM_PROMPT = SYSTEM_PROMPT_BASE + _load_agent_md()

UNDERSTANDING_PROMPT = """You are a helpful coding assistant. The user wants you to perform a task.

Analyze their request and respond with a specific, actionable plan:

**What I'll do:**
- Briefly state the goal in your own words

**Files/Tools I'll use:**
- List specific files you plan to read/modify
- List shell commands or searches you plan to run

**Approach:**
- Describe your planned approach (2-3 bullet points max)
- Explain your reasoning for this approach

**Clarifications needed:** (only if unclear)
- Ask specific questions if the request is ambiguous

Be concrete and specific. Don't use generic phrases like "I'll help you with that" or "I understand you want me to do something." Actually describe what you will do and why.
"""

# Store conversations outside the repo to avoid git contamination
CONVERSATIONS_DIR = Path.home() / ".local" / "share" / "llmproxy" / "conversations"

# Pricing per 1M tokens (approximate for Kimi/Moonshot)
# These are conservative estimates - adjust based on actual pricing
PRICING = {
    "kimi-for-coding": {"input": 0.50, "output": 2.00},
    "moonshot-v1-8k": {"input": 0.50, "output": 2.00},
    "moonshot-v1-32k": {"input": 0.50, "output": 2.00},
    "moonshot-v1-128k": {"input": 0.50, "output": 2.00},
    "gpt-4": {"input": 30.00, "output": 60.00},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "default": {"input": 0.50, "output": 2.00},
}


def _get_project_id() -> str:
    """Generate a unique ID for the current project/workspace."""
    cwd = os.getcwd()
    # Use the directory name + full path hash for uniqueness
    dir_name = os.path.basename(cwd)
    path_hash = hash(cwd) & 0xFFFFFFFF
    return f"{dir_name}_{path_hash:08x}"


def _get_conversation_path(project_id: str, session_id: str) -> Path:
    """Get the file path for a conversation."""
    project_dir = CONVERSATIONS_DIR / project_id
    project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir / f"{session_id}.json"


def _list_sessions(project_id: str) -> list[dict]:
    """List all saved sessions for a project."""
    project_dir = CONVERSATIONS_DIR / project_id
    if not project_dir.exists():
        return []

    sessions = []
    for file_path in sorted(
        project_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True
    ):
        try:
            data = json.loads(file_path.read_text())
            sessions.append(
                {
                    "session_id": data.get("session_id", file_path.stem),
                    "created": data.get("created", "Unknown"),
                    "updated": data.get("updated", "Unknown"),
                    "message_count": len(data.get("messages", [])),
                    "preview": data.get("messages", [{}])[0].get("content", "")
                    if data.get("messages")
                    else "",
                    "usage": data.get("usage", {}),
                }
            )
        except Exception:
            continue
    return sessions


def _debug_log(title: str, data: Any) -> None:
    """Log debug information if DEBUG is enabled."""
    if not DEBUG:
        return
    
    # Print to stderr to avoid interfering with normal output
    import sys
    
    print(f"\n{'='*60}", file=sys.stderr)
    print(f"[DEBUG] {title}", file=sys.stderr)
    print("="*60, file=sys.stderr)
    
    if isinstance(data, list):
        # Log message list (conversation)
        for i, msg in enumerate(data):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            tool_calls = msg.get("tool_calls")
            
            print(f"\n  [{i}] {role.upper()}:", file=sys.stderr)
            if content:
                # Truncate long content
                content_str = str(content)
                if len(content_str) > 500:
                    content_str = content_str[:500] + "... [truncated]"
                for line in content_str.split("\n"):
                    print(f"      {line}", file=sys.stderr)
            if tool_calls:
                print(f"      tool_calls: {json.dumps(tool_calls, indent=2)}", file=sys.stderr)
    elif isinstance(data, dict):
        # Log dictionary (response)
        print(json.dumps(data, indent=2, default=str), file=sys.stderr)
    else:
        print(str(data), file=sys.stderr)
    
    print("="*60 + "\n", file=sys.stderr)


class Agent:
    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        api_key: str = "",
        model: str = "kimi-for-coding",
        max_tool_rounds: int = 10,
        session_id: str | None = None,
        resume: bool = False,
        debug: bool = False,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.base_url = base_url
        self.debug = debug or DEBUG

        # Session management
        self.project_id = _get_project_id()
        self.session_id = session_id or self._generate_session_id()

        # Load or initialize conversation
        if resume:
            self._load_or_resume()
        else:
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            self._save()

    def _generate_session_id(self) -> str:
        """Generate a new session ID based on timestamp."""
        now = datetime.now()
        return now.strftime("%Y%m%d_%H%M%S") + f"_{os.urandom(4).hex()}"

    def _get_save_path(self) -> Path:
        """Get the file path for saving this session."""
        return _get_conversation_path(self.project_id, self.session_id)

    def _load_or_resume(self) -> None:
        """Load existing session or show selector if multiple exist."""
        sessions = _list_sessions(self.project_id)

        if not sessions:
            # No existing sessions, start fresh
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            console.print("[dim]No saved sessions found. Starting fresh...[/dim]")
            self._save()
            return

        # If specific session_id provided, load it
        if hasattr(self, "session_id") and any(
            s["session_id"] == self.session_id for s in sessions
        ):
            self._load()
            return

        # Otherwise show session selector
        console.print("\n[bold cyan]Available Sessions:[/bold cyan]")
        for i, session in enumerate(sessions[:10], 1):  # Show top 10
            usage = session.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            preview = (
                session["preview"][:50] + "..."
                if len(session["preview"]) > 50
                else session["preview"]
            )
            console.print(
                f"  [cyan]{i}.[/cyan] {session['session_id']} | {tokens:,} tokens | {preview}"
            )

        console.print("  [cyan]n.[/cyan] Start new session")

        choice = Prompt.ask(
            "Select session",
            choices=[str(i) for i in range(1, min(len(sessions), 10) + 1)] + ["n"],
            default="n",
        )

        if choice == "n":
            self.session_id = self._generate_session_id()
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            self._save()
        else:
            self.session_id = sessions[int(choice) - 1]["session_id"]
            self._load()

    def _load(self) -> None:
        """Load conversation from disk."""
        try:
            path = self._get_save_path()
            if path.exists():
                data = json.loads(path.read_text())
                self.messages = data.get("messages", [{"role": "system", "content": SYSTEM_PROMPT}])
                self.usage = data.get(
                    "usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
                )
                console.print(f"[dim]Resumed session: {self.session_id}[/dim]")
            else:
                self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        except Exception as e:
            console.print(f"[dim red]Failed to load session: {e}. Starting fresh.[/dim red]")
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            self._save()

    def _save(self) -> None:
        """Save conversation to disk."""
        try:
            path = self._get_save_path()
            data = {
                "session_id": self.session_id,
                "project_id": self.project_id,
                "created": getattr(self, "_created", datetime.now().isoformat()),
                "updated": datetime.now().isoformat(),
                "messages": self.messages,
                "usage": self.usage,
            }
            if not hasattr(self, "_created"):
                self._created = data["created"]
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            console.print(f"[dim red]Failed to save session: {e}[/dim red]")

    def _update_usage(self, response: object) -> None:
        """Update token usage from API response."""
        usage = response.usage
        if usage:
            self.usage["input_tokens"] += usage.prompt_tokens or 0
            self.usage["output_tokens"] += usage.completion_tokens or 0
            self.usage["total_tokens"] += usage.total_tokens or 0

    def get_usage_summary(self) -> str:
        """Get formatted usage summary."""
        total = self.usage.get("total_tokens", 0)
        inp = self.usage.get("input_tokens", 0)
        out = self.usage.get("output_tokens", 0)

        # Calculate estimated cost
        pricing = PRICING.get(self.model, PRICING["default"])
        input_cost = (inp / 1_000_000) * pricing["input"]
        output_cost = (out / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        cost_str = f"~${total_cost:.2f}" if total_cost >= 0.01 else f"~${total_cost:.3f}"

        return f"[dim]Tokens: {total:,} ({inp:,}↑ {out:,}↓) | Est: {cost_str}[/dim]"

    def get_proxy_savings(self) -> str:
        """Get proxy token savings summary."""
        savings = _fetch_proxy_savings(self.base_url)
        if not savings:
            return "[dim]Proxy: not available[/dim]"

        saved = savings.get("tokens_saved", 0)
        cache_hits = savings.get("cache_hits", 0)
        cache_rate = savings.get("cache_hit_rate", 0)

        # Calculate cost savings (rough estimate)
        pricing = PRICING.get(self.model, PRICING["default"])
        saved_cost = (saved / 1_000_000) * pricing["input"]

        parts = []
        if saved > 0:
            parts.append(f"{saved:,} tokens filtered")
        if cache_hits > 0:
            parts.append(f"{cache_hits} cached")
        if cache_rate > 0:
            parts.append(f"{cache_rate:.0%} cache hit")

        summary = " | ".join(parts) if parts else "No savings yet"
        return f"[dim green]Proxy saved: {summary} (~${saved_cost:.2f})[/dim green]"

    def _print_tool_call(self, name: str, args: dict) -> None:
        """Pretty-print a tool call with context about what it's doing."""
        if name == "read_file":
            path = args.get("path", "unknown")
            offset = args.get("offset", 1)
            limit = args.get("limit", 100)
            console.print(
                f"[dim blue]📖 Reading[/dim blue] [dim]{path} (lines {offset}-{offset + limit - 1})...[/dim]"
            )

        elif name == "write_file":
            path = args.get("path", "unknown")
            mode = args.get("mode", "overwrite")
            content = args.get("content", "")
            lines = content.count("\n") + 1 if content else 0
            action = "Creating" if mode == "overwrite" else "Appending to"
            console.print(
                f"[dim yellow]✏️  {action}[/dim yellow] [dim]{path} ({lines} lines)...[/dim]"
            )

        elif name == "shell":
            command = args.get("command", "")
            timeout = args.get("timeout", 30)
            # Truncate long commands
            cmd_display = command[:60] + "..." if len(command) > 60 else command
            console.print(
                f"[dim magenta]⚡ Running[/dim magenta] [dim]{cmd_display} (timeout: {timeout}s)[/dim]"
            )

        elif name == "list_directory":
            path = args.get("path", ".")
            console.print(f"[dim green]📁 Listing directory[/dim green] [dim]{path}/...[/dim]")

        elif name == "grep":
            pattern = args.get("pattern", "")
            path = args.get("path", ".")
            glob = args.get("glob")
            glob_str = f" ({glob})" if glob else ""
            console.print(
                f"[dim cyan]🔍 Searching[/dim cyan] [dim]'{pattern}' in {path}{glob_str}...[/dim]"
            )

        elif name == "get_datetime":
            tz = args.get("timezone_offset", "UTC")
            fmt = args.get("format", "iso")
            console.print(f"[dim white]🕐 Getting date/time[/dim white] [dim]({tz}, {fmt})...[/dim]")

        elif name == "search_web":
            query = args.get("query", "")
            limit = args.get("limit", 5)
            console.print(f"[dim blue]🌐 Searching web[/dim blue] [dim]'{query}' (max {limit} results)...[/dim]")

        elif name == "fetch_url":
            url = args.get("url", "")
            console.print(f"[dim blue]📥 Fetching URL[/dim blue] [dim]{url[:60]}...[/dim]")

        elif name == "glob_files":
            pattern = args.get("pattern", "")
            console.print(f"[dim cyan]🔍 Finding files[/dim cyan] [dim]pattern: {pattern}...[/dim]")

        elif name == "delete_file":
            path = args.get("path", "")
            console.print(f"[dim red]🗑️  Deleting file[/dim red] [dim]{path}...[/dim]")

        elif name == "python":
            code = args.get("code", "")
            lines = code.count("\n") + 1
            console.print(f"[dim yellow]🐍 Running Python[/dim yellow] [dim]({lines} lines)...[/dim]")

        elif name == "copy_file":
            src = args.get("source", "")
            dst = args.get("destination", "")
            console.print(f"[dim blue]📋 Copying file[/dim blue] [dim]{src} → {dst}...[/dim]")

        elif name == "move_file":
            src = args.get("source", "")
            dst = args.get("destination", "")
            console.print(f"[dim magenta]📦 Moving file[/dim magenta] [dim]{src} → {dst}...[/dim]")

        elif name == "http_request":
            method = args.get("method", "GET")
            url = args.get("url", "")
            console.print(f"[dim blue]🌐 HTTP {method}[/dim blue] [dim]{url[:60]}...[/dim]")

        elif name == "git":
            cmd = args.get("command", "")
            console.print(f"[dim cyan]📎 git {cmd}[/dim cyan]")

        else:
            # Generic fallback
            console.print(f"[dim]→ Tool call: {name}({json.dumps(args)})[/dim]")

    def _print_tool_result(self, name: str, result: str) -> None:
        """Print a brief summary of the tool result."""
        # Truncate result for display
        max_display_len = 200

        if name == "read_file":
            # Show file size info from the header line
            first_line = result.split("\n")[0] if result else ""
            if "lines" in first_line:
                console.print(f"[dim green]   ✓ {first_line}[/dim green]")
            else:
                display = (
                    result[:max_display_len] + "..." if len(result) > max_display_len else result
                )
                console.print(f"[dim]{display}[/dim]")

        elif name == "write_file":
            # Usually just "Success: wrote to ..."
            console.print(f"[dim green]   ✓ {result}[/dim green]")

        elif name == "shell":
            # Show exit code and brief output
            lines = result.split("\n")
            exit_code_line = [line for line in lines if line.startswith("Exit code:")]
            if exit_code_line:
                exit_code = exit_code_line[0].split(":")[1].strip()
                status = "✓" if exit_code == "0" else "✗"
                color = "green" if exit_code == "0" else "red"
                console.print(f"[dim {color}]   {status} Exit code: {exit_code}[/dim {color}]")

            # Show first line of output if any
            stdout_lines = [line for line in lines if line.startswith("STDOUT:")]
            if stdout_lines and len(stdout_lines[0]) > 8:
                output = stdout_lines[0][7:].strip()[:80]
                if output:
                    console.print(f"[dim]   → {output}...[/dim]")

        elif name == "list_directory":
            # Count entries
            lines = result.split("\n")
            entries = len([line for line in lines if line.strip().startswith("[")])
            console.print(f"[dim green]   ✓ Found {entries} items[/dim green]")

        elif name == "grep":
            # Count matches
            matches = len([line for line in result.split("\n") if line.strip()])
            if result.startswith("No matches"):
                console.print("[dim yellow]   ⚠ No matches found[/dim yellow]")
            else:
                console.print(f"[dim green]   ✓ {min(matches, 100)} matches found[/dim green]")

        elif name == "get_datetime":
            # Show the date/time result
            console.print(f"[dim green]   ✓ {result[:80]}[/dim green]")

        elif name == "search_web":
            # Count search results
            if "Error" in result:
                console.print(f"[dim red]   ✗ {result[:80]}[/dim red]")
            else:
                # Count results (they're numbered like "1. Title")
                import re
                count = len(re.findall(r'^\d+\.', result, re.MULTILINE))
                console.print(f"[dim green]   ✓ Found {count} results[/dim green]")

        elif name == "fetch_url":
            # Show fetched URL
            if "Error" in result:
                console.print(f"[dim red]   ✗ Failed to fetch URL[/dim red]")
            else:
                lines = result.split("\n")
                title_line = [l for l in lines if l.startswith("Title:")]
                if title_line:
                    title = title_line[0].replace("Title:", "").strip()[:60]
                    console.print(f"[dim green]   ✓ Fetched: {title}...[/dim green]")
                else:
                    console.print(f"[dim green]   ✓ URL fetched[/dim green]")

        elif name == "glob_files":
            # Count matches
            if "No files" in result:
                console.print("[dim yellow]   ⚠ No files found[/dim yellow]")
            else:
                count = result.count("\n  ") - 1  # Count indented lines
                console.print(f"[dim green]   ✓ Found {max(0, count)} files[/dim green]")

        elif name == "delete_file":
            if result.startswith("Success"):
                console.print("[dim green]   ✓ File deleted[/dim green]")
            else:
                console.print(f"[dim red]   ✗ {result}[/dim red]")

        elif name == "python":
            if "Error" in result:
                console.print("[dim red]   ✗ Python execution failed[/dim red]")
            else:
                console.print("[dim green]   ✓ Code executed[/dim green]")

        elif name == "copy_file":
            if result.startswith("Success"):
                console.print("[dim green]   ✓ File copied[/dim green]")
            else:
                console.print(f"[dim red]   ✗ {result}[/dim red]")

        elif name == "move_file":
            if result.startswith("Success"):
                console.print("[dim green]   ✓ File moved[/dim green]")
            else:
                console.print(f"[dim red]   ✗ {result}[/dim red]")

        elif name == "http_request":
            if "Error" in result:
                console.print("[dim red]   ✗ Request failed[/dim red]")
            else:
                # Extract status code
                status_line = [l for l in result.split("\n") if l.startswith("Status:")]
                if status_line:
                    status = status_line[0].replace("Status:", "").strip()
                    color = "green" if status.startswith("2") else "yellow" if status.startswith("3") else "red"
                    console.print(f"[dim {color}]   ✓ Status {status}[/dim {color}]")
                else:
                    console.print("[dim green]   ✓ Request completed[/dim green]")

        elif name == "git":
            if "Error" in result:
                console.print("[dim red]   ✗ Git command failed[/dim red]")
            else:
                console.print("[dim green]   ✓ Git command completed[/dim green]")

        else:
            # Generic fallback
            display = result[:max_display_len] + "..." if len(result) > max_display_len else result
            console.print(f"[dim]   → {display}[/dim]")

    def get_understanding(self, user_input: str) -> str:
        """Get a brief summary of understanding before executing."""
        # Create a temporary message list for the understanding prompt
        temp_messages = [
            {"role": "system", "content": UNDERSTANDING_PROMPT},
            {"role": "user", "content": user_input},
        ]

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=temp_messages,
                temperature=0.3,
                max_tokens=200,  # Keep it brief
            )

            # Track usage for understanding request
            self._update_usage(response)

            content = response.choices[0].message.content
            if (
                content
                and content.strip()
                and content.strip().lower()
                not in (
                    "i'll help you with that.",
                    "i'll help you with that",
                    "i can help you with that.",
                    "i can help you with that",
                )
            ):
                return content.strip()
        except Exception:
            pass

        # Fallback: show the actual user request (truncated if too long)
        user_input = user_input.strip()
        if len(user_input) > 200:
            user_input = user_input[:200] + "..."
        return f"**You asked:** {user_input}"

    def chat(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        # Save after adding user message
        self._save()
        
        # Debug: log messages being sent
        _debug_log(f"SENDING TO LLM ({self.model})", self.messages)

        for round_num in range(self.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.3,
            )
            
            # Debug: log raw response
            if self.debug:
                resp_dict = {
                    "id": response.id,
                    "model": response.model,
                    "usage": {
                        "prompt_tokens": response.usage.prompt_tokens if response.usage else None,
                        "completion_tokens": response.usage.completion_tokens if response.usage else None,
                    },
                    "choices": [
                        {
                            "finish_reason": c.finish_reason,
                            "message": {
                                "role": c.message.role,
                                "content": c.message.content,
                                "tool_calls": [
                                    {
                                        "id": tc.id,
                                        "function": {
                                            "name": tc.function.name,
                                            "arguments": tc.function.arguments,
                                        }
                                    } for tc in (c.message.tool_calls or [])
                                ] if c.message.tool_calls else None,
                            }
                        }
                        for c in response.choices
                    ]
                }
                _debug_log("LLM RESPONSE", resp_dict)

            # Track token usage
            self._update_usage(response)

            choice = response.choices[0]
            assistant_msg = choice.message

            # Append the assistant message (content may be None)
            self.messages.append(assistant_msg.model_dump())

            # Save after assistant response
            self._save()

            tool_calls = assistant_msg.tool_calls
            if not tool_calls or choice.finish_reason != "tool_calls":
                return assistant_msg.content or "(no response)"

            # Show which round we're on (if multiple tools will be used)
            if round_num > 0 or tool_calls:
                console.print(f"[dim]— Step {round_num + 1} —[/dim]")

            # Print assistant's reasoning if provided
            if assistant_msg.content:
                console.print(f"[dim cyan]🤔 {assistant_msg.content}[/dim cyan]")

            # Execute tools and append results
            for tc in tool_calls:
                name = tc.function.name

                # Parse JSON arguments with error handling
                raw_args = tc.function.arguments
                try:
                    args = json.loads(raw_args)
                except json.JSONDecodeError as e:
                    # Try to fix common LLM JSON issues
                    try:
                        # Handle trailing commas, single quotes, unescaped newlines
                        import re

                        fixed = raw_args.replace("'", '"')
                        fixed = re.sub(r",\s*}", "}", fixed)
                        fixed = re.sub(r",\s*]", "]", fixed)
                        args = json.loads(fixed)
                    except Exception:
                        console.print(f"[dim red]⚠️ Invalid JSON in tool call: {e}[/dim red]")
                        args = {"_raw": raw_args, "_error": str(e)}

                # Pretty-print tool call with context
                self._print_tool_call(name, args)

                result = asyncio.run(execute_tool(name, args))

                # Print brief result summary
                self._print_tool_result(name, result)

                # Some providers (e.g. kimi-for-coding) omit tool_call_id; generate a fallback
                tool_call_id = (
                    tc.id or f"call_{hash(json.dumps(args, sort_keys=True, default=str))}"
                )
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call_id,
                        "content": result,
                    }
                )
                # Save after tool results
                self._save()

        # Max rounds reached - force a final answer by retrying without tools
        console.print("[yellow]Reached max tool rounds. Requesting final answer...[/yellow]")

        # Add a system message prompting for final answer
        self.messages.append(
            {
                "role": "system",
                "content": "You have reached the maximum number of tool calls. You MUST provide a final text answer to the user now based on what you've learned. Do NOT use any more tools - respond with plain text only.",
            }
        )

        # Make final calls without tools until we get actual content
        # (Some models may still try to use tools, so we need to be persistent)
        for final_attempt in range(3):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                temperature=0.3,
            )

            # Track token usage
            self._update_usage(response)

            assistant_msg = response.choices[0].message
            self.messages.append(assistant_msg.model_dump())
            self._save()

            # Check if we got actual content (not just more tool calls)
            if assistant_msg.content and not assistant_msg.tool_calls:
                return assistant_msg.content

            # If still trying to use tools, add another reminder
            if assistant_msg.tool_calls:
                console.print(
                    "[dim yellow]⚠️ Model still trying to use tools, reminding...[/dim yellow]"
                )
                self.messages.append(
                    {
                        "role": "system",
                        "content": f"Tool calls are DISABLED. Attempt {final_attempt + 2}/3. Provide your final text answer NOW.",
                    }
                )

        # If we still don't have content after 3 attempts, return last message or fallback
        last_content = self.messages[-1].get("content", "")
        if last_content:
            return last_content

        return "⚠️ I reached the tool call limit but couldn't generate a final response. Please ask me to summarize what I found."
