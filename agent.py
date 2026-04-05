#!/usr/bin/env python3
"""Entry point for the coding agent CLI."""

import atexit
import os
import sys
import termios
from pathlib import Path
from typing import Optional

import openai
import typer
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.styles import Style
from prompt_toolkit.formatted_text import HTML, merge_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.application import get_app
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.history import FileHistory
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from llmproxy.cli_agent import Agent, _get_project_id, _init_agent_md, _list_sessions


# Terminal state management for cleanup on exit
_original_terminal_attrs = None


def _save_terminal_state():
    """Save current terminal state for later restoration."""
    global _original_terminal_attrs
    try:
        if sys.stdin.isatty():
            _original_terminal_attrs = termios.tcgetattr(sys.stdin.fileno())
    except Exception:
        pass


def _restore_terminal():
    """Restore terminal to original state."""
    global _original_terminal_attrs
    try:
        if _original_terminal_attrs and sys.stdin.isatty():
            termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, _original_terminal_attrs)
    except Exception:
        pass
    # Fallback: reset common terminal settings
    try:
        os.system('stty sane 2>/dev/null')
    except Exception:
        pass


# Register cleanup on exit
atexit.register(_restore_terminal)


app = typer.Typer(help="Coding agent CLI — interacts with your filesystem via LLM tools.")
console = Console()

# Command categories for organized help
COMMAND_CATEGORIES = {
    "Session": [
        ("/exit", "/quit", "Save session and exit"),
        ("/clear", None, "Clear the screen"),
        ("/usage", None, "Show token usage stats"),
        ("/savings", None, "Show proxy savings"),
    ],
    "Model": [
        ("/model", "/m", "Quick switch model (by name)"),
        ("/models", None, "List and select from available models"),
        ("/model-info", "/info", "Show current model details"),
    ],
    "Settings": [
        ("/confirm", None, "Enable confirmation before tasks"),
        ("/noconfirm", None, "Disable confirmation (auto-execute)"),
    ],
    "Project": [
        ("/init", None, "Initialize AGENT.md project context"),
        ("/help", "/h", "Show this help message"),
    ],
}

# Flatten for autocompletion
SLASH_COMMANDS = []
for category, commands in COMMAND_CATEGORIES.items():
    for cmd, alias, desc in commands:
        SLASH_COMMANDS.append((cmd, desc))
        if alias:
            SLASH_COMMANDS.append((alias, f"Alias for {cmd}"))


# Completion menu style
COMPLETION_STYLE = Style.from_dict({
    'completion-menu': 'bg:#2b2b2b #ffffff',
    'completion-menu.completion': 'bg:#2b2b2b #ffffff',
    'completion-menu.completion.current': 'bg:#005f87 #ffffff bold',
    'completion-menu.meta.completion': 'bg:#2b2b2b #a0a0a0',
    'completion-menu.meta.completion.current': 'bg:#005f87 #c0c0c0',
    # Toolbar styles
    'toolbar': 'bg:#1a1a1a #e0e0e0',
    'toolbar.model': 'bg:#1a1a1a #5fd7ff bold',
    'toolbar.tokens': 'bg:#1a1a1a #e0e0e0',
    'toolbar.cost': 'bg:#1a1a1a #ffd700',
    'toolbar.savings': 'bg:#1a1a1a #5fd75f',
    'toolbar.local': 'bg:#1a1a1a #5fd7ff',
    'toolbar.gpu': 'bg:#1a1a1a #a0a0a0',
    'toolbar.confirm-on': 'bg:#1a1a1a #5fd75f',
    'toolbar.confirm-off': 'bg:#1a1a1a #d7af5f',
    'toolbar.separator': 'bg:#1a1a1a #666666',
})


class SlashCommandCompleter(Completer):
    """Enhanced completer for slash commands with visual feedback."""

    def get_completions(self, document, complete_event):
        text = document.text
        if not text or text.startswith("/"):
            # Show all commands when just "/" is typed, or filter if there's more
            search_text = text.lower()
            for cmd, desc in SLASH_COMMANDS:
                if cmd.startswith(search_text):
                    # Highlight the matched part
                    if search_text and len(search_text) > 1:
                        display = HTML(f'<b>{cmd[:len(search_text)]}</b>{cmd[len(search_text):]}')
                    else:
                        display = cmd
                    
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=display,
                        display_meta=desc,
                        style='class:completion-menu.completion',
                        selected_style='class:completion-menu.completion.current',
                    )
    
    def get_completion_for_index(self, index: int) -> Optional[str]:
        """Get command by index (for number selection)."""
        if 0 <= index < len(SLASH_COMMANDS):
            return SLASH_COMMANDS[index][0]
        return None


