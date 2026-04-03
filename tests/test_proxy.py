#!/usr/bin/env python3
"""Quick integration test for the proxy filtering/compression/cache logic."""

from llmproxy.cache import LRUCache
from llmproxy.compressors import compress_messages, count_message_tokens
from llmproxy.config import settings
from llmproxy.filters import filter_messages


def test_filtering():
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "system", "content": "You are a helpful assistant."},  # duplicate
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": ""},  # empty
        {"role": "user", "content": "x" * 100_000},  # too long
    ]
    filtered = filter_messages(messages, settings)
    assert len(filtered) == 3, f"Expected 3 messages, got {len(filtered)}"
    assert filtered[0]["role"] == "system"
    assert filtered[1]["role"] == "user"
    assert "truncated" in filtered[2]["content"]
    print("✓ Filtering works")


def test_compression():
    # Build a long conversation
    messages = [{"role": "system", "content": "Sys"}]
    for i in range(50):
        messages.append({"role": "user", "content": f"Message {i}: " + "word " * 200})
        messages.append({"role": "assistant", "content": f"Reply {i}: " + "ok " * 200})

    original_tokens = count_message_tokens(messages, "gpt-4")
    compressed = compress_messages(messages, settings, "gpt-4")
    compressed_tokens = count_message_tokens(compressed, "gpt-4")
    assert compressed_tokens <= settings.max_total_tokens
    assert compressed[0]["role"] == "system"
    # Last messages preserved
    assert compressed[-1]["role"] == "assistant"
    print(f"✓ Compression works: {original_tokens} -> {compressed_tokens} tokens")


def test_cache():
    cache = LRUCache(max_size=10, ttl_seconds=5)
    payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
    assert cache.get(payload) is None
    cache.set(payload, {"choices": []})
    assert cache.get(payload) == {"choices": []}
    print("✓ Cache works")


if __name__ == "__main__":
    test_filtering()
    test_compression()
    test_cache()
    print("All tests passed.")
