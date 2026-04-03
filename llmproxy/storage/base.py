"""Abstract base class for storage backends."""

from abc import ABC, abstractmethod
from typing import Optional


class StorageBackend(ABC):
    """Abstract base class for cache storage backends.

    Implementations must provide thread-safe/async-safe operations.
    """

    def __init__(self, ttl_seconds: int = 300):
        self.ttl_seconds = ttl_seconds

    @abstractmethod
    def get(self, key: str) -> Optional[dict]:
        """Retrieve a value from storage.

        Args:
            key: Cache key

        Returns:
            Cached value dict or None if not found/expired
        """
        pass

    @abstractmethod
    def set(self, key: str, value: dict) -> None:
        """Store a value in storage.

        Args:
            key: Cache key
            value: Value to store
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete a value from storage.

        Args:
            key: Cache key

        Returns:
            True if key existed and was deleted, False otherwise
        """
        pass

    @abstractmethod
    def clear(self) -> None:
        """Clear all values from storage."""
        pass

    @abstractmethod
    def stats(self) -> dict:
        """Get storage statistics.

        Returns:
            Dict with backend-specific stats
        """
        pass

    def health_check(self) -> bool:
        """Check if storage backend is healthy.

        Returns:
            True if healthy, False otherwise
        """
        return True
