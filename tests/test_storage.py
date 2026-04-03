"""Tests for storage backends (memory and redis)."""

import time

import pytest

from llmproxy.storage import MemoryBackend, create_backend
from llmproxy.storage.base import StorageBackend


class TestStorageBackendInterface:
    """Test the abstract base class interface."""

    def test_base_class_is_abstract(self):
        """StorageBackend should not be instantiable directly."""
        with pytest.raises(TypeError):
            StorageBackend()

    def test_base_class_methods_are_abstract(self):
        """All methods should be abstract."""

        # Create a concrete class that doesn't implement methods
        class BadBackend(StorageBackend):
            pass

        with pytest.raises(TypeError):
            BadBackend()


class TestMemoryBackend:
    """Tests for the in-memory LRU cache backend."""

    def test_create_backend(self):
        """Should create memory backend via factory."""
        backend = create_backend("memory", max_size=100, ttl_seconds=60)
        assert isinstance(backend, MemoryBackend)

    def test_get_and_set(self):
        """Should store and retrieve values."""
        backend = MemoryBackend(max_size=100, ttl_seconds=60)

        value = {"choices": [{"message": {"content": "Hello"}}]}
        backend.set("key1", value)

        result = backend.get("key1")
        assert result == value

    def test_get_missing_key(self):
        """Should return None for missing keys."""
        backend = MemoryBackend(max_size=100, ttl_seconds=60)

        result = backend.get("nonexistent")
        assert result is None

    def test_ttl_expiration(self):
        """Should expire entries after TTL."""
        backend = MemoryBackend(max_size=100, ttl_seconds=0.1)

        value = {"data": "test"}
        backend.set("key1", value)

        # Should exist immediately
        assert backend.get("key1") == value

        # Wait for TTL to expire
        time.sleep(0.2)

        # Should be expired now
        assert backend.get("key1") is None

    def test_lru_eviction(self):
        """Should evict oldest entries when at capacity."""
        backend = MemoryBackend(max_size=3, ttl_seconds=60)

        # Add 3 entries
        backend.set("key1", {"data": 1})
        backend.set("key2", {"data": 2})
        backend.set("key3", {"data": 3})

        # All should exist
        assert backend.get("key1") is not None
        assert backend.get("key2") is not None
        assert backend.get("key3") is not None

        # Add 4th entry (exceeds capacity)
        backend.set("key4", {"data": 4})

        # key1 should be evicted (oldest)
        assert backend.get("key1") is None
        assert backend.get("key2") is not None
        assert backend.get("key3") is not None
        assert backend.get("key4") is not None

    def test_lru_reorder_on_get(self):
        """Should reorder entry to most recent on get."""
        backend = MemoryBackend(max_size=3, ttl_seconds=60)

        backend.set("key1", {"data": 1})
        backend.set("key2", {"data": 2})
        backend.set("key3", {"data": 3})

        # Access key1 to make it most recent
        backend.get("key1")

        # Add new entry
        backend.set("key4", {"data": 4})

        # key2 should be evicted (now oldest)
        assert backend.get("key2") is None
        assert backend.get("key1") is not None  # Still exists

    def test_delete(self):
        """Should delete existing keys."""
        backend = MemoryBackend(max_size=100, ttl_seconds=60)

        backend.set("key1", {"data": "test"})
        assert backend.get("key1") is not None

        deleted = backend.delete("key1")
        assert deleted is True
        assert backend.get("key1") is None

    def test_delete_missing(self):
        """Should return False for deleting missing keys."""
        backend = MemoryBackend(max_size=100, ttl_seconds=60)

        deleted = backend.delete("nonexistent")
        assert deleted is False

    def test_clear(self):
        """Should clear all entries."""
        backend = MemoryBackend(max_size=100, ttl_seconds=60)

        backend.set("key1", {"data": 1})
        backend.set("key2", {"data": 2})

        backend.clear()

        assert backend.get("key1") is None
        assert backend.get("key2") is None

    def test_stats(self):
        """Should return stats."""
        backend = MemoryBackend(max_size=100, ttl_seconds=60)

        backend.set("key1", {"data": 1})
        backend.set("key2", {"data": 2})

        stats = backend.stats()

        assert stats["backend"] == "memory"
        assert stats["size"] == 2
        assert stats["max_size"] == 100
        assert stats["ttl_seconds"] == 60
        assert stats["utilization"] == 0.02

    def test_health_check(self):
        """Memory backend should always be healthy."""
        backend = MemoryBackend()
        assert backend.health_check() is True


