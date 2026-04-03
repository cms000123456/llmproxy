"""Redis storage backend for distributed caching."""

import json
import logging
from typing import Optional

try:
    import redis
    from redis.exceptions import RedisError
except ImportError:
    redis = None
    RedisError = Exception

from .base import StorageBackend

logger = logging.getLogger(__name__)


class RedisBackend(StorageBackend):
    """Redis-based cache backend for distributed deployments.
    
    Supports Redis standalone, Redis Cluster, and Redis Sentinel.
    
    Example URLs:
    - redis://localhost:6379/0
    - redis://username:password@localhost:6379/0
    - rediss://localhost:6379/0 (SSL)
    - redis+sentinel://localhost:26379/0?service_name=mymaster
    """
    
    def __init__(
        self,
        url: str = "redis://localhost:6379",
        ttl_seconds: int = 300,
        key_prefix: str = "llmproxy:",
        socket_timeout: float = 5.0,
        socket_connect_timeout: float = 5.0,
        health_check_interval: int = 30,
    ):
        super().__init__(ttl_seconds)
        self.url = url
        self.key_prefix = key_prefix
        self._client: Optional[redis.Redis] = None
        
        if redis is None:
            raise ImportError(
                "Redis backend requires 'redis' package. "
                "Install with: pip install redis"
            )
        
        try:
            self._client = redis.from_url(
                url,
                socket_timeout=socket_timeout,
                socket_connect_timeout=socket_connect_timeout,
                health_check_interval=health_check_interval,
                decode_responses=True,
            )
            # Test connection
            self._client.ping()
            logger.info(f"Connected to Redis at {url}")
        except RedisError as e:
            logger.error(f"Failed to connect to Redis: {e}")
            raise
    
    def _make_key(self, key: str) -> str:
        """Add prefix to key."""
        return f"{self.key_prefix}{key}"
    
    def get(self, key: str) -> Optional[dict]:
        """Retrieve a value from Redis.
        
        Args:
            key: Cache key
            
        Returns:
            Cached value or None if not found/expired
        """
        if self._client is None:
            return None
        
        try:
            data = self._client.get(self._make_key(key))
            if data is None:
                return None
            return json.loads(data)
        except RedisError as e:
            logger.warning(f"Redis get error: {e}")
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Failed to decode cached value: {e}")
            return None
    
    def set(self, key: str, value: dict) -> None:
        """Store a value in Redis.
        
        Args:
            key: Cache key
            value: Value to store
        """
        if self._client is None:
            return
        
        try:
            serialized = json.dumps(value, ensure_ascii=False)
            self._client.setex(
                self._make_key(key),
                self.ttl_seconds,
                serialized
            )
        except RedisError as e:
            logger.warning(f"Redis set error: {e}")
        except (TypeError, ValueError) as e:
            logger.error(f"Failed to serialize value: {e}")
    
    def delete(self, key: str) -> bool:
        """Delete a value from Redis.
        
        Args:
            key: Cache key
            
        Returns:
            True if key existed and was deleted
        """
        if self._client is None:
            return False
        
        try:
            result = self._client.delete(self._make_key(key))
            return result > 0
        except RedisError as e:
            logger.warning(f"Redis delete error: {e}")
            return False
    
    def clear(self) -> None:
        """Clear all values with our key prefix.
        
        Warning: This uses KEYS command which can be slow on large databases.
        Consider using a separate Redis DB or SCAN for production.
        """
        if self._client is None:
            return
        
        try:
            pattern = f"{self.key_prefix}*"
            # Use scan_iter to avoid blocking Redis
            for key in self._client.scan_iter(match=pattern):
                self._client.delete(key)
            logger.info(f"Cleared Redis cache with prefix: {self.key_prefix}")
        except RedisError as e:
            logger.error(f"Redis clear error: {e}")
    
    def stats(self) -> dict:
        """Get Redis cache statistics.
        
        Returns:
            Dict with backend info and Redis stats
        """
        if self._client is None:
            return {
                "backend": "redis",
                "connected": False,
                "url": self.url,
                "key_prefix": self.key_prefix,
            }
        
        try:
            info = self._client.info()
            # Count our keys
            pattern = f"{self.key_prefix}*"
            key_count = sum(1 for _ in self._client.scan_iter(match=pattern))
            
            return {
                "backend": "redis",
                "connected": True,
                "url": self.url,
                "key_prefix": self.key_prefix,
                "size": key_count,
                "ttl_seconds": self.ttl_seconds,
                "redis_version": info.get("redis_version"),
                "used_memory_human": info.get("used_memory_human"),
                "total_keys": info.get("db0", {}).get("keys", 0) if "db0" in info else None,
            }
        except RedisError as e:
            logger.warning(f"Redis stats error: {e}")
            return {
                "backend": "redis",
                "connected": False,
                "url": self.url,
                "error": str(e),
            }
    
    def health_check(self) -> bool:
        """Check if Redis connection is healthy.
        
        Returns:
            True if Redis is reachable
        """
        if self._client is None:
            return False
        
        try:
            return self._client.ping()
        except RedisError:
            return False
