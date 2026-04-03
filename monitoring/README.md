# LLM Proxy Monitoring Stack

This directory contains the Prometheus + Grafana monitoring stack for LLM Proxy.

## Components

- **Prometheus** - Metrics collection and storage
- **Grafana** - Visualization dashboards

## Quick Start

### 1. Start the main LLM Proxy services first:

```bash
docker-compose up -d
```

### 2. Start the monitoring stack:

```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

### 3. Access the services:

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://localhost:9090 | - |
| Grafana | http://localhost:3001 | admin/admin |
| LLM Proxy Metrics | http://localhost:8080/metrics/prometheus | - |

## Available Metrics

| Metric | Description |
|--------|-------------|
| `llmproxy_requests_total` | Total number of requests processed |
| `llmproxy_cache_hits_total` | Total cache hits |
| `llmproxy_cache_misses_total` | Total cache misses |
| `llmproxy_cache_hit_rate` | Cache hit rate (0-1) |
| `llmproxy_tokens_upstream_total` | Tokens sent to upstream API |
| `llmproxy_tokens_downstream_total` | Tokens received from upstream |
| `llmproxy_tokens_saved_total` | Tokens saved by filtering/compression |
| `llmproxy_errors_total` | Total errors |
| `llmproxy_avg_latency_ms` | Average request latency |

## Dashboard Panels

The Grafana dashboard includes:
- **Total Requests** - Request counter
- **Cache Hit Rate** - Percentage of cached responses
- **Cache Hits/Misses** - Cache statistics
- **Total Errors** - Error counter
- **Request Rate** - Requests per second over time
- **Average Latency** - Response latency trends
- **Token Usage** - Upstream vs downstream tokens
- **Tokens Saved** - Efficiency gains from filtering/compression

## Stopping

```bash
docker-compose -f docker-compose.monitoring.yml down
```

To also remove data volumes:
```bash
docker-compose -f docker-compose.monitoring.yml down -v
```
