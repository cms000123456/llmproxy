from __future__ import annotations

"""Prompt compression strategies to fit within token budgets."""

import json
from types import ModuleType
from typing import Any

tiktoken: ModuleType | None = None
try:
    import tiktoken as _tiktoken_module
    tiktoken = _tiktoken_module
except Exception:  # pragma: no cover
    pass


def count_tokens(text: str, model: str = "gpt-4") -> int:
    if tiktoken is None:
        # Rough fallback: ~4 chars per token for CJK, ~4 for English too as safe over-estimate
        return len(text) // 3
    try:
        enc = tiktoken.encoding_for_model(model)
    except KeyError:
        enc = tiktoken.get_encoding("cl100k_base")
    return len(enc.encode(text))


def count_message_tokens(messages: list[dict], model: str = "gpt-4") -> int:
    total = 0
    for m in messages:
        content = m.get("content", "")
        if isinstance(content, str):
            total += count_tokens(content, model)
        elif isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and "text" in item:
                    total += count_tokens(item["text"], model)
                else:
                    total += count_tokens(json.dumps(item, ensure_ascii=False), model)
        else:
            total += count_tokens(json.dumps(content, ensure_ascii=False), model)
    return total


def compress_messages(messages: list[dict], cfg: Any, model: str = "gpt-4") -> list[dict]:
    if not cfg.enable_compression:
        return messages

    total = count_message_tokens(messages, model)
    if total <= cfg.max_total_tokens:
        return messages

    strategy = cfg.compression_strategy

    if strategy == "truncate_oldest":
        return _truncate_oldest(messages, cfg.max_total_tokens, model)
    elif strategy == "summarize_oldest":
        return _summarize_oldest(messages, cfg.max_total_tokens, model, cfg.summary_model)
    else:
        return _truncate_oldest(messages, cfg.max_total_tokens, model)


def _truncate_oldest(messages: list[dict], budget: int, model: str) -> list[dict]:
    # Always preserve the system message and the last user/assistant exchange
    if not messages:
        return messages

    preserved_head = []
    preserved_tail = []
    mutable_middle = []

    # Keep first system message at head
    idx = 0
    if messages[0].get("role") == "system":
        preserved_head.append(messages[0])
        idx = 1

    # Keep last 2 messages at tail
    tail_start = max(idx, len(messages) - 2)
    mutable_middle = messages[idx:tail_start]
    preserved_tail = messages[tail_start:]

    current = count_message_tokens(preserved_head + mutable_middle + preserved_tail, model)
    while mutable_middle and current > budget:
        removed = mutable_middle.pop(0)
        current -= max(1, count_message_tokens([removed], model))

    result = preserved_head + mutable_middle + preserved_tail
    if current > budget and len(preserved_tail) > 1:
        # Emergency: truncate oldest in tail
        result = _truncate_oldest(result, budget, model)
    return result


def _summarize_oldest(
    messages: list[dict], budget: int, model: str, summary_model: str
) -> list[dict]:
    # Placeholder summarization: collapse oldest non-system/user/assistant roles into a summary placeholder
    # In a real deployment you'd call a cheap LLM here.
    result = _truncate_oldest(messages, budget, model)
    return result
