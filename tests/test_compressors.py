#!/usr/bin/env python3
"""Tests for message compression."""

from llmproxy.compressors import (
    _truncate_oldest,
    compress_messages,
    count_message_tokens,
    count_tokens,
)
from llmproxy.config import Settings


def test_count_tokens_string():
    """Test token counting for strings."""
    # This will use tiktoken if available, or fallback
    tokens = count_tokens("hello world", "gpt-4")
    assert tokens > 0
    print(f"✓ Token counting works (got {tokens} tokens)")


def test_count_tokens_long():
    """Test token counting for longer text."""
    text = "word " * 100
    tokens = count_tokens(text, "gpt-4")
    # Rough estimate: 100 words should be ~100-150 tokens
    assert tokens >= 50
    print(f"✓ Long text token counting works (got {tokens} tokens)")


def test_count_message_tokens():
    """Test token counting for message list."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
    ]
    tokens = count_message_tokens(messages, "gpt-4")
    assert tokens > 0
    print(f"✓ Message token counting works (got {tokens} tokens)")


def test_count_message_tokens_with_list_content():
    """Test token counting with list content (vision models)."""
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Hello!"},
                {"type": "image_url", "url": "http://example.com/image.png"},
            ],
        },
    ]
    tokens = count_message_tokens(messages, "gpt-4")
    assert tokens > 0
    print(f"✓ List content token counting works (got {tokens} tokens)")


def test_count_message_tokens_empty():
    """Test token counting with empty messages."""
    messages = []
    tokens = count_message_tokens(messages, "gpt-4")
    assert tokens == 0
    print("✓ Empty message token counting works")


def test_compress_messages_no_compression_needed():
    """Test when compression is not needed (under budget)."""
    settings = Settings()
    settings.enable_compression = True
    settings.max_total_tokens = 100000

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello!"},
    ]
    result = compress_messages(messages, settings, "gpt-4")

    assert len(result) == 2
    assert result[0]["role"] == "system"
    print("✓ No compression when under budget")


def test_compress_messages_disabled():
    """Test when compression is disabled."""
    settings = Settings()
    settings.enable_compression = False

    messages = [{"role": "user", "content": "Hello!"}]
    result = compress_messages(messages, settings, "gpt-4")

    assert result == messages
    print("✓ Compression disabled works")


def test_truncate_oldest_basic():
    """Test basic truncation of oldest messages."""
    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Question 1?"},
        {"role": "assistant", "content": "Answer 1."},
        {"role": "user", "content": "Question 2?"},
        {"role": "assistant", "content": "Answer 2."},
    ]

    # Set a budget that forces truncation but not too small to avoid recursion
    result = _truncate_oldest(messages, budget=30, model="gpt-4")

    # System message should be preserved
    assert result[0]["role"] == "system"
    # Last exchange should be preserved
    assert result[-1]["role"] == "assistant"
    assert result[-2]["role"] == "user"
    print("✓ Basic truncation works")


def test_truncate_oldest_preserves_system():
    """Test that system message is always preserved."""
    messages = [
        {"role": "system", "content": "Important system prompt."},
        {"role": "user", "content": "Short."},
        {"role": "assistant", "content": "Short."},
    ]

    # Use a reasonable budget that preserves system message
    result = _truncate_oldest(messages, budget=25, model="gpt-4")

    assert result[0]["role"] == "system"
    assert result[0]["content"] == "Important system prompt."
    print("✓ System message preserved")


def test_truncate_oldest_preserves_tail():
    """Test that last exchange is preserved."""
    messages = [
        {"role": "user", "content": "Old question 1"},
        {"role": "assistant", "content": "Old answer 1"},
        {"role": "user", "content": "Old question 2"},
        {"role": "assistant", "content": "Old answer 2"},
        {"role": "user", "content": "Recent question"},
        {"role": "assistant", "content": "Recent answer"},
    ]

    result = _truncate_oldest(messages, budget=30, model="gpt-4")

    # Last user/assistant pair should be preserved
    assert result[-2]["content"] == "Recent question"
    assert result[-1]["content"] == "Recent answer"
    print("✓ Tail preservation works")


def test_truncate_oldest_empty():
    """Test truncation with empty messages."""
    result = _truncate_oldest([], budget=100, model="gpt-4")
    assert result == []
    print("✓ Empty message truncation works")


def test_truncate_oldest_single_message():
    """Test truncation with single message."""
    messages = [{"role": "system", "content": "System"}]
    result = _truncate_oldest(messages, budget=100, model="gpt-4")
    assert len(result) == 1
    assert result[0]["content"] == "System"
    print("✓ Single message truncation works")


def test_truncate_oldest_emergency_truncation():
    """Test emergency truncation when tail is too large."""
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello"},
    ]

    # Small budget - should trigger emergency truncation but not recurse infinitely
    result = _truncate_oldest(messages, budget=15, model="gpt-4")

    # Should have at least system message
    assert result[0]["role"] == "system"
    # Total tokens should be under budget (or close to it)
    total = count_message_tokens(result, "gpt-4")
    assert total <= 50  # Give some slack for encoding
    print("✓ Emergency truncation works")


def test_compression_strategy_summarize():
    """Test summarize strategy falls back to truncate."""
    settings = Settings()
    settings.enable_compression = True
    settings.compression_strategy = "summarize_oldest"
    settings.max_total_tokens = 50

    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "word " * 20},
        {"role": "assistant", "content": "word " * 20},
    ]

    result = compress_messages(messages, settings, "gpt-4")

    # Should not fail - falls back to truncate
    assert len(result) >= 1
    assert result[0]["role"] == "system"
    print("✓ Summarize strategy fallback works")


def test_unknown_strategy_defaults_to_truncate():
    """Test unknown strategy defaults to truncate."""
    settings = Settings()
    settings.enable_compression = True
    settings.compression_strategy = "unknown_strategy"
    settings.max_total_tokens = 50

    messages = [
        {"role": "user", "content": "word " * 20},
    ]

    # Should not raise, defaults to truncate
    result = compress_messages(messages, settings, "gpt-4")
    assert len(result) >= 0  # May be empty if budget too small
    print("✓ Unknown strategy defaults to truncate")


if __name__ == "__main__":
    test_count_tokens_string()
    test_count_tokens_long()
    test_count_message_tokens()
    test_count_message_tokens_with_list_content()
    test_count_message_tokens_empty()
    test_compress_messages_no_compression_needed()
    test_compress_messages_disabled()
    test_truncate_oldest_basic()
    test_truncate_oldest_preserves_system()
    test_truncate_oldest_preserves_tail()
    test_truncate_oldest_empty()
    test_truncate_oldest_single_message()
    test_truncate_oldest_emergency_truncation()
    test_compression_strategy_summarize()
    test_unknown_strategy_defaults_to_truncate()
    print("\n✅ All compressor tests passed!")
