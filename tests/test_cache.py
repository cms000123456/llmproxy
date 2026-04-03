#!/usr/bin/env python3
"""Tests for LRU Cache implementation."""

import threading
import time

from llmproxy.cache import LRUCache


def test_basic_get_set():
    """Test basic cache operations."""
    cache = LRUCache(max_size=10, ttl_seconds=60)

    # Test get on empty cache
    assert cache.get({"key": "value"}) is None

    # Test set and get
    payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
    response = {"choices": [{"message": {"content": "hello"}}]}
    cache.set(payload, response)

    assert cache.get(payload) == response
    print("✓ Basic get/set works")


def test_ttl_expiration():
    """Test that entries expire after TTL."""
    cache = LRUCache(max_size=10, ttl_seconds=1)  # 1 second TTL

    payload = {"model": "gpt-4", "prompt": "test"}
    response = {"result": "ok"}
    cache.set(payload, response)

    # Should exist immediately
    assert cache.get(payload) == response

    # Wait for TTL to expire
    time.sleep(1.1)

    # Should be expired now
    assert cache.get(payload) is None
    print("✓ TTL expiration works")


def test_lru_eviction():
    """Test LRU eviction when max_size is reached."""
    cache = LRUCache(max_size=3, ttl_seconds=60)

    # Add 3 items
    cache.set({"id": 1}, "value1")
    cache.set({"id": 2}, "value2")
    cache.set({"id": 3}, "value3")

    # Access item 1 to make it recently used
    cache.get({"id": 1})

    # Add 4th item - should evict item 2 (least recently used)
    cache.set({"id": 4}, "value4")

    assert cache.get({"id": 1}) == "value1"  # Still there (recently used)
    assert cache.get({"id": 2}) is None  # Evicted
    assert cache.get({"id": 3}) == "value3"  # Still there
    assert cache.get({"id": 4}) == "value4"  # New item
    print("✓ LRU eviction works")


def test_update_existing_key():
    """Test updating an existing key."""
    cache = LRUCache(max_size=10, ttl_seconds=60)

    payload = {"model": "gpt-4"}
    cache.set(payload, "old_value")
    cache.set(payload, "new_value")

    assert cache.get(payload) == "new_value"
    print("✓ Update existing key works")


def test_stats():
    """Test cache statistics."""
    cache = LRUCache(max_size=100, ttl_seconds=300)

    stats = cache.stats()
    assert stats["size"] == 0
    assert stats["max_size"] == 100
    assert stats["ttl_seconds"] == 300

    cache.set({"key": "value"}, "result")
    stats = cache.stats()
    assert stats["size"] == 1
    print("✓ Cache stats work")


def test_deterministic_hash():
    """Test that equivalent payloads produce the same hash."""
    cache = LRUCache(max_size=10, ttl_seconds=60)

    # Same content, different key order
    payload1 = {"model": "gpt-4", "messages": [{"role": "user", "content": "hi"}]}
    payload2 = {"messages": [{"role": "user", "content": "hi"}], "model": "gpt-4"}

    cache.set(payload1, "response")
    assert cache.get(payload2) == "response"
    print("✓ Deterministic hashing works (key order independent)")


def test_thread_safety():
    """Test thread-safe operations."""
    cache = LRUCache(max_size=100, ttl_seconds=60)
    errors = []

    def writer():
        try:
            for i in range(100):
                cache.set({"id": i}, f"value{i}")
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for i in range(100):
                cache.get({"id": i})
        except Exception as e:
            errors.append(e)

    threads = []
    for _ in range(5):
        threads.append(threading.Thread(target=writer))
        threads.append(threading.Thread(target=reader))

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"Thread safety errors: {errors}"
    print("✓ Thread safety works")


if __name__ == "__main__":
    test_basic_get_set()
    test_ttl_expiration()
    test_lru_eviction()
    test_update_existing_key()
    test_stats()
    test_deterministic_hash()
    test_thread_safety()
    print("\n✅ All cache tests passed!")
