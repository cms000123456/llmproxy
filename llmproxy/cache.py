"""Simple in-memory LRU cache for LLM responses."""

import hashlib
import json
import time
from threading import Lock
from typing import Optional


class LRUCache:
    def __init__(self, max_size: int = 1000, ttl_seconds: int = 300):
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self._store: dict[str, dict] = {}
        self._lock = Lock()

    def _make_key(self, payload: dict) -> str:
        # Deterministic hash of the request body
        canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def get(self, payload: dict) -> Optional[dict]:
        key = self._make_key(payload)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if time.time() - entry["ts"] > self.ttl_seconds:
                del self._store[key]
                return None
            # Move to end (most recently used)
            self._store.pop(key, None)
            self._store[key] = entry
            return entry["value"]

    def set(self, payload: dict, value: dict) -> None:
        key = self._make_key(payload)
        with self._lock:
            if key in self._store:
                self._store.pop(key, None)
            elif len(self._store) >= self.max_size:
                # Evict oldest
                oldest = next(iter(self._store))
                del self._store[oldest]
            self._store[key] = {"ts": time.time(), "value": value}

    def stats(self) -> dict:
        with self._lock:
            return {"size": len(self._store), "max_size": self.max_size, "ttl_seconds": self.ttl_seconds}