def _get_env(var: str, default: str = "") -> str:
    return os.getenv(var, default)


def _format_bottom_toolbar(agent, gpu_info: Optional[dict] = None, confirm_status: str = ""):
    """Format a persistent bottom toolbar for prompt_toolkit.
    
    Returns HTML-formatted text showing:
    - Model name
    - Token usage  
    - Estimated cost
    - Cache/proxy savings
    - Local savings
    - GPU info
    - Confirm status
    """
    parts = []
    
    # Model (truncated if needed)
    model = agent.model
    if len(model) > 25:
        model = model[:23] + ".."
    parts.append(("class:toolbar.model", f" {model} "))
    parts.append(("class:toolbar.separator", "│"))
    
    # Token usage
    total = agent.usage.get("total_tokens", 0)
    inp = agent.usage.get("input_tokens", 0)
    out = agent.usage.get("output_tokens", 0)
    parts.append(("class:toolbar.tokens", f" Tokens: {total:,} (↑{inp:,} ↓{out:,}) "))
    parts.append(("class:toolbar.separator", "│"))
    
    # Estimated cost
    from llmproxy.cli_agent import PRICING
    pricing = PRICING.get(agent.model, PRICING["default"])
    input_cost = (inp / 1_000_000) * pricing["input"]
    output_cost = (out / 1_000_000) * pricing["output"]
    total_cost = input_cost + output_cost
    cost_str = f"~${total_cost:.2f}" if total_cost >= 0.01 else f"~${total_cost:.3f}"
    parts.append(("class:toolbar.cost", f" Cost: {cost_str} "))
    parts.append(("class:toolbar.separator", "│"))
    
    # Proxy savings
    from llmproxy.cli_agent import _fetch_proxy_savings
    savings = _fetch_proxy_savings(agent.base_url)
    if savings:
        saved = savings.get("tokens_saved", 0)
        cache_hits = savings.get("cache_hits", 0)
        cache_rate = savings.get("cache_hit_rate", 0)
        
        saved_cost = (saved / 1_000_000) * pricing["input"]
        savings_parts = []
        if saved > 0:
            savings_parts.append(f"{saved:,} filtered")
        if cache_hits > 0:
            savings_parts.append(f"{cache_hits} cached")
        if cache_rate > 0:
            savings_parts.append(f"{cache_rate:.0%} hit")
        
        if savings_parts:
            summary = " | ".join(savings_parts)
            parts.append(("class:toolbar.savings", f" Proxy: {summary} (~${saved_cost:.2f}) "))
            parts.append(("class:toolbar.separator", "│"))
    
    # Local model savings (if using local model)
    if pricing.get("local", False) and total > 0:
        cloud_pricing = PRICING["kimi-for-coding"]
        cloud_cost = (inp / 1_000_000) * cloud_pricing["input"] + (out / 1_000_000) * cloud_pricing["output"]
        if cloud_cost >= 0.01:
            parts.append(("class:toolbar.local", f" Local saved: ~${cloud_cost:.2f} "))
            parts.append(("class:toolbar.separator", "│"))
    
    # GPU info
    if gpu_info:
        free_vram = gpu_info.get("free_vram_gb", 0)
        if free_vram > 0:
            parts.append(("class:toolbar.gpu", f" VRAM: {free_vram:.1f}G "))
            parts.append(("class:toolbar.separator", "│"))
    
    # Confirm status
    if confirm_status:
        if "ON" in confirm_status:
            parts.append(("class:toolbar.confirm-on", " ✓ Confirm "))
        else:
            parts.append(("class:toolbar.confirm-off", " ⚡ Auto "))
    
    return FormattedText(parts)


