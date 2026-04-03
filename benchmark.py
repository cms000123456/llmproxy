#!/usr/bin/env python3
"""Benchmark the LLM Proxy to measure token savings, latency, and cache efficiency."""

import json
import os
import random
import statistics
import time
from typing import Optional

import httpx
from rich.console import Console
from rich.table import Table

console = Console()


def generate_conversation(turns: int, words_per_message: int) -> list[dict]:
    """Generate a synthetic conversation."""
    words = ["alpha", "bravo", "charlie", "delta", "echo", "foxtrot", "golf", "hotel"]
    messages = [{"role": "system", "content": "You are a helpful coding assistant."}]
    for i in range(turns):
        content = " ".join(random.choices(words, k=words_per_message))
        role = "user" if i % 2 == 0 else "assistant"
        messages.append({"role": role, "content": content})
    return messages


def send_request(proxy_url: str, payload: dict) -> dict:
    resp = httpx.post(
        f"{proxy_url}/v1/chat/completions",
        headers={"Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    return {"status": resp.status_code, "latency_ms": resp.elapsed.total_seconds() * 1000}


def get_metrics(proxy_url: str) -> dict:
    try:
        return httpx.get(f"{proxy_url}/metrics", timeout=5).json()
    except Exception:
        return {}


def run_benchmark(proxy_url: str = "http://localhost:8080") -> None:
    scenarios = [
        ("tiny_clean", 1, 10, 1),
        ("small_chat", 4, 50, 2),
        ("medium_chat", 10, 100, 1),
        ("large_bloated", 20, 500, 1),
        ("duplicate_system", 6, 100, 1),
        ("cache_hit", 2, 20, 3),
    ]

    # Reset proxy metrics by restarting? Not possible here, so we note starting state
    baseline = get_metrics(proxy_url)
    baseline_requests = baseline.get("metrics", {}).get("requests_total", 0)

    results = []

    for name, turns, words, repeats in scenarios:
        if name == "duplicate_system":
            messages = [
                {"role": "system", "content": "You are helpful."},
                {"role": "system", "content": "You are helpful."},
                {"role": "system", "content": "You are helpful."},
            ]
            for _ in range(turns):
                content = " ".join(random.choices(["foo", "bar", "baz"], k=words))
                messages.append({"role": "user", "content": content})
                messages.append({"role": "assistant", "content": content})
        else:
            messages = generate_conversation(turns, words)

        payload = {"model": "kimi-for-coding", "messages": messages}
        latencies = []

        for _ in range(repeats):
            info = send_request(proxy_url, payload)
            latencies.append(info["latency_ms"])
            time.sleep(0.2)

        after = get_metrics(proxy_url)
        after_requests = after.get("metrics", {}).get("requests_total", 0)
        tokens_upstream = after.get("metrics", {}).get("tokens_upstream", 0)
        tokens_downstream = after.get("metrics", {}).get("tokens_downstream", 0)
        tokens_saved = after.get("metrics", {}).get("tokens_saved", 0)
        cache_hits = after.get("metrics", {}).get("cache_hits", 0)

        results.append({
            "name": name,
            "repeats": repeats,
            "avg_latency_ms": round(statistics.mean(latencies), 2),
            "tokens_upstream": tokens_upstream,
            "tokens_downstream": tokens_downstream,
            "tokens_saved": tokens_saved,
            "cache_hits": cache_hits,
        })

    table = Table(title="LLM Proxy Benchmark Results")
    table.add_column("Scenario", style="cyan")
    table.add_column("Calls", justify="right")
    table.add_column("Avg Latency (ms)", justify="right")
    table.add_column("Upstream Tokens", justify="right")
    table.add_column("Downstream Tokens", justify="right")
    table.add_column("Tokens Saved", justify="right", style="green")
    table.add_column("Cache Hits", justify="right", style="magenta")

    for r in results:
        table.add_row(
            r["name"],
            str(r["repeats"]),
            str(r["avg_latency_ms"]),
            str(r["tokens_upstream"]),
            str(r["tokens_downstream"]),
            str(r["tokens_saved"]),
            str(r["cache_hits"]),
        )

    console.print(table)

    total_saved = sum(r["tokens_saved"] for r in results)
    total_upstream = max(1, sum(r["tokens_upstream"] for r in results))
    savings_pct = round((total_saved / total_upstream) * 100, 2)

    console.print(f"\n[bold green]Total tokens saved:[/bold green] {total_saved}")
    console.print(f"[bold green]Effective reduction:[/bold green] {savings_pct}%")
    console.print(
        f"\n[dim]Note: metrics are cumulative since proxy start. "
        f"If you want per-scenario isolation, restart the proxy between runs.[/dim]"
    )


if __name__ == "__main__":
    import sys

    proxy_url = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8080"
    run_benchmark(proxy_url)
