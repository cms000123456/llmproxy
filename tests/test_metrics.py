#!/usr/bin/env python3
"""Tests for metrics tracking."""

import threading
from llmproxy.metrics import Metrics


def test_initial_state():
    """Test initial metrics state."""
    m = Metrics()
    assert m.requests_total == 0
    assert m.cache_hits == 0
    assert m.cache_misses == 0
    assert m.tokens_upstream == 0
    assert m.tokens_downstream == 0
    assert m.tokens_saved == 0
    assert m.errors_total == 0
    assert m.latencies == []
    print("✓ Initial state correct")


def test_record_request():
    """Test recording a request."""
    m = Metrics()
    m.record_request(
        upstream_tokens=100,
        downstream_tokens=50,
        latency_ms=200.0,
        cached=False,
        tokens_saved_filtering=25
    )
    
    assert m.requests_total == 1
    assert m.cache_misses == 1
    assert m.cache_hits == 0
    assert m.tokens_upstream == 100
    assert m.tokens_downstream == 50
    assert m.tokens_saved == 25  # From filtering
    assert m.latencies == [200.0]
    print("✓ Record request works")


def test_record_cached_request():
    """Test recording a cached request."""
    m = Metrics()
    m.record_request(
        upstream_tokens=100,
        downstream_tokens=100,
        latency_ms=50.0,
        cached=True,
        tokens_saved_filtering=10
    )
    
    assert m.requests_total == 1
    assert m.cache_hits == 1
    assert m.cache_misses == 0
    assert m.tokens_saved == 10
    print("✓ Record cached request works")


def test_record_multiple_requests():
    """Test recording multiple requests."""
    m = Metrics()
    
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=100.0, tokens_saved_filtering=25)
    m.record_request(upstream_tokens=200, downstream_tokens=150, latency_ms=200.0, cached=True, tokens_saved_filtering=50)
    m.record_request(upstream_tokens=100, downstream_tokens=100, latency_ms=150.0, tokens_saved_filtering=0)
    
    assert m.requests_total == 3
    assert m.cache_hits == 1
    assert m.cache_misses == 2
    assert m.tokens_upstream == 400
    assert m.tokens_downstream == 300
    assert m.tokens_saved == 75  # 25 + 50 + 0
    assert m.latencies == [100.0, 200.0, 150.0]
    print("✓ Record multiple requests works")


def test_record_error():
    """Test recording errors."""
    m = Metrics()
    m.record_error()
    m.record_error()
    
    assert m.errors_total == 2
    print("✓ Record error works")


def test_summary():
    """Test summary generation."""
    m = Metrics()
    
    # Empty summary
    summary = m.summary()
    assert summary["requests_total"] == 0
    assert summary["cache_hit_rate"] == 0.0
    assert summary["avg_latency_ms"] == 0.0
    
    # Add some data
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=100.0, cached=True, tokens_saved_filtering=25)
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=200.0, cached=False, tokens_saved_filtering=25)
    
    summary = m.summary()
    assert summary["requests_total"] == 2
    assert summary["cache_hits"] == 1
    assert summary["cache_misses"] == 1
    assert summary["cache_hit_rate"] == 0.5
    assert summary["avg_latency_ms"] == 150.0
    assert summary["tokens_upstream"] == 200
    assert summary["tokens_downstream"] == 100
    assert summary["tokens_saved"] == 50  # 25 + 25
    assert summary["errors_total"] == 0
    print("✓ Summary works")


def test_concurrent_access():
    """Test thread safety."""
    m = Metrics()
    
    def record_batch():
        for i in range(100):
            m.record_request(upstream_tokens=10, downstream_tokens=5, latency_ms=float(i), tokens_saved_filtering=5)
    
    threads = [threading.Thread(target=record_batch) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert m.requests_total == 500
    assert m.tokens_upstream == 5000
    assert m.tokens_downstream == 2500
    assert m.tokens_saved == 2500  # 5 * 500
    print("✓ Concurrent access works")


def test_latencies_bounded():
    """Test that latencies list stays bounded."""
    m = Metrics()
    
    # Add many latencies
    for i in range(15_000):
        m.record_request(upstream_tokens=10, downstream_tokens=5, latency_ms=float(i), tokens_saved_filtering=5)
    
    # Should be bounded
    assert len(m.latencies) <= 10_000
    print("✓ Latencies bounded")


def test_tokens_saved_filtering():
    """Test tokens saved from filtering is tracked correctly."""
    m = Metrics()
    
    # No filtering savings
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=100.0, tokens_saved_filtering=0)
    assert m.tokens_saved == 0
    
    # Some filtering savings
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=100.0, tokens_saved_filtering=30)
    assert m.tokens_saved == 30
    
    # More filtering savings
    m.record_request(upstream_tokens=200, downstream_tokens=100, latency_ms=100.0, tokens_saved_filtering=50)
    assert m.tokens_saved == 80  # 30 + 50
    
    print("✓ Tokens saved filtering tracked correctly")