def _format_status_footer(agent, gpu_info: Optional[dict] = None, confirm_status: str = "") -> str:
    """Format a compact status footer with key stats.
    
    Returns a Rich-formatted string showing:
    - Model name (truncated)
    - Token usage
    - Estimated cost
    - Cache/proxy savings
    - GPU info if available
    """
    parts = []
    
    # Model (truncated)
    model = agent.model
    if len(model) > 20:
        model = model[:18] + ".."
    parts.append(f"[cyan]{model}[/cyan]")
    
    # Token usage
    usage = agent.get_usage_summary()
    # Extract just the numbers from the usage string
    # Format: "Tokens: 1,234 (567↑ 789↓) | Est: $0.01"
    parts.append(usage.replace("[dim]", "").replace("[/dim]", ""))
    
    # Proxy savings (show if available, even if zero)
    savings = agent.get_proxy_savings()
    if "Proxy saved:" in savings:
        # Has actual savings data
        savings_clean = savings.replace("[dim]", "").replace("[/dim]", "").replace("[dim green]", "").replace("[/dim green]", "")
        parts.append(f"[green]{savings_clean}[/green]")
    elif "Proxy: not available" not in savings:
        # Proxy is available but may have no savings yet
        savings_clean = savings.replace("[dim]", "").replace("[/dim]", "").replace("[dim green]", "").replace("[/dim green]", "")
        parts.append(f"[dim]{savings_clean}[/dim]")
    
    # Local model savings (if using local model)
    local_savings = agent.get_local_savings()
    if local_savings:
        local_savings_clean = local_savings.replace("[dim]", "").replace("[/dim]", "").replace("💰 ", "")
        parts.append(f"[cyan]{local_savings_clean}[/cyan]")
    
    # GPU info
    if gpu_info:
        free_vram = gpu_info.get("free_vram_gb", 0)
        if free_vram > 0:
            parts.append(f"[dim]VRAM: {free_vram:.1f}G[/dim]")
    
    # Confirm status
    if confirm_status:
        parts.append(confirm_status)
    
    return " | ".join(parts)


def _fetch_models(base_url: str, api_key: str = "") -> list[dict]:
    """Fetch available models from the proxy."""
    import httpx
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        resp = httpx.get(f"{base_url}/models", headers=headers, timeout=10.0)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("data", [])
    except Exception:
        pass
    return []


def _format_progress_bar(used: int, limit: int, width: int = 25) -> str:
    """Format a progress bar showing usage."""
    if not limit:
        return "━" * width
    
    ratio = min(used / limit, 1.0) if limit > 0 else 0
    filled = int(width * ratio)
    empty = width - filled
    
    # Build the bar
    if empty > 0:
        bar = "━" * filled + "╺" + "━" * (empty - 1)
    else:
        bar = "━" * width
    
    return bar


def _fetch_gpu_info(base_url: str, api_key: str = "") -> Optional[dict]:
    """Fetch GPU info from the proxy."""
    import httpx
    
    headers = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    
    try:
        resp = httpx.get(f"{base_url}/system/gpu", headers=headers, timeout=5.0)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


def _format_model_info(model_id: str, gpu_info: Optional[dict] = None) -> str:
    """Format model information for display."""
    info_lines = []
    
    # Extract model size from name
    import re
    size_match = re.search(r'(\d+\.?\d*)b', model_id.lower())
    if size_match:
        size = size_match.group(1)
        info_lines.append(f"Size: ~{size}B parameters")
    
    # Estimate VRAM
    from llmproxy.gpu_detector import calculate_model_vram
    vram = calculate_model_vram(model_id)
    info_lines.append(f"VRAM Required: ~{vram:.1f} GB")
    
    # Check if fits GPU
    if gpu_info and gpu_info.get("free_vram_gb"):
        free_vram = gpu_info["free_vram_gb"]
        if free_vram >= vram:
            info_lines.append(f"[green]✓ Fits your GPU ({free_vram:.1f} GB free)[/green]")
        else:
            info_lines.append(f"[red]✗ May not fit ({free_vram:.1f} GB free)[/red]")
    
    return "\n".join(info_lines)


