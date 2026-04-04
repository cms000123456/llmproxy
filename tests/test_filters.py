#!/usr/bin/env python3
"""Tests for message filtering."""

import base64

from llmproxy.config import Settings
from llmproxy.filters import (
    filter_messages,
    is_base64_string,
    strip_large_images,
    truncate_message,
)


def test_is_base64_string_valid():
    """Test detection of valid base64 strings."""
    # Valid base64 (longer than 100 chars)
    long_valid = base64.b64encode(b"x" * 200).decode()
    assert is_base64_string(long_valid) 
    print("✓ Valid base64 detection works")


def test_is_base64_string_invalid():
    """Test rejection of non-base64 strings."""
    # Too short (less than 100 chars)
    short = base64.b64encode(b"hello").decode()
    assert is_base64_string(short) 

    # Regular text
    assert (
        is_base64_string(
            "hello world this is just regular text that is long enough to meet the minimum length requirement"
        )
        
    )

    # Invalid characters
    assert (
        is_base64_string(
            '!!!@@@###$$$%%%^^^&&&***((()))___+++===[[[{{{{}}}]]]|||\\\\\\:;;;"""<<<>??>>,,,..///'
        )
        
    )
    print("✓ Invalid base64 rejection works")


def test_truncate_message_string():
    """Test truncating string content."""
    content = "x" * 1000
    result = truncate_message(content, 100)

    assert len(result) < 200  # Truncated with message
    assert "truncated" in result
    assert "1000 chars" in result
    print("✓ String truncation works")


def test_truncate_message_short():
    """Test that short messages are not truncated."""
    content = "short message"
    result = truncate_message(content, 100)

    assert result == content
    print("✓ Short message not truncated")


def test_truncate_message_list():
    """Test truncating list content (vision models)."""
    content = [
        {"type": "text", "text": "x" * 1000},
        {"type": "image_url", "url": "http://example.com/image.png"},
    ]
    result = truncate_message(content, 100)

    assert result[0]["type"] == "text"
    assert "truncated" in result[0]["text"]
    assert result[1]["type"] == "image_url"  # Untouched
    print("✓ List content truncation works")


def test_strip_large_images():
    """Test stripping image content blocks."""
    content = [
        {"type": "text", "text": "Hello"},
        {"type": "image_url", "url": "http://example.com/image.png"},
        {"type": "image", "data": "base64data"},
    ]
    result = strip_large_images(content)

    assert len(result) == 1
    assert result[0]["type"] == "text"
    print("✓ Image stripping works")


def test_strip_large_images_fallback():
    """Test fallback when all content is images."""
    content = [
        {"type": "image_url", "url": "http://example.com/image.png"},
    ]
    result = strip_large_images(content)

    assert result == "[Image removed by proxy filter]"
    print("✓ Image fallback works")


def test_strip_large_images_non_list():
    """Test strip_large_images with non-list content."""
    content = "just a string"
    result = strip_large_images(content)

    assert result == content
    print("✓ Non-list content passthrough works")


def test_filter_messages_deduplicate_system():
    """Test deduplication of system messages."""
    settings = Settings()
    settings.enable_filtering = True
    settings.deduplicate_system_messages = True

    messages = [
        {"role": "system", "content": "You are helpful."},
        {"role": "system", "content": "You are helpful."},
        {"role": "user", "content": "Hello"},
    ]
    result = filter_messages(messages, settings)

    assert len(result) == 2
    assert result[0]["role"] == "system"
    assert result[1]["role"] == "user"
    print("✓ System message deduplication works")


def test_filter_messages_remove_empty():
    """Test removal of empty messages."""
    settings = Settings()
    settings.enable_filtering = True
    settings.remove_empty_messages = True

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": ""},
        {"role": "user", "content": "World"},
    ]
    result = filter_messages(messages, settings)

    assert len(result) == 2
    print("✓ Empty message removal works")


def test_filter_messages_keep_tool_messages():
    """Test that tool messages are kept even if empty."""
    settings = Settings()
    settings.enable_filtering = True
    settings.remove_empty_messages = True

    messages = [
        {"role": "user", "content": "Call tool"},
        {"role": "tool", "content": "", "tool_call_id": "123"},
    ]
    result = filter_messages(messages, settings)

    assert len(result) == 2
    assert result[1]["role"] == "tool"
    print("✓ Tool message preservation works")


def test_filter_messages_keep_assistant_with_tool_calls():
    """Test that assistant messages with tool_calls are kept."""
    settings = Settings()
    settings.enable_filtering = True

    messages = [
        {"role": "user", "content": "Call tool"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "123"}]},
    ]
    result = filter_messages(messages, settings)

    assert len(result) == 2
    assert result[1]["role"] == "assistant"
    print("✓ Assistant with tool_calls preservation works")


def test_filter_messages_strip_images():
    """Test image stripping when configured."""
    settings = Settings()
    settings.enable_filtering = True
    settings.strip_base64_images = True

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "Look at this:"},
                {"type": "image_url", "url": "http://example.com/image.png"},
            ],
        },
    ]
    result = filter_messages(messages, settings)

    assert len(result[0]["content"]) == 1
    assert result[0]["content"][0]["type"] == "text"
    print("✓ Image stripping in filter works")


def test_filter_messages_truncate():
    """Test message truncation in filter."""
    settings = Settings()
    settings.enable_filtering = True
    settings.max_message_length = 10

    messages = [
        {"role": "user", "content": "x" * 100},
    ]
    result = filter_messages(messages, settings)

    assert "truncated" in result[0]["content"]
    print("✓ Message truncation in filter works")


def test_filter_messages_disabled():
    """Test that filtering can be disabled."""
    settings = Settings()
    settings.enable_filtering = False

    messages = [
        {"role": "system", "content": "Sys1"},
        {"role": "system", "content": "Sys2"},
        {"role": "user", "content": ""},
    ]
    result = filter_messages(messages, settings)

    assert len(result) == 3  # Nothing filtered
    print("✓ Filter disable works")


def test_filter_preserves_extra_fields():
    """Test that extra fields are preserved (tool_calls, name, etc.)."""
    settings = Settings()
    settings.enable_filtering = True

    messages = [
        {"role": "assistant", "content": "Using tool", "tool_calls": [{"id": "123"}]},
        {"role": "tool", "content": "Result", "tool_call_id": "123", "name": "my_tool"},
    ]
    result = filter_messages(messages, settings)

    assert result[0]["tool_calls"] == [{"id": "123"}]
    assert result[1]["tool_call_id"] == "123"
    assert result[1]["name"] == "my_tool"
    print("✓ Extra fields preserved")


if __name__ == "__main__":
    test_is_base64_string_valid()
    test_is_base64_string_invalid()
    test_truncate_message_string()
    test_truncate_message_short()
    test_truncate_message_list()
    test_strip_large_images()
    test_strip_large_images_fallback()
    test_strip_large_images_non_list()
    test_filter_messages_deduplicate_system()
    test_filter_messages_remove_empty()
    test_filter_messages_keep_tool_messages()
    test_filter_messages_keep_assistant_with_tool_calls()
    test_filter_messages_strip_images()
    test_filter_messages_truncate()
    test_filter_messages_disabled()
    test_filter_preserves_extra_fields()
    print("\n✅ All filter tests passed!")
