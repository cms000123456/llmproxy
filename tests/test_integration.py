#!/usr/bin/env python3
"""Integration tests for the full proxy pipeline."""

import os

from llmproxy.cache import LRUCache
from llmproxy.compressors import compress_messages, count_message_tokens
from llmproxy.config import Settings
from llmproxy.filters import filter_messages
from llmproxy.metrics import Metrics


def get_clean_settings():
    """Get clean settings without env var interference."""
    for key in list(os.environ.keys()):
        if key.startswith("LLM_PROXY_"):
            del os.environ[key]
    return Settings()


def test_full_pipeline_basic():
    """Test the full message processing pipeline."""
    settings = get_clean_settings()

    # Create a conversation
    messages = [
        {"role": "system", "content": "You are a helpful assistant."},
        {"role": "user", "content": "Hello!"},
        {"role": "assistant", "content": "Hi there!"},
        {"role": "user", "content": "How are you?"},
    ]

    # Step 1: Filter
    filtered = filter_messages(messages, settings)
    assert len(filtered) == 4

    # Step 2: Compress
    compressed = compress_messages(filtered, settings, "gpt-4")
    assert len(compressed) >= 1

    # Step 3: Cache (simulate)
    cache = LRUCache(max_size=10, ttl_seconds=60)
    request_payload = {"model": "gpt-4", "messages": compressed}

    # First request - cache miss
    assert cache.get(request_payload) is None

    # Simulate response
    response = {"choices": [{"message": {"content": "I'm doing well!"}}]}
    cache.set(request_payload, response)

    # Second request - cache hit
    assert cache.get(request_payload) == response

    print("✓ Full pipeline basic flow works")


def test_full_pipeline_with_duplicates():
    """Test pipeline with duplicate system messages."""
    settings = get_clean_settings()
    settings.deduplicate_system_messages = True

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "system", "content": "You are helpful."},  # Duplicate
        {"role": "system", "content": "You are helpful."},  # Duplicate
        {"role": "user", "content": "Hello!"},
    ]

    # Filter should remove duplicates
    filtered = filter_messages(messages, settings)
    assert len(filtered) == 2
    assert filtered[0]["role"] == "system"
    assert filtered[1]["role"] == "user"

    print("✓ Pipeline with duplicates works")


def test_full_pipeline_with_compression():
    """Test pipeline with message compression."""
    settings = get_clean_settings()
    settings.enable_compression = True
    settings.max_total_tokens = 500  # Reasonable budget to force compression but avoid recursion

    # Create long conversation
    messages = [{"role": "system", "content": "System prompt."}]
    for i in range(20):
        messages.append({"role": "user", "content": f"Question {i}: " + "word " * 20})
        messages.append({"role": "assistant", "content": f"Answer {i}: " + "word " * 20})

    original_tokens = count_message_tokens(messages, "gpt-4")

    # Process through pipeline
    filtered = filter_messages(messages, settings)
    compressed = compress_messages(filtered, settings, "gpt-4")

    compressed_tokens = count_message_tokens(compressed, "gpt-4")

    assert compressed_tokens <= settings.max_total_tokens
    assert compressed[0]["role"] == "system"  # System preserved

    print(f"✓ Pipeline compression works: {original_tokens} -> {compressed_tokens} tokens")


def test_metrics_integration():
    """Test metrics tracking through pipeline."""
    metrics = Metrics()

    # Simulate requests
    metrics.record_request(
        upstream_tokens=100, downstream_tokens=50, latency_ms=200.0, tokens_saved_filtering=50
    )
    metrics.record_request(
        upstream_tokens=150,
        downstream_tokens=100,
        latency_ms=300.0,
        cached=True,
        tokens_saved_filtering=50,
    )
    metrics.record_error()

    summary = metrics.summary()

    assert summary["requests_total"] == 2
    assert summary["cache_hits"] == 1
    assert summary["cache_misses"] == 1
    assert summary["cache_hit_rate"] == 0.5
    assert summary["errors_total"] == 1
    assert summary["tokens_saved"] == 100  # (100-50) + max(0, 150-100)

    print("✓ Metrics integration works")


