from __future__ import annotations

"""Storage backends for LLM Proxy cache."""

from .base import StorageBackend
from .memory import MemoryBackend
from typing import Any

__all__ = ["StorageBackend", "MemoryBackend"]

# Optional: Redis backend
try:
    from .redis import RedisBackend

    __all__.append("RedisBackend")
except ImportError:
    pass


def create_backend(backend_type: str, **kwargs: Any) -> StorageBackend:
    """Factory function to create storage backends.

    Args:
        backend_type: Type of backend ('memory' or 'redis')
        **kwargs: Backend-specific configuration

    Returns:
        StorageBackend instance

    Raises:
        ValueError: If backend_type is unknown
        ImportError: If redis backend requested but redis not installed
    """
    backend_type = backend_type.lower()

    if backend_type == "memory":
        return MemoryBackend(
            max_size=kwargs.get("max_size", 1000), ttl_seconds=kwargs.get("ttl_seconds", 300)
        )
    elif backend_type == "redis":
        try:
            from .redis import RedisBackend

            return RedisBackend(
                url=kwargs.get("redis_url", "redis://localhost:6379"),
                ttl_seconds=kwargs.get("ttl_seconds", 300),
                key_prefix=kwargs.get("redis_key_prefix", "llmproxy:"),
            )
        except ImportError:
            raise ImportError(
                "Redis backend requires 'redis' package. Install with: pip install redis"
            )
    else:
        raise ValueError(f"Unknown backend type: {backend_type}. Supported: memory, redis")
