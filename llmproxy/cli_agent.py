"""Agent loop for the coding CLI."""

import os
from typing import Optional

from openai import OpenAI
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

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


class Agent:
    def __init__(
        self,
        base_url: str = "http://localhost:8080/v1",
        api_key: Optional[str] = None,
        model: str = "kimi-for-coding",
    ):
        self.client = OpenAI(
            base_url=base_url,
            api_key=api_key or "dummy",
        )
        self.model = model
        self.messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        self.max_tool_rounds = 10

    def chat(self, user_input: str) -> str:
        self.messages.append({"role": "user", "content": user_input})

        for _ in range(self.max_tool_rounds):
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self.messages,
                tools=TOOL_DEFINITIONS,
                temperature=0.3,
            )
            choice = response.choices[0]
            assistant_msg = choice.message

            # Append the assistant message (content may be None)
            self.messages.append(assistant_msg.model_dump())

            tool_calls = assistant_msg.tool_calls
            if not tool_calls or choice.finish_reason != "tool_calls":
                return assistant_msg.content or "(no response)"

            # Execute tools and append results
            for tc in tool_calls:
                name = tc.function.name
                import json
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

        return "(reached max tool rounds without final answer)"
