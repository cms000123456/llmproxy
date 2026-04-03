"""Lightweight metrics tracking."""

import time
from dataclasses import dataclass, field
from threading import Lock


@dataclass
class Metrics:
    requests_total: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    tokens_upstream: int = 0
    tokens_downstream: int = 0
    tokens_saved: int = 0  # Tokens saved from filtering/compression
    errors_total: int = 0
    latencies: list[float] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock)

    def record_request(
        self,
        upstream_tokens: int,
        downstream_tokens: int,
        latency_ms: float,
        cached: bool = False,
        tokens_saved_filtering: int = 0
    ):
        """Record request metrics.
        
        Args:
            upstream_tokens: Number of tokens sent upstream (after filtering/compression)
            downstream_tokens: Number of tokens in the response
            latency_ms: Request latency in milliseconds
            cached: Whether the response was served from cache
            tokens_saved_filtering: Tokens saved by filtering/compression (before sending)
        """
        with self._lock:
            self.requests_total += 1
            self.tokens_upstream += upstream_tokens
            self.tokens_downstream += downstream_tokens
            self.tokens_saved += tokens_saved_filtering
            self.latencies.append(latency_ms)
            # Keep latencies bounded
            if len(self.latencies) > 10_000:
                self.latencies = self.latencies[-5_000:]
            if cached:
                self.cache_hits += 1
            else:
                self.cache_misses += 1

    def record_error(self):
        with self._lock:
            self.errors_total += 1

    def summary(self) -> dict:
        with self._lock:
            avg_latency = sum(self.latencies) / len(self.latencies) if self.latencies else 0.0
            return {
                "requests_total": self.requests_total,
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "cache_hit_rate": round(self.cache_hits / max(1, self.requests_total), 4),
                "tokens_upstream": self.tokens_upstream,
                "tokens_downstream": self.tokens_downstream,
                "tokens_saved": self.tokens_saved,
                "errors_total": self.errors_total,
                "avg_latency_ms": round(avg_latency, 2),
            }


METRICS = Metrics()
