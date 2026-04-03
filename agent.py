#!/usr/bin/env python3
"""Entry point for the coding agent CLI."""

import os
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.table import Table

from llmproxy.cli_agent import Agent, _list_sessions, _get_project_id

app = typer.Typer(help="Coding agent CLI — interacts with your filesystem via LLM tools.")
console = Console()


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
    )

    if prompt:
        reply = agent.chat(prompt)
        console.print(Markdown(reply))
        console.print(agent.get_usage_summary())
        return

    # Show welcome panel with usage info
    usage_str = agent.get_usage_summary()
    
    # Format session ID more nicely
    session_short = agent.session_id[:20]
    
    console.print(Panel.fit(
        f"[bold green]Coding Agent[/bold green]\n"
        f"[dim]Model:[/dim] {model}\n"
        f"[dim]Workspace:[/dim] {os.getcwd()}\n"
        f"[dim]Session:[/dim] {session_short}...\n"
        f"{usage_str}\n"
        f"[dim]Commands:[/dim] [bold]'exit'[/bold] to quit, [bold]'help'[/bold] for usage info",
        title="Welcome",
    ))

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session saved. Goodbye.[/dim]")
            break

        user_input = user_input.strip()
        
        # Handle special commands
        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Session saved. Goodbye.[/dim]")
            break
        elif user_input.lower() == "help":
            console.print(Panel.fit(
                "[bold cyan]Usage Information[/bold cyan]\n\n"
                "[bold]Token Display:[/bold]\n"
                "  • [dim]Usage: 1,234 tokens total (1,000 in / 234 out)[/dim]\n"
                "    - Total: Sum of all tokens sent and received\n"
                "    - In: Tokens sent to the AI (your messages + context)\n" 
                "    - Out: Tokens received from the AI (responses)\n\n"
                "[bold]Cost Display:[/bold]\n"
                "  • [dim]Cost: ~12¢[/dim] or [dim]Cost: $1.23[/dim]\n"
                "    - Based on model pricing per million tokens\n"
                "    - Kimi: ~$0.50/M input, $2.00/M output\n\n"
                "[bold]Commands:[/bold]\n"
                "  • [bold]exit[/bold] or [bold]quit[/bold] - Save and exit\n"
                "  • [bold]help[/bold] - Show this help\n"
                "  • [bold]usage[/bold] - Show current session usage\n\n"
                "[bold]Session Management:[/bold]\n"
                "  Sessions are auto-saved and isolated per project\n"
                "  Resume with: ./llmproxy.sh agent --resume",
                title="Help"
            ))
            continue
        elif user_input.lower() == "usage":
            console.print(agent.get_usage_summary())
            continue
        elif not user_input:
            continue

        with console.status("[bold green]Thinking...[/bold green]"):
            reply = agent.chat(user_input)

        console.print(Panel(Markdown(reply), title="[bold magenta]Assistant[/bold magenta]", border_style="magenta"))
        console.print(agent.get_usage_summary())


if __name__ == "__main__":
    app()
