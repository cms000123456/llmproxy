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
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=200.0, cached=False)
    
    assert m.requests_total == 1
    assert m.cache_misses == 1
    assert m.cache_hits == 0
    assert m.tokens_upstream == 100
    assert m.tokens_downstream == 50
    assert m.tokens_saved == 50
    assert m.latencies == [200.0]
    print("✓ Record request works")


def test_record_cached_request():
    """Test recording a cached request."""
    m = Metrics()
    m.record_request(upstream_tokens=100, downstream_tokens=100, latency_ms=50.0, cached=True)
    
    assert m.requests_total == 1
    assert m.cache_hits == 1
    assert m.cache_misses == 0
    print("✓ Record cached request works")


def test_record_multiple_requests():
    """Test recording multiple requests."""
    m = Metrics()
    
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=100.0)
    m.record_request(upstream_tokens=200, downstream_tokens=150, latency_ms=200.0, cached=True)
    m.record_request(upstream_tokens=100, downstream_tokens=100, latency_ms=150.0)
    
    assert m.requests_total == 3
    assert m.cache_hits == 1
    assert m.cache_misses == 2
    assert m.tokens_upstream == 400
    assert m.tokens_downstream == 300
    assert m.tokens_saved == 100
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
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=100.0, cached=True)
    m.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=200.0, cached=False)
    
    summary = m.summary()
    assert summary["requests_total"] == 2
    assert summary["cache_hits"] == 1
    assert summary["cache_misses"] == 1
    assert summary["cache_hit_rate"] == 0.5
    assert summary["avg_latency_ms"] == 150.0
    assert summary["tokens_upstream"] == 200
    assert summary["tokens_downstream"] == 100
    assert summary["tokens_saved"] == 100
    assert summary["errors_total"] == 0
    print("✓ Summary works")


def test_latency_bounding():
    """Test that latencies list is bounded to prevent memory growth."""
    m = Metrics()
    
    # Add more than 10,000 latencies
    for i in range(10_500):
        m.record_request(upstream_tokens=10, downstream_tokens=10, latency_ms=float(i))
    
    # Should be trimmed to ~5,000 (implementation keeps 5,000 after exceeding 10,000)
    # The actual behavior: when len > 10,000, keep last 5,000
    # So after adding 10,500: keep indices 5,500 to 10,499 = 5,000 items
    assert len(m.latencies) <= 5_500  # Give some slack
    assert len(m.latencies) >= 5_000
    # Should keep the most recent (last entries)
    assert m.latencies[-1] == 10_499.0  # Last element
    print("✓ Latency bounding works")


def test_thread_safety():
    """Test thread-safe operations."""
    m = Metrics()
    errors = []
    
    def record_requests():
        try:
            for i in range(100):
                m.record_request(upstream_tokens=10, downstream_tokens=5, latency_ms=float(i))
        except Exception as e:
            errors.append(e)
    
    def record_errors():
        try:
            for _ in range(50):
                m.record_error()
        except Exception as e:
            errors.append(e)
    
    threads = []
    for _ in range(5):
        threads.append(threading.Thread(target=record_requests))
        threads.append(threading.Thread(target=record_errors))
    
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    
    assert not errors, f"Thread safety errors: {errors}"
    assert m.requests_total == 500  # 5 threads * 100 requests
    assert m.errors_total == 250    # 5 threads * 50 errors
    print("✓ Thread safety works")


def test_tokens_saved_calculation():
    """Test tokens saved is calculated correctly (never negative)."""
    m = Metrics()
    
    # Downstream > upstream (should result in 0 saved, not negative)
    m.record_request(upstream_tokens=50, downstream_tokens=100, latency_ms=100.0)
    assert m.tokens_saved == 0
    
    # Upstream > downstream
    m.record_request(upstream_tokens=200, downstream_tokens=50, latency_ms=100.0)
    assert m.tokens_saved == 150  # 150 + 0 (from previous)
    print("✓ Tokens saved calculation works")


if __name__ == "__main__":
    test_initial_state()
    test_record_request()
    test_record_cached_request()
    test_record_multiple_requests()
    test_record_error()
    test_summary()
    test_latency_bounding()
    test_thread_safety()
    test_tokens_saved_calculation()
    print("\n✅ All metrics tests passed!")
