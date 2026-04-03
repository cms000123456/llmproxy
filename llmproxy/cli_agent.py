"""Agent loop for the coding CLI."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table

from .tools import TOOL_DEFINITIONS, execute_tool

console = Console()

SYSTEM_PROMPT = """You are a helpful coding assistant with direct access to the user's local filesystem.
You can read files, write files, run shell commands, list directories, and search code.

Guidelines:
- Prefer reading files before editing them.
- When writing code, produce complete, working files.
- Keep shell commands safe and relevant.
- If a task spans multiple steps, use tools iteratively and confirm each step.
- Always summarize what you did in your final response.
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
    for file_path in sorted(project_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            data = json.loads(file_path.read_text())
            sessions.append({
                "session_id": file_path.stem,
                "created": data.get("created", "Unknown"),
                "updated": data.get("updated", "Unknown"),
                "preview": data.get("preview", "No preview"),
                "message_count": len(data.get("messages", [])),
                "usage": data.get("usage", {"prompt_tokens": 0, "completion_tokens": 0}),
            })
        except Exception:
            continue
    return sessions


def _save_session(project_id: str, session_id: str, messages: list, usage: dict = None, preview: str = ""):
    """Save a conversation session to disk."""
    conv_path = _get_conversation_path(project_id, session_id)
    now = datetime.now().isoformat()
    
    # Try to get existing data to preserve creation time
    created = now
    if conv_path.exists():
        try:
            existing = json.loads(conv_path.read_text())
            created = existing.get("created", now)
        except Exception:
            pass
    
    data = {
        "session_id": session_id,
        "created": created,
        "updated": now,
        "project_path": os.getcwd(),
        "preview": preview[:200] if preview else "",
        "messages": messages,
        "usage": usage or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
    }
    
    conv_path.write_text(json.dumps(data, indent=2))


def _load_session(project_id: str, session_id: str) -> tuple[Optional[list[dict]], Optional[dict]]:
    """Load a conversation session from disk.
    
    Returns: (messages, usage) tuple
    """
    conv_path = _get_conversation_path(project_id, session_id)
    if not conv_path.exists():
        return None, None
    
    try:
        data = json.loads(conv_path.read_text())
        return data.get("messages", []), data.get("usage")
    except Exception:
        return None, None


def _select_session(project_id: str) -> Optional[str]:
    """Interactive session selector. Returns session_id or None for new session."""
    sessions = _list_sessions(project_id)
    
    if not sessions:
        return None
    
    console.print(Panel.fit(
        "[bold cyan]Resume Previous Session?[/bold cyan]\n"
        "Select a session to resume, or start a new one.",
        title="Sessions"
    ))
    
    table = Table(show_header=True, header_style="bold")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Created", style="dim")
    table.add_column("Updated", style="dim")
    table.add_column("Tokens", justify="right")
    table.add_column("Preview", style="green")
    
    table.add_row("0", "—", "—", "—", "[dim]Start new session[/dim]")
    
    for i, session in enumerate(sessions[:10], 1):  # Show last 10
        usage = session.get("usage", {})
        total_tokens = usage.get("total_tokens", 0)
        token_str = f"{total_tokens:,}" if total_tokens else "—"
        
        table.add_row(
            str(i),
            session["created"][:16].replace("T", " ") if session["created"] != "Unknown" else "—",
            session["updated"][:16].replace("T", " ") if session["updated"] != "Unknown" else "—",
            token_str,
            session["preview"][:50] + "..." if len(session["preview"]) > 50 else session["preview"] or "[dim]No preview[/dim]",
        )
    
    console.print(table)
    
    choice = IntPrompt.ask("Select session", default=0, show_default=True)
    
    if choice == 0 or choice > len(sessions):
        return None
    
    return sessions[choice - 1]["session_id"]


def _format_usage(usage: dict, model: str) -> str:
    """Format usage statistics with cost estimation."""
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    total_tokens = usage.get("total_tokens", prompt_tokens + completion_tokens)
    
    # Get pricing for model
    pricing = PRICING.get(model, PRICING["default"])
    input_cost = (prompt_tokens / 1_000_000) * pricing["input"]
    output_cost = (completion_tokens / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost
    
    return (
        f"[dim]Tokens: {total_tokens:,} "
        f"(↑{prompt_tokens:,} ↓{completion_tokens:,}) "
        f"| Est. cost: ${total_cost:.4f}[/dim]"
    )


class Agent:
    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        api_key: Optional[str] = None,
        model: str = "kimi-for-coding",
        session_id: Optional[str] = None,
        resume: bool = False,
    ):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )
        self.model = model
        self.project_id = _get_project_id()
        self.max_tool_rounds = 30
        
        # Usage tracking
        self.usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        
        # Determine session ID
        if session_id:
            self.session_id = session_id
        elif resume:
            # Interactive selection
            selected = _select_session(self.project_id)
            self.session_id = selected if selected else self._generate_session_id()
        else:
            self.session_id = self._generate_session_id()
        
        # Load or initialize messages
        loaded_messages, loaded_usage = _load_session(self.project_id, self.session_id) if resume or session_id else (None, None)
        if loaded_messages:
            self.messages = loaded_messages
            if loaded_usage:
                self.usage = loaded_usage
            console.print(f"[dim]↳ Resumed session: {self.session_id[:16]}... ({self.usage['total_tokens']:,} tokens)[/dim]")
        else:
            self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    def _generate_session_id(self) -> str:
        """Generate a new unique session ID."""
        now = datetime.now()
        return f"{now.strftime('%Y%m%d_%H%M%S')}_{os.urandom(4).hex()}"
    
    def _get_first_user_message(self) -> str:
        """Get the first user message for preview."""
        for msg in self.messages:
            if msg.get("role") == "user":
                return msg.get("content", "")[:100]
        return ""
    
    def _save(self):
        """Persist current conversation state."""
        preview = self._get_first_user_message()
        _save_session(self.project_id, self.session_id, self.messages, self.usage, preview)
    
    def _update_usage(self, response):
        """Update usage statistics from response."""
        if hasattr(response, 'usage') and response.usage:
            usage = response.usage
            self.usage["prompt_tokens"] += getattr(usage, 'prompt_tokens', 0)
            self.usage["completion_tokens"] += getattr(usage, 'completion_tokens', 0)
            self.usage["total_tokens"] = (
                self.usage["prompt_tokens"] + self.usage["completion_tokens"]
            )
    
    def get_usage_summary(self) -> str:
        """Get formatted usage summary."""
        return _format_usage(self.usage, self.model)
    
    def chat(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})
        
        # Save after adding user message
        self._save()

        for _ in range(self.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.3,
            )
            
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

            # Execute tools and append results
            for tc in tool_calls:
                name = tc.function.name
                args = json.loads(tc.function.arguments)
                console.print(f"[dim]→ Tool call: {name}({json.dumps(args)})[/dim]")
                result = execute_tool(name, args)
                # Some providers (e.g. kimi-for-coding) omit tool_call_id; generate a fallback
                tool_call_id = tc.id or f"call_{hash(json.dumps(args, sort_keys=True))}"
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                })
                # Save after tool results
                self._save()

        return "(reached max tool rounds without final answer)"