def _display_models_enhanced(
    models: list[dict], 
    current_model: str, 
    gpu_info: Optional[dict] = None
) -> None:
    """Display available models with enhanced formatting."""
    
    if not models:
        console.print("[dim yellow]No models available.[/dim yellow]")
        console.print("[dim]If using local/hybrid mode, ensure Ollama is running with: ollama serve[/dim]")
        if gpu_info:
            console.print(f"\n[dim]GPU: {gpu_info.get('platform', 'unknown')} | "
                         f"VRAM: {gpu_info.get('free_vram_gb', 0):.1f} GB free[/dim]")
        return
    
    # Group models by category
    categories = {
        "Recommended": [],
        "Local (Ollama)": [],
        "Cloud": [],
        "Other": [],
    }
    
    recommended_names = set()
    if gpu_info and gpu_info.get("recommended_models"):
        recommended_names = {m["name"] for m in gpu_info["recommended_models"][:5]}
    
    for i, model in enumerate(models):
        model_id = model.get("id", "unknown")
        owned_by = model.get("owned_by", "unknown")
        
        entry = {"idx": i + 1, "id": model_id, "owned_by": owned_by}
        
        if model_id == current_model:
            entry["current"] = True
        
        if model_id in recommended_names:
            categories["Recommended"].append(entry)
        elif owned_by == "ollama" or ":" in model_id:
            categories["Local (Ollama)"].append(entry)
        elif owned_by in ["openai", "moonshot", "anthropic"]:
            categories["Cloud"].append(entry)
        else:
            categories["Other"].append(entry)
    
    # Display in tree format
    tree = Tree(f"[bold]Available Models[/bold] ([dim]{len(models)} total[/dim])")
    
    for cat_name, cat_models in categories.items():
        if not cat_models:
            continue
        
        branch = tree.add(f"[bold cyan]{cat_name}[/bold cyan]")
        
        for entry in cat_models[:20]:  # Limit per category
            idx = entry["idx"]
            model_id = entry["id"]
            is_current = entry.get("current", False)
            
            if is_current:
                branch.add(f"[bold green]{idx}. {model_id} ● current[/bold green]")
            else:
                branch.add(f"[dim]{idx}.[/dim] {model_id}")
        
        if len(cat_models) > 20:
            branch.add(f"[dim]... and {len(cat_models) - 20} more[/dim]")
    
    console.print(tree)
    
    # Show GPU and Ollama status
    status_parts = []
    if gpu_info:
        status_parts.append(f"GPU: {gpu_info.get('platform', 'unknown')} | "
                          f"VRAM: {gpu_info.get('free_vram_gb', 0):.1f} GB free")
        
        # Show Ollama status in hybrid mode
        ollama_available = gpu_info.get('ollama_available', False)
        local_mode = gpu_info.get('local_mode', False)
        
        if local_mode:
            status_parts.append("Mode: local-only")
        elif ollama_available:
            status_parts.append("Ollama: available (hybrid mode)")
        else:
            status_parts.append("Ollama: not available")
    
    if status_parts:
        console.print(f"\n[dim]{' | '.join(status_parts)}[/dim]")


def _show_help_panel(get_confirm_status) -> None:
    """Show organized help panel."""
    
    # Build help text by category
    help_lines = ["[bold cyan]Available Commands[/bold cyan]\n"]
    
    for category, commands in COMMAND_CATEGORIES.items():
        help_lines.append(f"\n[bold]{category}:[/bold]")
        for cmd, alias, desc in commands:
            if alias:
                help_lines.append(f"  [cyan]{cmd}[/cyan] ([dim]{alias}[/dim])  - {desc}")
            else:
                help_lines.append(f"  [cyan]{cmd}[/cyan]  - {desc}")
    
    # Add extra info
    help_lines.extend([
        "\n[bold]Keyboard Shortcuts:[/bold]",
        "  [cyan]Ctrl+C[/cyan]  - Interrupt current chat",
        "  [cyan]Ctrl+D[/cyan]  - Exit agent",
        "  [cyan]↑/↓[/cyan]     - Navigate command history",
        "  [cyan]Tab[/cyan]     - Autocomplete commands",
        "",
        "[bold]Confirmation Mode:[/bold]",
        f"  Current: {get_confirm_status()}",
        "",
        "[bold]Tips:[/bold]",
        "  • Type [cyan]/[/cyan] then press [cyan]Tab[/cyan] to see all commands (with autocomplete)",
        "  • Press [cyan]Ctrl+Space[/cyan] to force show completions",
        "  • Use [cyan]/model <name>[/cyan] for quick model switching",
        "  • Sessions auto-save and are isolated per project",
        "  • Resume later with: [cyan]./llmproxy.sh agent --resume[/cyan]",
        "  • [cyan]Hybrid mode[/cyan]: Ollama models (with :tag) are routed locally"
    ])
    
    console.print(Panel.fit("\n".join(help_lines), title="Help", border_style="cyan"))


