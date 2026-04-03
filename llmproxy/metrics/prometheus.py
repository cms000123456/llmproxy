"""Prometheus metrics exporter for LLM Proxy.

Exports metrics in Prometheus text format for scraping by Prometheus server.
See: https://prometheus.io/docs/instrumenting/exposition_formats/
"""

from typing import Iterator
from ..metrics import METRICS


def generate_prometheus_metrics() -> Iterator[str]:
    """Generate Prometheus-formatted metrics.
    
    Yields lines of Prometheus text format output.
    
    Example output:
        # HELP llmproxy_requests_total Total number of requests processed
        # TYPE llmproxy_requests_total counter
        llmproxy_requests_total 1234
        ...
    """
    # Get current metrics snapshot
    summary = METRICS.summary()
    
    # llmproxy_requests_total - Counter
    yield "# HELP llmproxy_requests_total Total number of requests processed"
    yield "# TYPE llmproxy_requests_total counter"
    yield f"llmproxy_requests_total {summary['requests_total']}"
    yield ""
    
    # llmproxy_cache_hits_total - Counter
    yield "# HELP llmproxy_cache_hits_total Total number of cache hits"
    yield "# TYPE llmproxy_cache_hits_total counter"
    yield f"llmproxy_cache_hits_total {summary['cache_hits']}"
    yield ""
    
    # llmproxy_cache_misses_total - Counter
    yield "# HELP llmproxy_cache_misses_total Total number of cache misses"
    yield "# TYPE llmproxy_cache_misses_total counter"
    yield f"llmproxy_cache_misses_total {summary['cache_misses']}"
    yield ""
    
    # llmproxy_cache_hit_rate - Gauge (0-1)
    yield "# HELP llmproxy_cache_hit_rate Cache hit rate (0-1)"
    yield "# TYPE llmproxy_cache_hit_rate gauge"
    yield f"llmproxy_cache_hit_rate {summary['cache_hit_rate']}"
    yield ""
    
    # llmproxy_tokens_upstream_total - Counter
    yield "# HELP llmproxy_tokens_upstream_total Total tokens sent to upstream API"
    yield "# TYPE llmproxy_tokens_upstream_total counter"
    yield f"llmproxy_tokens_upstream_total {summary['tokens_upstream']}"
    yield ""
    
    # llmproxy_tokens_downstream_total - Counter
    yield "# HELP llmproxy_tokens_downstream_total Total tokens received from upstream API"
    yield "# TYPE llmproxy_tokens_downstream_total counter"
    yield f"llmproxy_tokens_downstream_total {summary['tokens_downstream']}"
    yield ""
    
    # llmproxy_tokens_saved_total - Counter
    yield "# HELP llmproxy_tokens_saved_total Total tokens saved by filtering/compression"
    yield "# TYPE llmproxy_tokens_saved_total counter"
    yield f"llmproxy_tokens_saved_total {summary['tokens_saved']}"
    yield ""
    
    # llmproxy_errors_total - Counter
    yield "# HELP llmproxy_errors_total Total number of errors"
    yield "# TYPE llmproxy_errors_total counter"
    yield f"llmproxy_errors_total {summary['errors_total']}"
    yield ""
    
    # llmproxy_avg_latency_ms - Gauge
    yield "# HELP llmproxy_avg_latency_ms Average request latency in milliseconds"
    yield "# TYPE llmproxy_avg_latency_ms gauge"
    yield f"llmproxy_avg_latency_ms {summary['avg_latency_ms']}"
    yield ""
    
    # llmproxy_info - Info metric (always 1)
    yield "# HELP llmproxy_info LLM Proxy version information"
    yield "# TYPE llmproxy_info gauge"
    yield 'llmproxy_info{version="1.0.0"} 1'
    yield ""


def get_prometheus_metrics_text() -> str:
    """Get all Prometheus metrics as a single text string.
    
    Returns:
        Prometheus-formatted metrics text
    """
    return "\n".join(generate_prometheus_metrics())