def test_cache_key_determinism():
    """Test that cache keys are deterministic for equivalent requests."""
    cache = LRUCache(max_size=10, ttl_seconds=60)

    # Same content, different order
    request1 = {"messages": [{"role": "user", "content": "Hello"}], "model": "gpt-4"}
    request2 = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

    cache.set(request1, "response")

    # Should be cache hit for equivalent request
    assert cache.get(request2) == "response"

    print("✓ Cache key determinism works")


def test_pipeline_with_empty_messages():
    """Test pipeline handling of empty messages."""
    settings = get_clean_settings()
    settings.remove_empty_messages = True

    messages = [
        {"role": "system", "content": "System."},
        {"role": "user", "content": ""},  # Empty
        {"role": "assistant", "content": ""},  # Empty
        {"role": "user", "content": "Real message"},
    ]

    filtered = filter_messages(messages, settings)

    # Empty user message should be removed
    # Empty assistant without tool_calls should be removed
    assert len(filtered) == 2
    assert filtered[0]["role"] == "system"
    assert filtered[1]["role"] == "user"

    print("✓ Pipeline with empty messages works")


def test_pipeline_with_tool_calls():
    """Test pipeline with tool calls."""
    settings = get_clean_settings()
    settings.remove_empty_messages = True

    messages = [
        {"role": "user", "content": "Use a tool"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"id": "123", "function": {"name": "test"}}],
        },
        {"role": "tool", "content": "Result", "tool_call_id": "123"},
    ]

    filtered = filter_messages(messages, settings)

    # All should be preserved
    assert len(filtered) == 3
    assert filtered[1]["tool_calls"] == [{"id": "123", "function": {"name": "test"}}]
    assert filtered[2]["tool_call_id"] == "123"

    print("✓ Pipeline with tool calls works")


def test_end_to_end_simulation():
    """Simulate end-to-end request processing."""
    settings = get_clean_settings()
    cache = LRUCache(max_size=100, ttl_seconds=300)
    metrics = Metrics()

    # Simulate incoming request
    incoming_request = {
        "model": "gpt-4",
        "messages": [
            {"role": "system", "content": "You are helpful."},
            {"role": "system", "content": "You are helpful."},  # Duplicate
            {"role": "user", "content": "Hello!"},
            {"role": "assistant", "content": ""},  # Empty
            {"role": "user", "content": "How are you?"},
        ],
    }

    # Process messages
    original_messages = incoming_request["messages"]
    filtered_messages = filter_messages(original_messages, settings)
    compressed_messages = compress_messages(filtered_messages, settings, "gpt-4")

    # Prepare transformed payload
    transformed_payload = {"model": incoming_request["model"], "messages": compressed_messages}

    # Check cache
    cached_response = cache.get(transformed_payload)

    if cached_response:
        metrics.record_request(
            upstream_tokens=0,
            downstream_tokens=len(str(cached_response)),
            latency_ms=10.0,
            cached=True,
        )
        response = cached_response
    else:
        # Simulate upstream call
        simulated_response = {"choices": [{"message": {"content": "I'm doing well!"}}]}
        cache.set(transformed_payload, simulated_response)

        metrics.record_request(
            upstream_tokens=count_message_tokens(compressed_messages, "gpt-4"),
            downstream_tokens=50,
            latency_ms=200.0,
            cached=False,
        )
        response = simulated_response

    # Verify results
    assert response is not None
    summary = metrics.summary()
    assert summary["requests_total"] == 1

    # Verify filtering worked
    assert len(compressed_messages) <= len(original_messages)

    print("✓ End-to-end simulation works")


if __name__ == "__main__":
    test_full_pipeline_basic()
    test_full_pipeline_with_duplicates()
    test_full_pipeline_with_compression()
    test_metrics_integration()
    test_cache_key_determinism()
    test_pipeline_with_empty_messages()
    test_pipeline_with_tool_calls()
    test_end_to_end_simulation()
    print("\n✅ All integration tests passed!")
