"""Request filtering strategies."""

import base64
import re
from typing import Any


def is_base64_string(s: str) -> bool:
    try:
        if len(s) < 100:
            return False
        return base64.b64encode(base64.b64decode(s, validate=True)).decode("ascii") == s
    except Exception:
        return False


def truncate_message(content: Any, max_length: int) -> Any:
    if isinstance(content, str) and len(content) > max_length:
        return content[:max_length] + f"\n\n[... truncated from {len(content)} chars to {max_length} ...]"
    if isinstance(content, list):
        # Handle content arrays (e.g., vision models)
        out = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item.get("text", "")
                if len(text) > max_length:
                    text = text[:max_length] + f"\n\n[... truncated from {len(text)} chars to {max_length} ...]"
                out.append({**item, "text": text})
            else:
                out.append(item)
        return out
    return content


def strip_large_images(content: Any) -> Any:
    if not isinstance(content, list):
        return content
    out = []
    for item in content:
        if isinstance(item, dict):
            if item.get("type") == "image_url":
                continue
            if item.get("type") == "image":
                continue
        out.append(item)
    return out if out else "[Image removed by proxy filter]"


def filter_messages(messages: list[dict], cfg: Any) -> list[dict]:
    if not cfg.enable_filtering:
        return messages

    out = []
    seen_system = False

    for msg in messages:
        role = msg.get("role", "")
        content = msg.get("content")

        # Remove empty messages
        if cfg.remove_empty_messages and not content:
            continue

        # Deduplicate system messages (keep first)
        if cfg.deduplicate_system_messages and role == "system":
            if seen_system:
                continue
            seen_system = True

        # Strip images if configured
        if cfg.strip_base64_images:
            content = strip_large_images(content)

        # Truncate long messages
        content = truncate_message(content, cfg.max_message_length)

        out.append({"role": role, "content": content})

    return out
