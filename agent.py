#!/usr/bin/env python3
"""Entry point for the coding agent CLI."""

import os
import sys

import openai
import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from prompt_toolkit import prompt as pt_prompt
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.application import get_app
from rich.table import Table

from llmproxy.cli_agent import Agent, _list_sessions, _get_project_id

app = typer.Typer(help="Coding agent CLI — interacts with your filesystem via LLM tools.")
console = Console()

# Available slash commands for autocompletion
SLASH_COMMANDS = [
    ("/exit", "Save session and exit"),
    ("/quit", "Save session and exit (alias)"),
    ("/help", "Show available commands"),
    ("/usage", "Show token usage"),
    ("/savings", "Show proxy savings"),
    ("/confirm", "Enable confirmation before tasks"),
    ("/noconfirm", "Disable confirmation (auto-execute)"),
]


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
        True,
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
                session["created"][:16].replace("T", " ") if session["created"] != "Unknown" else "—",
                session["updated"][:16].replace("T", " ") if session["updated"] != "Unknown" else "—",
                f"{total_tokens:,}" if total_tokens else "—",
                str(session["message_count"]),
                session["preview"][:40] + "..." if len(session["preview"]) > 40 else session["preview"] or "[dim]—[/dim]",
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
        return "[dim green]✓[/dim green] Confirm ON" if confirm_state[0] else "[dim yellow]⚡[/dim yellow] Confirm OFF"

    # Show welcome panel with usage info
    usage_str = agent.get_usage_summary()
    savings_str = agent.get_proxy_savings()
    
    # Format session ID more nicely
    session_short = agent.session_id[:20]
    
    console.print(Panel.fit(
        f"[bold green]Coding Agent[/bold green]\n"
        f"[dim]Model:[/dim] {model}\n"
        f"[dim]Workspace:[/dim] {os.getcwd()}\n"
        f"[dim]Session:[/dim] {session_short}...\n"
        f"{usage_str}\n"
        f"{savings_str}\n"
        f"{get_confirm_status()}\n"
        f"[dim]Commands:[/dim] Type [bold]'/help'[/bold] for available commands",
        title="Welcome",
    ))

    # Setup prompt toolkit bindings
    bindings = KeyBindings()
    
    @bindings.add("c-d")
    def _(event):
        """Ctrl-D to exit gracefully."""
        event.app.exit(result="/exit")
    
    # Ctrl-C is not bound - it will cancel input naturally (raise KeyboardInterrupt)
    
    # Show available commands hint on startup
    commands_hint = " | ".join([f"[cyan]{cmd}[/cyan]" for cmd, _ in SLASH_COMMANDS[:4]]) + " | [dim]...[/dim]"
    console.print(f"[dim]Commands: {commands_hint} Type / for suggestions[/dim]")
    console.print()
    
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
        if user_input.lower() == "/exit" or user_input.lower() == "/quit":
            console.print("[dim]Session saved. Goodbye.[/dim]")
            break
        elif user_input.lower() == "/help":
            console.print(Panel.fit(
                "[bold cyan]Available Commands[/bold cyan]\n\n"
                "[bold]Session Commands:[/bold]\n"
                "  [cyan]/exit[/cyan], [cyan]/quit[/cyan]  - Save session and exit\n"
                "  [cyan]/usage[/cyan]          - Show current session token usage\n"
                "  [cyan]/savings[/cyan]         - Show proxy savings (filtering/caching)\n"
                "  [cyan]/help[/cyan]            - Show this help message\n\n"
                "[bold]Confirmation Mode:[/bold]\n"
                f"  Current: {get_confirm_status()}\n"
                "  [cyan]/confirm[/cyan]        - Enable confirmation before tasks\n"
                "  [cyan]/noconfirm[/cyan]      - Disable confirmation (auto-execute)\n\n"
                "[bold]Keyboard Shortcuts:[/bold]\n"
                "  [cyan]Ctrl+C[/cyan]            - Interrupt current chat\n"
                "  [cyan]Ctrl+D[/cyan]            - Exit agent\n\n"
                "[bold]Usage Display:[/bold]\n"
                "  [dim]Usage: 1,234 tokens total (1,000 in / 234 out) | Cost: ~12¢[/dim]\n"
                "    - [bold]in:[/bold] Tokens sent to AI (your messages + context)\n"
                "    - [bold]out:[/bold] Tokens received from AI (responses)\n"
                "    - [bold]Cost:[/bold] Estimated based on model pricing\n\n"
                "[bold]Proxy Savings:[/bold]\n"
                "  Shows tokens saved by the proxy through:\n"
                "    - Filtering (removing duplicates, truncation)\n"
                "    - Caching (avoiding duplicate API calls)\n\n"
                "[bold]Session Management:[/bold]\n"
                "  Sessions auto-save and are isolated per project.\n"
                "  Resume later with: [cyan]./llmproxy.sh agent --resume[/cyan]",
                title="Help"
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
            console.print(f"[dim green]✓[/dim green] Confirmation enabled. The agent will ask before executing tasks.")
            continue
        elif user_input.lower() == "/noconfirm":
            confirm_state[0] = False
            console.print(f"[dim yellow]⚡[/dim yellow] Confirmation disabled. The agent will auto-execute tasks.")
            continue
        elif not user_input:
            continue
        elif user_input.startswith("/"):
            console.print(f"[dim]Unknown command: {user_input}. Type /help for available commands.[/dim]")
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
