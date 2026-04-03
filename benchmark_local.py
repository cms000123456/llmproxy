#!/usr/bin/env python3
"""Local benchmark: measure token savings from filtering + compression without network calls."""

import random
import time

from rich.console import Console
from rich.table import Table

from llmproxy.compressors import count_message_tokens, compress_messages
from llmproxy.config import settings
from llmproxy.filters import filter_messages

console = Console()


def make_words(n: int) -> str:
    pool = [
        "lorem", "ipsum", "dolor", "sit", "amet", "consectetur", "adipiscing", "elit",
        "sed", "do", "eiusmod", "tempor", "incididunt", "ut", "labore", "et",
        "dolore", "magna", "aliqua", "ut", "enim", "ad", "minim", "veniam",
    ]
    return " ".join(random.choices(pool, k=n))


def scenario_clean(turns: int, words: int) -> list[dict]:
    messages = [{"role": "system", "content": "You are a helpful assistant."}]
    for i in range(turns):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": make_words(words)})
    return messages


def scenario_bloated() -> list[dict]:
    """Messy real-world-like payload."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "system", "content": "You are helpful."},  # duplicate
        {"role": "system", "content": "You are helpful."},  # duplicate
        {"role": "user", "content": make_words(800)},
        {"role": "assistant", "content": ""},  # empty
        {"role": "user", "content": make_words(800)},
        {"role": "assistant", "content": make_words(800)},
        {"role": "user", "content": make_words(800)},
        {"role": "assistant", "content": ""},  # empty
        {"role": "user", "content": "Summarize everything above."},
    ]
    return messages


def scenario_long_context() -> list[dict]:
    """Very long conversation that exceeds token budget."""
    messages = [{"role": "system", "content": "You are a coding assistant."}]
    for i in range(40):
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": make_words(600)})
    return messages


def scenario_image_bloat() -> list[dict]:
    """Conversation with a huge base64 image that should be stripped."""
    # Simulate a 500KB base64 string (about 700k tokens if kept)
    fake_image = "data:image/png;base64," + ("A" * 500_000)
    return [
        {"role": "system", "content": "You are a helpful assistant."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "What's in this image?"},
                {"type": "image_url", "image_url": {"url": fake_image}},
            ],
        },
        {"role": "assistant", "content": "It looks like a chart."},
        {"role": "user", "content": "Summarize the report."},
    ]


def run():
    # Temporarily tighten settings so filtering & compression actually trigger
    original_budget = settings.max_total_tokens
    original_strip = settings.strip_base64_images
    settings.max_total_tokens = 8000
    settings.strip_base64_images = True

    scenarios = [
        ("clean_small", scenario_clean(4, 50)),
        ("clean_medium", scenario_clean(10, 200)),
        ("bloated_chat", scenario_bloated()),
        ("long_context", scenario_long_context()),
        ("massive_history", scenario_clean(60, 400)),
        ("image_bloat", scenario_image_bloat()),
    ]

    table = Table(title="Local Proxy Savings Benchmark")
    table.add_column("Scenario", style="cyan")
    table.add_column("Raw Tokens", justify="right")
    table.add_column("After Filter", justify="right")
    table.add_column("After Compress", justify="right")
    table.add_column("Tokens Saved", justify="right", style="green")
    table.add_column("Reduction %", justify="right", style="green")
    table.add_column("Latency (ms)", justify="right", style="dim")

    total_raw = 0
    total_saved = 0

    for name, messages in scenarios:
        raw_tokens = count_message_tokens(messages, "gpt-4")

        t0 = time.perf_counter()
        filtered = filter_messages(messages, settings)
        filtered_tokens = count_message_tokens(filtered, "gpt-4")

        compressed = compress_messages(filtered, settings, "gpt-4")
        compressed_tokens = count_message_tokens(compressed, "gpt-4")
        t1 = time.perf_counter()

        saved = raw_tokens - compressed_tokens
        pct = (saved / max(1, raw_tokens)) * 100
        latency_ms = round((t1 - t0) * 1000, 3)

        total_raw += raw_tokens
        total_saved += saved

        table.add_row(
            name,
            str(raw_tokens),
            str(filtered_tokens),
            str(compressed_tokens),
            str(saved),
            f"{pct:.1f}%",
            str(latency_ms),
        )

    console.print(table)
    total_pct = (total_saved / max(1, total_raw)) * 100
    console.print(
        f"\n[bold green]Total raw tokens:[/bold green] {total_raw:,}  →  "
        f"[bold green]Saved:[/bold green] {total_saved:,} "
        f"([bold green]{total_pct:.1f}%[/bold green] reduction)"
    )

    # Cost estimate placeholder (generic $2 per 1M input tokens)
    cost_per_1m = 2.0
    raw_cost = (total_raw / 1_000_000) * cost_per_1m
    saved_cost = (total_saved / 1_000_000) * cost_per_1m
    console.print(
        f"\n[dim]At ~${cost_per_1m}/1M tokens, this batch would cost "
        f"${raw_cost:.2f} raw vs ${raw_cost - saved_cost:.2f} proxied, "
        f"saving ${saved_cost:.2f}.[/dim]"
    )

    settings.max_total_tokens = original_budget
    settings.strip_base64_images = original_strip


if __name__ == "__main__":
    run()
