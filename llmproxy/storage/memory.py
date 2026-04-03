"""In-memory LRU cache storage backend."""

import time
from threading import Lock
from typing import Optional

from .base import StorageBackend


class MemoryBackend(StorageBackend):
    """Thread-safe in-memory LRU cache with TTL support.
    
    This is the default backend and is suitable for single-node deployments.
    For multi-node deployments, use RedisBackend instead.
    """
    
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        super().__init__(ttl_seconds)
        self.max_size = max_size
        self._store: dict[str, dict] = {}
        self._lock = Lock()
    
    def get(self, key: str) -> Optional[dict]:
        """Retrieve a value from memory cache.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            
            # Check TTL
            if time.time() - entry["ts"] > self.ttl_seconds:
                del self._store[key]
                return None
            
            # Move to end (most recently used)
            self._store.pop(key, None)
            self._store[key] = entry
            
            return entry["value"]
    
    def set(self, key: str, value: dict) -> None:
        """Store a value in memory cache.
        
        Args:
            key: Cache key
            value: Value to store
        """
        with self._lock:
            # Remove existing entry to update position
            if key in self._store:
                self._store.pop(key, None)
            # Evict oldest if at capacity
            elif len(self._store) >= self.max_size:
                oldest = next(iter(self._store))
                del self._store[oldest]
            
            self._store[key] = {"ts": time.time(), "value": value}
    
    def delete(self, key: str) -> bool:
        """Delete a value from memory cache.
        
        Args:
            key: Cache key
            
        Returns:
            True if key existed and was deleted
        """
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False
    
    def clear(self) -> None:
        """Clear all values from memory cache."""
        with self._lock:
            self._store.clear()
    
    def stats(self) -> dict:
        """Get memory cache statistics.
        
        Returns:
            Dict with size, max_size, and ttl
        """
        with self._lock:
            return {
                "backend": "memory",
                "size": len(self._store),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "utilization": len(self._store) / self.max_size if self.max_size > 0 else 0
            }
