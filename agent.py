#!/usr/bin/env python3
"""Entry point for the coding agent CLI."""

import os
from typing import Optional

import openai
import typer
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.tree import Tree

from llmproxy.cli_agent import Agent, _get_project_id, _init_agent_md, _list_sessions

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


class SlashCommandCompleter(Completer):
    """Completer for slash commands."""

    def get_completions(self, document, complete_event):
        text = document.text
        if text.startswith("/"):
            for cmd, desc in SLASH_COMMANDS:
                if cmd.startswith(text):
                    yield Completion(
                        cmd,
                        start_position=-len(text),
                        display=cmd,
                        display_meta=desc,
                    )


def _get_env(var: str, default: str = "") -> str:
    return os.getenv(var, default)


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
        console.print("[dim]If using local mode, ensure Ollama is running with: ollama serve[/dim]")
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
    
    if gpu_info:
        console.print(f"\n[dim]GPU: {gpu_info.get('platform', 'unknown')} | "
                     f"VRAM: {gpu_info.get('free_vram_gb', 0):.1f} GB free[/dim]")


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
        "  • Type [cyan]/[/cyan] then press Tab to see all commands",
        "  • Use [cyan]/model <name>[/cyan] for quick model switching",
        "  • Sessions auto-save and are isolated per project",
        "  • Resume later with: [cyan]./llmproxy.sh agent --resume[/cyan]",
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
    prompt: str = typer.Argument("", help="Single prompt to run non-interactively"),
):
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

    # Ctrl-C is not bound - it will cancel input naturally (raise KeyboardInterrupt)

    # Show available commands hint on startup
    commands_hint = (
        " | ".join([f"[cyan]{cmd}[/cyan]" for cmd, _, _ in COMMAND_CATEGORIES["Session"][:2]])
        + " | [cyan]/m[/cyan] | [cyan]/h[/cyan]"
    )
    console.print(f"[dim]Quick: {commands_hint} | Type / for all commands[/dim]")
    console.print()

    # Cache models list to avoid repeated fetching
    cached_models: Optional[list[dict]] = None

    while True:
        try:
            # Use prompt_toolkit for better UX (autocompletion, etc.)
            user_input = pt_prompt(
                "> ",
                completer=SlashCommandCompleter(),
                complete_while_typing=True,
                key_bindings=bindings,
                enable_history_search=True,
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
            console.print(agent.get_usage_summary())
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
            console.print(agent.get_usage_summary())
            console.print(agent.get_proxy_savings())
        except openai.APIError as e:
            console.print(f"\n[dim red]API Error ({e.__class__.__name__}): {e}[/dim red]")
        except KeyboardInterrupt:
            console.print("\n[dim yellow]⏹ Chat interrupted.[/dim yellow]")
            # Add a placeholder message so the conversation context is preserved
            agent.messages.append({"role": "assistant", "content": "[Response interrupted by user]"})
            agent._save()


if __name__ == "__main__":
    app()
