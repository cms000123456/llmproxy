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
    console.print(Panel.fit(
        f"[bold green]Coding Agent[/bold green]\n"
        f"Model: {model}\n"
        f"Base URL: {base_url}\n"
        f"Workspace: {os.getcwd()}\n"
        f"Session: {agent.session_id[:24]}...\n"
        f"{usage_str}\n"
        f"Type [bold]'exit'[/bold] or [bold]'quit'[/bold] to leave.",
        title="Welcome",
    ))

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Session saved. Goodbye.[/dim]")
            break

        user_input = user_input.strip()
        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Session saved. Goodbye.[/dim]")
            break
        if not user_input:
            continue

        with console.status("[bold green]Thinking...[/bold green]"):
            reply = agent.chat(user_input)

        console.print(Panel(Markdown(reply), title="[bold magenta]Assistant[/bold magenta]", border_style="magenta"))
        console.print(agent.get_usage_summary())


if __name__ == "__main__":
    app()
