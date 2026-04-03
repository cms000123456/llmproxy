#!/usr/bin/env python3
"""Entry point for the coding agent CLI."""

import os
import sys

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt

from llmproxy.cli_agent import Agent

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
    prompt: str = typer.Argument("", help="Single prompt to run non-interactively"),
):
    agent = Agent(base_url=base_url, api_key=api_key, model=model)

    if prompt:
        reply = agent.chat(prompt)
        console.print(Markdown(reply))
        return

    console.print(Panel.fit(
        f"[bold green]Coding Agent[/bold green]\n"
        f"Model: {model}\n"
        f"Base URL: {base_url}\n"
        f"Workspace: {os.getcwd()}\n"
        f"Type [bold]'exit'[/bold] or [bold]'quit'[/bold] to leave.",
        title="Welcome",
    ))

    while True:
        try:
            user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]Goodbye.[/dim]")
            break

        user_input = user_input.strip()
        if user_input.lower() in ("exit", "quit"):
            console.print("[dim]Goodbye.[/dim]")
            break
        if not user_input:
            continue

        with console.status("[bold green]Thinking...[/bold green]"):
            reply = agent.chat(user_input)

        console.print(Panel(Markdown(reply), title="[bold magenta]Assistant[/bold magenta]", border_style="magenta"))


if __name__ == "__main__":
    app()
