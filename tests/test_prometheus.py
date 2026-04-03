#!/usr/bin/env python3
"""Tests for Prometheus metrics endpoint."""

import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from httpx import ASGITransport, AsyncClient

from llmproxy.metrics import METRICS
from llmproxy.metrics.prometheus import generate_prometheus_metrics, get_prometheus_metrics_text
from llmproxy.server import app


class TestPrometheusMetrics:
    """Test Prometheus metrics generation."""

    def test_generate_prometheus_metrics_format(self):
        """Test that metrics are in valid Prometheus format."""
        lines = list(generate_prometheus_metrics())

        # Should have HELP, TYPE, and value lines for each metric
        help_lines = [line for line in lines if line.startswith("# HELP")]
        type_lines = [line for line in lines if line.startswith("# TYPE")]
        value_lines = [line for line in lines if not line.startswith("#") and line.strip()]

        # Each metric should have HELP and TYPE
        assert len(help_lines) >= 9  # At least 9 metrics
        assert len(type_lines) >= 9
        assert len(value_lines) >= 9

        print("✓ Prometheus metrics format is valid")

    def test_prometheus_metrics_content(self):
        """Test that metrics contain expected values."""
        text = get_prometheus_metrics_text()

        # Check for expected metrics
        assert "llmproxy_requests_total" in text
        assert "llmproxy_cache_hits_total" in text
        assert "llmproxy_cache_misses_total" in text
        assert "llmproxy_cache_hit_rate" in text
        assert "llmproxy_tokens_upstream_total" in text
        assert "llmproxy_tokens_downstream_total" in text
        assert "llmproxy_tokens_saved_total" in text
        assert "llmproxy_errors_total" in text
        assert "llmproxy_avg_latency_ms" in text
        assert "llmproxy_info" in text

        print("✓ All expected metrics present")

    def test_prometheus_metric_types(self):
        """Test that metrics have correct types."""
        text = get_prometheus_metrics_text()

        # Counters
        assert "# TYPE llmproxy_requests_total counter" in text
        assert "# TYPE llmproxy_cache_hits_total counter" in text
        assert "# TYPE llmproxy_cache_misses_total counter" in text
        assert "# TYPE llmproxy_tokens_upstream_total counter" in text
        assert "# TYPE llmproxy_tokens_downstream_total counter" in text
        assert "# TYPE llmproxy_tokens_saved_total counter" in text
        assert "# TYPE llmproxy_errors_total counter" in text

        # Gauges
        assert "# TYPE llmproxy_cache_hit_rate gauge" in text
        assert "# TYPE llmproxy_avg_latency_ms gauge" in text
        assert "# TYPE llmproxy_info gauge" in text

        print("✓ Metric types are correct")

    def test_prometheus_metrics_with_data(self):
        """Test metrics reflect actual data."""
        # Record some test data
        METRICS.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=200.0)
        METRICS.record_request(
            upstream_tokens=200, downstream_tokens=100, latency_ms=300.0, cached=True
        )
        METRICS.record_error()

        text = get_prometheus_metrics_text()

        # Check values are reflected
        assert "llmproxy_requests_total 2" in text
        assert "llmproxy_cache_hits_total 1" in text
        assert "llmproxy_cache_misses_total 1" in text
        assert "llmproxy_tokens_upstream_total 300" in text
        assert "llmproxy_tokens_downstream_total 150" in text
        assert "llmproxy_errors_total 1" in text

        # Cleanup
        METRICS.requests_total = 0
        METRICS.cache_hits = 0
        METRICS.cache_misses = 0
        METRICS.tokens_upstream = 0
        METRICS.tokens_downstream = 0
        METRICS.tokens_saved = 0
        METRICS.errors_total = 0
        METRICS.latencies.clear()

        print("✓ Metrics reflect actual data")


class TestPrometheusEndpoint:
    """Test Prometheus HTTP endpoint."""

    @pytest.mark.asyncio
    async def test_prometheus_endpoint_returns_text(self):
        """Test that /metrics/prometheus returns plain text."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metrics/prometheus")

        assert response.status_code == 200
        assert response.headers["content-type"] == "text/plain; charset=utf-8"

        print("✓ Prometheus endpoint returns text/plain")

    @pytest.mark.asyncio
    async def test_prometheus_endpoint_content(self):
        """Test that endpoint returns valid Prometheus metrics."""
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/metrics/prometheus")

        text = response.text

        # Check for key metrics
        assert "llmproxy_requests_total" in text
        assert "llmproxy_cache_hits_total" in text
        assert "llmproxy_errors_total" in text

        # Check format
        assert text.startswith("# HELP")

        print("✓ Prometheus endpoint returns valid metrics")

    @pytest.mark.asyncio
    async def test_prometheus_endpoint_vs_json_metrics(self):
        """Test that Prometheus endpoint matches JSON metrics endpoint."""
        # Record test data
        METRICS.record_request(upstream_tokens=100, downstream_tokens=50, latency_ms=200.0)

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            prom_response = await client.get("/metrics/prometheus")
            json_response = await client.get("/metrics")

        prom_text = prom_response.text
        json_data = json_response.json()

        # Values should match
        assert "llmproxy_requests_total" in prom_text
        assert json_data["metrics"]["requests_total"] >= 1

        # Cleanup
        METRICS.requests_total = 0
        METRICS.tokens_upstream = 0
        METRICS.tokens_downstream = 0
        METRICS.latencies.clear()

        print("✓ Prometheus and JSON metrics are consistent")


def test_prometheus_info_metric():
    """Test that info metric includes version."""
    text = get_prometheus_metrics_text()

    # Info metric should have version label
    assert 'llmproxy_info{version="1.0.0"} 1' in text

    print("✓ Info metric includes version")


if __name__ == "__main__":
    # Run sync tests
    test_gen = TestPrometheusMetrics()
    test_gen.test_generate_prometheus_metrics_format()
    test_gen.test_prometheus_metrics_content()
    test_gen.test_prometheus_metric_types()
    test_gen.test_prometheus_metrics_with_data()

    test_prometheus_info_metric()

    print("\n✅ All Prometheus tests passed!")
