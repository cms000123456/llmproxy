"""Agent loop for the coding CLI."""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt, IntPrompt
from rich.table import Table

import asyncio

from .tools import TOOL_DEFINITIONS, execute_tool

console = Console()


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

SYSTEM_PROMPT = """You are a helpful coding assistant with direct access to the user's local filesystem.
You can read files, write files, run shell commands, list directories, and search code.

Guidelines:
- Prefer reading files before editing them.
- When writing code, produce complete, working files.
- Keep shell commands safe and relevant.
- If a task spans multiple steps, use tools iteratively and confirm each step.
- Always summarize what you did in your final response.
- When creating reports or documentation, use the current date (ask if unsure).
- Do not invent or hallucinate file contents - always read files first.
- Be concise in your responses and tool usage.
"""

UNDERSTANDING_PROMPT = """You are a helpful assistant. The user is about to ask you to do something.
Your task is to briefly summarize your understanding of what they want you to do.

Respond with:
1. A 1-2 sentence summary of what you understand they're asking for
2. The key steps or actions you think you'll need to take
3. Any clarifying questions if something is unclear

Keep it concise (3-5 bullet points max). Be direct and specific.
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
                "session_id": data.get("session_id", file_path.stem),
                "created": data.get("created", "Unknown"),
                "updated": data.get("updated", "Unknown"),
                "message_count": len(data.get("messages", [])),
                "preview": data.get("messages", [{}])[0].get("content", "") if data.get("messages") else "",
                "usage": data.get("usage", {}),
            })
        except Exception:
            continue
    return sessions


class Agent:
    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        api_key: str = "",
        model: str = "kimi-for-coding",
        max_tool_rounds: int = 10,
        session_id: Optional[str] = None,
        resume: bool = False,
    ):
        self.client = OpenAI(base_url=base_url, api_key=api_key)
        self.model = model
        self.max_tool_rounds = max_tool_rounds
        self.base_url = base_url
        
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

    def _load_or_resume(self):
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
        if hasattr(self, 'session_id') and any(s["session_id"] == self.session_id for s in sessions):
            self._load()
            return
        
        # Otherwise show session selector
        console.print("\n[bold cyan]Available Sessions:[/bold cyan]")
        for i, session in enumerate(sessions[:10], 1):  # Show top 10
            usage = session.get("usage", {})
            tokens = usage.get("total_tokens", 0)
            preview = session["preview"][:50] + "..." if len(session["preview"]) > 50 else session["preview"]
            console.print(f"  [cyan]{i}.[/cyan] {session['session_id']} | {tokens:,} tokens | {preview}")
        
        console.print(f"  [cyan]n.[/cyan] Start new session")
        
        choice = Prompt.ask(
            "Select session",
            choices=[str(i) for i in range(1, min(len(sessions), 10) + 1)] + ["n"],
            default="n"
        )
        
        if choice == "n":
            self.session_id = self._generate_session_id()
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            self._save()
        else:
            self.session_id = sessions[int(choice) - 1]["session_id"]
            self._load()

    def _load(self):
        """Load conversation from disk."""
        try:
            path = self._get_save_path()
            if path.exists():
                data = json.loads(path.read_text())
                self.messages = data.get("messages", [{"role": "system", "content": SYSTEM_PROMPT}])
                self.usage = data.get("usage", {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0})
                console.print(f"[dim]Resumed session: {self.session_id}[/dim]")
            else:
                self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
                self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        except Exception as e:
            console.print(f"[dim red]Failed to load session: {e}. Starting fresh.[/dim red]")
            self.messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            self.usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
            self._save()

    def _save(self):
        """Save conversation to disk."""
        try:
            path = self._get_save_path()
            data = {
                "session_id": self.session_id,
                "project_id": self.project_id,
                "created": getattr(self, '_created', datetime.now().isoformat()),
                "updated": datetime.now().isoformat(),
                "messages": self.messages,
                "usage": self.usage,
            }
            if not hasattr(self, '_created'):
                self._created = data["created"]
            path.write_text(json.dumps(data, indent=2))
        except Exception as e:
            console.print(f"[dim red]Failed to save session: {e}[/dim red]")

    def _update_usage(self, response):
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
        
        upstream = savings.get("upstream_tokens", 0)
        downstream = savings.get("downstream_tokens", 0)
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
    
    def get_understanding(self, user_input: str) -> str:
        """Get a brief summary of understanding before executing."""
        # Create a temporary message list for the understanding prompt
        temp_messages = [
            {"role": "system", "content": UNDERSTANDING_PROMPT},
            {"role": "user", "content": user_input}
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
            if content and content.strip() and content.strip().lower() not in (
                "i'll help you with that.",
                "i'll help you with that",
                "i can help you with that.",
                "i can help you with that",
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
                result = asyncio.run(execute_tool(name, args))
                # Some providers (e.g. kimi-for-coding) omit tool_call_id; generate a fallback
                tool_call_id = tc.id or f"call_{hash(json.dumps(args, sort_keys=True))}"
                self.messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call_id,
                    "content": result,
                })
                # Save after tool results
                self._save()

        # Max rounds reached - force a final answer by retrying without tools
        console.print("[yellow]Reached max tool rounds. Requesting final answer...[/yellow]")
        
        # Add a system message prompting for final answer
        self.messages.append({
            "role": "system",
            "content": "You have reached the maximum number of tool calls. Please provide a final answer to the user now based on what you've learned. Do not use any more tools."
        })
        
        # Make one final call without tools to force a response
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
        
        return assistant_msg.content or "(agent completed but returned no response)"