def _switch_model_interactive(
    models: list[dict], 
    current_model: str,
    gpu_info: Optional[dict],
    agent
) -> bool:
    """Interactive model switching with preview.
    
    Returns True if model was switched.
    """
    if not models:
        return False
    
    _display_models_enhanced(models, current_model, gpu_info)
    
    console.print("\n[dim]Options:[/dim]")
    console.print("  [cyan]<number>[/cyan]  - Select model by number")
    console.print("  [cyan]i <number>[/cyan] - Show model info")
    console.print("  [cyan]Enter[/cyan]     - Keep current model")
    
    choice = pt_prompt("\nSelect> ").strip()
    
    if not choice:
        console.print("[dim]Keeping current model.[/dim]")
        return False
    
    # Handle info request
    if choice.lower().startswith("i "):
        try:
            idx = int(choice.split()[1]) - 1
            if 0 <= idx < len(models):
                model_id = models[idx]["id"]
                info = _format_model_info(model_id, gpu_info)
                console.print(Panel(info, title=f"Model: {model_id}", border_style="blue"))
            else:
                console.print("[red]Invalid model number.[/red]")
        except (ValueError, IndexError):
            console.print("[red]Usage: i <number>[/red]")
        return False
    
    # Handle selection
    try:
        idx = int(choice) - 1
        if 0 <= idx < len(models):
            selected_model = models[idx]["id"]
            agent.model = selected_model
            console.print(f"[bold green]✓[/bold green] Switched to: [cyan]{selected_model}[/cyan]")
            
            # Show model info
            info = _format_model_info(selected_model, gpu_info)
            console.print(Panel(info, border_style="dim", padding=(0, 2)))
            return True
        else:
            console.print("[red]Invalid selection.[/red]")
    except ValueError:
        console.print("[red]Please enter a number.[/red]")
    
    return False