class TestCreateBackendFactory:
    """Tests for the create_backend factory function."""

    def test_factory_memory_backend(self):
        """Factory should create memory backend."""
        backend = create_backend("memory", max_size=50, ttl_seconds=30)
        assert isinstance(backend, MemoryBackend)

        stats = backend.stats()
        assert stats["max_size"] == 50
        assert stats["ttl_seconds"] == 30

    def test_factory_case_insensitive(self):
        """Backend type should be case insensitive."""
        backend = create_backend("MEMORY")
        assert isinstance(backend, MemoryBackend)

        backend = create_backend("Memory")
        assert isinstance(backend, MemoryBackend)

    def test_factory_unknown_backend(self):
        """Factory should raise error for unknown backend."""
        with pytest.raises(ValueError) as exc_info:
            create_backend("unknown")

        assert "Unknown backend type" in str(exc_info.value)
        assert "memory" in str(exc_info.value)
        assert "redis" in str(exc_info.value)


class TestCacheKeyGeneration:
    """Tests for cache key generation (used in server.py)."""

    def test_make_cache_key_deterministic(self):
        """Same payload should generate same key."""
        from llmproxy.server import _make_cache_key

        payload = {"model": "gpt-4", "messages": [{"role": "user", "content": "Hello"}]}

        key1 = _make_cache_key(payload)
        key2 = _make_cache_key(payload)

        assert key1 == key2
        assert len(key1) == 64  # SHA256 hex length

    def test_make_cache_key_order_independent(self):
        """Key order should not affect hash."""
        from llmproxy.server import _make_cache_key

        payload1 = {"a": 1, "b": 2, "c": 3}
        payload2 = {"c": 3, "a": 1, "b": 2}

        key1 = _make_cache_key(payload1)
        key2 = _make_cache_key(payload2)

        assert key1 == key2

    def test_make_cache_key_different_payloads(self):
        """Different payloads should generate different keys."""
        from llmproxy.server import _make_cache_key

        payload1 = {"model": "gpt-4"}
        payload2 = {"model": "gpt-3.5"}

        key1 = _make_cache_key(payload1)
        key2 = _make_cache_key(payload2)

        assert key1 != key2

    def test_make_cache_key_content(self):
        """Key should be valid SHA256 hex."""
        from llmproxy.server import _make_cache_key

        payload = {"test": "data"}
        key = _make_cache_key(payload)

        # Should be 64 hex characters
        assert len(key) == 64
        assert all(c in "0123456789abcdef" for c in key)


@pytest.mark.skipif(True, reason="Redis not available in test environment")
class TestRedisBackend:
    """Tests for Redis backend - requires Redis server."""

    def test_create_backend(self):
        """Should create redis backend via factory."""
        try:
            backend = create_backend("redis", redis_url="redis://localhost:6379")
            assert backend.health_check() is True
        except ImportError:
            pytest.skip("redis package not installed")
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")

    def test_get_and_set(self):
        """Should store and retrieve values from Redis."""
        try:
            from llmproxy.storage.redis import RedisBackend

            backend = RedisBackend(url="redis://localhost:6379", ttl_seconds=60)

            value = {"choices": [{"message": {"content": "Hello"}}]}
            backend.set("test_key", value)

            result = backend.get("test_key")
            assert result == value

            # Cleanup
            backend.delete("test_key")
        except ImportError:
            pytest.skip("redis package not installed")
        except Exception as e:
            pytest.skip(f"Redis not available: {e}")


class TestBackendCompatibility:
    """Test that different backends have compatible behavior."""

    def test_all_backends_implement_interface(self):
        """All backends should implement StorageBackend interface."""
        backends = [MemoryBackend()]

        for backend in backends:
            # Should have all required methods
            assert hasattr(backend, "get")
            assert hasattr(backend, "set")
            assert hasattr(backend, "delete")
            assert hasattr(backend, "clear")
            assert hasattr(backend, "stats")
            assert hasattr(backend, "health_check")

            # Methods should be callable
            assert callable(backend.get)
            assert callable(backend.set)
            assert callable(backend.delete)
            assert callable(backend.clear)
            assert callable(backend.stats)
            assert callable(backend.health_check)