@app.command()
def run(
    base_url: str = typer.Option(
        _get_env("LLM_PROXY_BASE_URL", "http://localhost:8080/v1"),
        "--base-url",
        "-b",
        help="OpenAI-compatible base URL",
    ),
    api_key: str = typer.Option(
        _get_env("LLM_PROXY_UPSTREAM_API_KEY", ""),
        "--api-key",
        "-k",
        help="API key (or set LLM_PROXY_UPSTREAM_API_KEY)",
    ),
    model: str = typer.Option(
        _get_env("LLM_PROXY_MODEL", "kimi-for-coding"),
        "--model",
        "-m",
        help="Model ID to use",
    ),
    resume: bool = typer.Option(
        False,
        "--resume",
        "-r",
        help="Resume a previous session (interactive selection)",
    ),
    session_id: str = typer.Option(
        "",
        "--session-id",
        "-s",
        help="Resume a specific session by ID",
    ),
    list_sessions: bool = typer.Option(
        False,
        "--list",
        "-l",
        help="List saved sessions for this project",
    ),
    confirm: bool = typer.Option(
        False,
        "--confirm/--no-confirm",
        help="Ask for confirmation before executing tasks",
    ),
    max_tool_rounds: int = typer.Option(
        int(_get_env("LLM_AGENT_MAX_TOOL_ROUNDS", "10")),
        "--max-tool-rounds",
        "-t",
        help="Maximum number of tool call rounds per request (env: LLM_AGENT_MAX_TOOL_ROUNDS)",
    ),
    debug: bool = typer.Option(
        False,
        "--debug",
        "-d",
        help="Enable debug logging of LLM interactions (env: LLM_AGENT_DEBUG)",
    ),
    prompt: str = typer.Argument("", help="Single prompt to run non-interactively"),
):
    # Save terminal state for cleanup on exit
    _save_terminal_state()
    
    # Handle list sessions
    if list_sessions:
        project_id = _get_project_id()
        sessions = _list_sessions(project_id)
        if not sessions:
            console.print("[dim]No saved sessions for this project.[/dim]")
            return

        table = Table(title=f"Saved Sessions for {os.getcwd()}")
        table.add_column("Session ID", style="cyan")
        table.add_column("Created", style="dim")
        table.add_column("Updated", style="dim")
        table.add_column("Tokens", justify="right")
        table.add_column("Messages", justify="right")
        table.add_column("Preview", style="green")

        for session in sessions:
            usage = session.get("usage", {})
            total_tokens = usage.get("total_tokens", 0)

            table.add_row(
                session["session_id"],
                session["created"][:16].replace("T", " ")
                if session["created"] != "Unknown"
                else "—",
                session["updated"][:16].replace("T", " ")
                if session["updated"] != "Unknown"
                else "—",
                f"{total_tokens:,}" if total_tokens else "—",
                str(session["message_count"]),
                session["preview"][:40] + "..."
                if len(session["preview"]) > 40
                else session["preview"] or "[dim]—[/dim]",
            )

        console.print(table)
        return

    # Create agent with session management
    agent = Agent(
        base_url=base_url,
        api_key=api_key,
        model=model,
        session_id=session_id if session_id else None,
        resume=resume,
        max_tool_rounds=max_tool_rounds,
        debug=debug,
    )

    if prompt:
        try:
            reply = agent.chat(prompt)
            console.print(Markdown(reply))
            console.print(agent.get_usage_summary())
            console.print(agent.get_proxy_savings())
        except openai.APIError as e:
            console.print(f"[dim red]API Error ({e.__class__.__name__}): {e}[/dim red]")
            raise SystemExit(1)
        return

    # Use a mutable list to allow toggling confirmation during session
    confirm_state = [confirm]

    def get_confirm_status():
        return (
            "[dim green]✓ Confirm ON[/dim green]"
            if confirm_state[0]
            else "[dim yellow]⚡ Confirm OFF[/dim yellow]"
        )

    # Show welcome panel with usage info
    usage_str = agent.get_usage_summary()
    savings_str = agent.get_proxy_savings()

    # Format session ID more nicely
    session_short = agent.session_id[:20]

    # Get GPU info for display
    gpu_info = _fetch_gpu_info(base_url, api_key)

    console.print(
        Panel.fit(
            f"[bold green]Coding Agent[/bold green]\n"
            f"[dim]Model:[/dim] [cyan]{model}[/cyan] [dim](/m to switch)[/dim]\n"
            f"[dim]Workspace:[/dim] {os.getcwd()}\n"
            f"[dim]Session:[/dim] {session_short}...\n"
            f"{usage_str}\n"
            f"{savings_str}\n"
            f"{get_confirm_status()}\n"
            f"[dim]Commands:[/dim] Type [bold]'/help'[/bold] or press [bold]'?'[/bold]",
            title="Welcome",
        )
    )

    # Setup prompt toolkit bindings
    bindings = KeyBindings()

    @bindings.add("c-d")
    def _(event):
        """Ctrl-D to exit gracefully."""
        event.app.exit(result="/exit")

    @bindings.add("?")
    def _(event):
        """? to show help."""
        event.app.exit(result="/help")

    @bindings.add("c-space")
    def _(event):
        """Ctrl+Space to force show completions."""
        event.app.current_buffer.complete_next()

    # Ctrl-C is not bound - it will cancel input naturally (raise KeyboardInterrupt)

    # Show available commands hint on startup
    commands_hint = (
        " | ".join([f"[cyan]{cmd}[/cyan]" for cmd, _, _ in COMMAND_CATEGORIES["Session"][:2]])
        + " | [cyan]/m[/cyan] | [cyan]/h[/cyan]"
    )
    console.print(f"[dim]Quick: {commands_hint} | Type / then Tab for commands[/dim]")
    console.print()

    # Cache models list to avoid repeated fetching
    cached_models: Optional[list[dict]] = None
    
    # Pre-fetch GPU info for status bar
    gpu_info = _fetch_gpu_info(base_url, api_key)
    
    # Setup command history
    history_path = Path.home() / ".local" / "share" / "llmproxy" / "history"
    history_path.mkdir(parents=True, exist_ok=True)
    session_history = FileHistory(str(history_path / f"{agent.project_id}.txt"))

    try:
        while True:
            try:
                # Use prompt_toolkit for better UX (autocompletion, etc.)
                # Bottom toolbar shows persistent status footer
                user_input = pt_prompt(
                    "> ",
                    completer=SlashCommandCompleter(),
                    complete_while_typing=True,
                    complete_style=CompleteStyle.MULTI_COLUMN,
                    key_bindings=bindings,
                    enable_history_search=True,
                    history=session_history,
                    style=COMPLETION_STYLE,
                    bottom_toolbar=lambda: _format_bottom_toolbar(agent, gpu_info, get_confirm_status()),
                    # Show completion menu on tab even when text is empty
                    reserve_space_for_menu=8,
                )
            except (EOFError, KeyboardInterrupt):
                console.print("\n[dim]Session saved. Goodbye.[/dim]")
                break
    
            user_input = user_input.strip()
    
            # Handle /commands
            if user_input.lower() in ("/exit", "/quit", "/q"):
                console.print("[dim]Session saved. Goodbye.[/dim]")
                break
            
            elif user_input.lower() in ("/help", "/h", "?"):
                _show_help_panel(get_confirm_status)
                continue
            
            elif user_input.lower() == "/clear":
                console.clear()
                console.print(
                    Panel.fit(
                        f"[bold green]Coding Agent[/bold green]\n"
                        f"[dim]Model:[/dim] [cyan]{agent.model}[/cyan]\n"
                        f"{get_confirm_status()}",
                        title="Screen Cleared",
                    )
                )
                continue
            
            elif user_input.lower() in ("/models", "/model"):
                # Fetch models if not cached
                if cached_models is None:
                    console.print("[dim]Fetching available models...[/dim]")
                    cached_models = _fetch_models(base_url, api_key)
                    gpu_info = _fetch_gpu_info(base_url, api_key)
                
                switched = _switch_model_interactive(
                    cached_models, agent.model, gpu_info, agent
                )
                
                if switched:
                    # Refresh usage display after model switch
                    console.print(f"\n[dim]Ready to use {agent.model}[/dim]")
                continue
            
            elif user_input.lower().startswith("/model ") or user_input.lower().startswith("/m "):
                # Quick model switch by name
                parts = user_input.split(maxsplit=1)
                if len(parts) > 1:
                    model_name = parts[1].strip()
                    agent.model = model_name
                    console.print(f"[bold green]✓[/bold green] Switched to: [cyan]{model_name}[/cyan]")
                    
                    # Show info
                    gpu_info = _fetch_gpu_info(base_url, api_key)
                    info = _format_model_info(model_name, gpu_info)
                    console.print(Panel(info, border_style="dim", padding=(0, 2)))
                else:
                    console.print("[red]Usage: /model <model-name>[/red]")
                continue
            
            elif user_input.lower() in ("/model-info", "/info", "/i"):
                # Show current model info
                gpu_info = _fetch_gpu_info(base_url, api_key)
                info = _format_model_info(agent.model, gpu_info)
                
                console.print(Panel(
                    f"[bold]Current Model:[/bold] [cyan]{agent.model}[/cyan]\n\n{info}",
                    title="Model Info",
                    border_style="blue"
                ))
                continue
            
            elif user_input.lower() == "/usage":
                # Build rich usage panel
                total = agent.usage.get("total_tokens", 0)
                inp = agent.usage.get("input_tokens", 0)
                out = agent.usage.get("output_tokens", 0)
                
                # Get pricing and calculate cost
                from llmproxy.cli_agent import PRICING
                pricing = PRICING.get(agent.model, PRICING["default"])
                input_cost = (inp / 1_000_000) * pricing["input"]
                output_cost = (out / 1_000_000) * pricing["output"]
                total_cost = input_cost + output_cost
                cost_str = f"${total_cost:.2f}" if total_cost >= 0.01 else f"${total_cost:.3f}"
                
                lines = []
                lines.append(f"[bold cyan]Session Usage[/bold cyan]  (Model: [cyan]{agent.model}[/cyan])")
                lines.append("")
                lines.append(f"  Total Tokens:  [bold white]{total:,}[/bold white]  ([green]↑{inp:,}[/green] input  [magenta]↓{out:,}[/magenta] output)")
                lines.append(f"  Est. Cost:     [yellow]{cost_str}[/yellow]")
                lines.append("")
                
                # Add proxy savings
                from llmproxy.cli_agent import _fetch_proxy_savings
                savings = _fetch_proxy_savings(agent.base_url)
                if savings:
                    upstream = savings.get("upstream_tokens", 0)
                    downstream = savings.get("downstream_tokens", 0)
                    saved = savings.get("tokens_saved", 0)
                    cache_hits = savings.get("cache_hits", 0)
                    cache_rate = savings.get("cache_hit_rate", 0)
                    requests = savings.get("requests_total", 0)
                    
                    lines.append("[bold cyan]Proxy Activity[/bold cyan]")
                    lines.append("")
                    lines.append(f"  Requests:        [white]{requests:,}[/white]")
                    lines.append(f"  Upstream:        [dim]{upstream:,} tokens[/dim]")
                    lines.append(f"  Downstream:      [dim]{downstream:,} tokens[/dim]")
                    if saved > 0:
                        lines.append(f"  Filtered:        [green]{saved:,} tokens[/green]")
                    if cache_hits > 0:
                        lines.append(f"  Cache hits:      [green]{cache_hits:,}[/green]")
                    if cache_rate > 0:
                        lines.append(f"  Cache hit rate:  [green]{cache_rate:.1%}[/green]")
                    
                    # Calculate money saved through proxy
                    saved_cost = (saved / 1_000_000) * pricing["input"]
                    if saved_cost >= 0.001:
                        lines.append(f"  Money saved:     [green]~${saved_cost:.3f}[/green]")
                    lines.append("")
                
                # Local model info
                if pricing.get("local", False):
                    lines.append("[bold cyan]Local Model Savings[/bold cyan]")
                    lines.append("")
                    cloud_pricing = PRICING["kimi-for-coding"]
                    cloud_cost = (inp / 1_000_000) * cloud_pricing["input"] + (out / 1_000_000) * cloud_pricing["output"]
                    if cloud_cost >= 0.001:
                        lines.append(f"  vs Cloud API:    [cyan]~${cloud_cost:.3f} saved[/cyan]")
                    lines.append("")
                
                console.print(Panel("\n".join(lines), title="[bold]Usage Statistics[/bold]", border_style="blue", padding=(0, 2), width=60))
                continue
            
            elif user_input.lower() == "/savings":
                console.print(agent.get_proxy_savings())
                continue
            
            elif user_input.lower() == "/confirm":
                confirm_state[0] = True
                console.print(
                    "[dim green]✓[/dim green] Confirmation enabled. The agent will ask before executing tasks."
                )
                continue
            
            elif user_input.lower() == "/noconfirm":
                confirm_state[0] = False
                console.print(
                    "[dim yellow]⚡[/dim yellow] Confirmation disabled. The agent will auto-execute tasks."
                )
                continue
            
            elif user_input.lower() == "/init":
                if _init_agent_md():
                    console.print(
                        "[dim green]✓[/dim green] Created AGENT.md with default project context."
                    )
                    console.print(
                        "[dim]Edit this file to customize project-specific instructions.[/dim]"
                    )
                else:
                    console.print(
                        "[dim yellow]⚠[/dim yellow] AGENT.md already exists. Edit it directly to customize."
                    )
                continue
            
            elif not user_input:
                continue
            
            elif user_input.startswith("/"):
                console.print(
                    f"[dim]Unknown command: {user_input}. Type /help for available commands.[/dim]"
                )
                continue
    
            # Confirmation flow: agent states its understanding first
            if confirm_state[0]:
                try:
                    with console.status("[bold blue]Understanding your request...[/bold blue]"):
                        understanding = agent.get_understanding(user_input)
                    
                    console.print(Panel(
                        Markdown(understanding),
                        title="[bold yellow]My Understanding[/bold yellow]",
                        border_style="yellow",
                        subtitle="[dim]Press Enter to proceed, Ctrl+C to cancel[/dim]"
                    ))
                    
                    # Wait for user confirmation
                    try:
                        confirm_input = pt_prompt("[Press Enter to proceed, or type to refine] > ")
                    except (EOFError, KeyboardInterrupt):
                        console.print("\n[dim yellow]⏹ Cancelled.[/dim yellow]")
                        continue
                    
                    # If user typed something, treat it as clarification/refinement
                    if confirm_input.strip():
                        user_input = f"{user_input}\n\n[Clarification: {confirm_input.strip()}]"
                        console.print("[dim]Proceeding with your clarification...[/dim]")
                    else:
                        console.print("[dim]Proceeding...[/dim]")
                        
                except KeyboardInterrupt:
                    console.print("\n[dim yellow]⏹ Cancelled.[/dim yellow]")
                    continue
    
            try:
                with console.status("[bold green]Thinking...[/bold green]"):
                    reply = agent.chat(user_input)
    
                console.print(Panel(Markdown(reply), title="[bold magenta]Assistant[/bold magenta]", border_style="magenta"))
                console.print()  # Extra newline for spacing
            except openai.RateLimitError as e:
                # Handle rate limit errors with helpful suggestions
                error_body = e.body if hasattr(e, 'body') else {}
                error_msg = str(e)
                console.print(Panel(
                    "[bold red]⏱️ Rate Limit Exceeded[/bold red]\n\n"
                    "The upstream API is rate-limiting requests. Options:\n\n"
                    "1. [cyan]/models[/cyan] - Switch to a different model\n"
                    "2. [cyan]/model <local-model>[/cyan] - Use a local Ollama model (no rate limits)\n"
                    "3. Wait a moment and try again\n\n"
                    f"[dim]Error: {error_msg[:100]}...[/dim]" if len(str(error_msg)) > 100 else f"[dim]Error: {error_msg}[/dim]",
                    title="Rate Limited",
                    border_style="red"
                ))
            except openai.APIError as e:
                console.print(f"\n[dim red]API Error ({e.__class__.__name__}): {e}[/dim red]")
            except KeyboardInterrupt:
                console.print("\n[dim yellow]⏹ Chat interrupted.[/dim yellow]")
                # Add a placeholder message so the conversation context is preserved
                agent.messages.append({"role": "assistant", "content": "[Response interrupted by user]"})
                agent._save()
    finally:
        # Restore terminal state on exit
        _restore_terminal()


if __name__ == "__main__":
    app()
