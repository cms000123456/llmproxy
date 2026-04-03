# LLM Proxy Monitoring Stack

This directory contains the Prometheus + Grafana monitoring stack for LLM Proxy.

## Components

- **Prometheus** - Metrics collection, storage, and alerting
- **Grafana** - Visualization dashboards
- **Alerting Rules** - Pre-configured alerts for common issues

## Quick Start

### 1. Start the main LLM Proxy services first:

```bash
docker-compose up -d
```

### 2. Start the monitoring stack:

```bash
# Create the Docker network if it doesn't exist
docker network create llmproxy-net 2>/dev/null || true

# Start monitoring
docker-compose -f docker-compose.monitoring.yml up -d
```

### 3. Access the services:

| Service | URL | Credentials |
|---------|-----|-------------|
| Prometheus | http://localhost:9091 | - |
| Grafana | http://localhost:3002 | admin/admin |
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

### Overview Row
- **Total Requests** - Request counter
- **Cache Hit Rate** - Percentage of cached responses
- **Cache Hits/Misses** - Cache statistics
- **Total Errors** - Error counter

### Performance Row
- **Request Rate** - Requests per second over time
- **Average Latency** - Response latency trends

### Token Efficiency Row
- **Token Usage** - Upstream vs downstream tokens
- **Tokens Saved** - Efficiency gains from filtering/compression

### Cost Tracking Row
- **Estimated Cost ($)** - Total estimated spend (input: $0.01/1K, output: $0.03/1K tokens)
- **Cost Savings ($)** - Money saved through filtering/compression
- **Savings Percentage** - Percentage of tokens saved
- **Cost Over Time** - Input, output, and saved costs over time

**Note:** Cost calculations assume $0.01 per 1K input tokens and $0.03 per 1K output tokens. Adjust these estimates based on your actual upstream API pricing.

## Alerting

Prometheus includes pre-configured alerting rules in `alerts.yml`.

### Alert Severities

| Severity | Description | Response Time |
|----------|-------------|---------------|
| **Critical** | Service down or severely degraded | Immediate |
| **Warning** | Degraded performance or unusual patterns | Within 1 hour |
| **Info** | Notable events, not necessarily bad | Next business day |

### Alert List

#### Critical Alerts

| Alert | Condition | Duration |
|-------|-----------|----------|
| `LLMProxyDown` | Service not responding | 1 minute |
| `HighErrorRate` | Error rate > 5% | 2 minutes |
| `HighLatency` | Average latency > 10s | 3 minutes |

#### Warning Alerts

| Alert | Condition | Duration |
|-------|-----------|----------|
| `ModerateErrorRate` | Error rate > 1% | 5 minutes |
| `ModerateLatency` | Average latency > 5s | 5 minutes |
| `LowCacheHitRate` | Cache hit rate < 10% | 10 minutes |
| `NoCacheHits` | Zero cache hits despite traffic | 15 minutes |

#### Info Alerts

| Alert | Condition |
|-------|-----------|
| `TrafficSpike` | Request rate 3x above normal |
| `HighTokenSavings` | >80% tokens saved (efficiency milestone) |
| `EstimatedCostThreshold` | Estimated cost > $100 in session |

### Viewing Alerts

1. **Prometheus UI**: http://localhost:9091/alerts
2. **Alert Status**: Shows firing, pending, and inactive alerts
3. **Expression Browser**: Test alert queries at http://localhost:9091/graph

### Configuring Alert Notifications (Optional)

To send alerts to Slack, PagerDuty, email, etc.:

1. Add Alertmanager to `docker-compose.monitoring.yml`:

```yaml
  alertmanager:
    image: prom/alertmanager:v0.26.0
    container_name: llmproxy-alertmanager
    ports:
      - "9093:9093"
    volumes:
      - ./monitoring/alertmanager.yml:/etc/alertmanager/alertmanager.yml:ro
    networks:
      - llmproxy-net
```

2. Create `alertmanager.yml` with your notification config:

```yaml
global:
  slack_api_url: 'YOUR_SLACK_WEBHOOK_URL'

route:
  receiver: 'default'

receivers:
  - name: 'default'
    slack_configs:
      - channel: '#alerts'
        title: '{{ .GroupLabels.alertname }}'
        text: '{{ .Annotations.summary }}'
```

3. Uncomment the `alerting` section in `prometheus.yml`

## Stopping

```bash
docker-compose -f docker-compose.monitoring.yml down
```

To also remove data volumes:
```bash
docker-compose -f docker-compose.monitoring.yml down -v
```

## Files

| File | Purpose |
|------|---------|
| `prometheus.yml` | Prometheus configuration and scrape targets |
| `alerts.yml` | Alerting rules definitions |
| `grafana/provisioning/` | Grafana auto-provisioning configs |
| `grafana/dashboards/` | Pre-built dashboard JSON |

## Distributed Tracing with Jaeger

The monitoring stack includes Jaeger for distributed tracing of requests through the LLM Proxy.

### What is Distributed Tracing?

Distributed tracing tracks a request as it flows through different components of a system, showing:
- Timing of each operation
- Dependencies between services
- Performance bottlenecks
- Error propagation

### Starting Jaeger

Jaeger is included in the monitoring stack:

```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

### Accessing Jaeger UI

Open http://localhost:16686 in your browser.

### Enabling Tracing in LLM Proxy

Set these environment variables:

```bash
# Enable tracing
export LLM_PROXY_TRACING_ENABLED=true

# Set Jaeger endpoint (use host IP if running proxy outside Docker)
export LLM_PROXY_OTEL_EXPORTER_ENDPOINT=http://localhost:4318/v1/traces

# Or if proxy is in Docker:
export LLM_PROXY_OTEL_EXPORTER_ENDPOINT=http://jaeger:4318/v1/traces
```

### Traced Operations

The LLM Proxy creates spans for these operations:

| Span Name | Description | Attributes |
|-----------|-------------|------------|
| `filter_messages` | Message deduplication and cleanup | `message_count`, `filtered_count` |
| `compress_messages` | Conversation compression | `strategy`, `original_tokens`, `compressed_tokens` |
| `ab_test_selection` | A/B test variant selection | `variant`, `traffic_split` |
| `cache_lookup` | Cache check operation | `cache_hit`, `cache_key` |
| `upstream_request` | Upstream API call | `model`, `tokens_upstream`, `latency_ms` |

### Using Jaeger UI

1. **Search Traces**: Filter by service, operation, tags, or time range
2. **Trace View**: See the full request flow with timing
3. **Compare Traces**: Find performance differences between requests
4. **Dependencies**: Visualize service dependencies

### Example Trace

A typical request trace looks like:

```
┌─ POST /v1/chat/completions ──────────────────────┐
├─ filter_messages ..................... 2ms       │
├─ compress_messages ................... 15ms      │
│  └─ ollama_summarize ................. 12ms      │
├─ cache_lookup ........................ 1ms       │
├─ upstream_request .................... 1250ms    │
│  └─ POST https://api.upstream.com/... 1248ms     │
└─ Total ............................... 1268ms    │
```

### Troubleshooting Tracing

**No traces appearing:**
```bash
# Check Jaeger is running
curl http://localhost:16686/api/services

# Check proxy can reach Jaeger
telnet localhost 4318

# Verify tracing is enabled
curl http://localhost:8080/health  # Check logs for tracing status
```

**Traces incomplete:**
- Ensure `LLM_PROXY_TRACING_ENABLED=true` is set
- Check OTLP endpoint URL is correct
- Verify network connectivity between proxy and Jaeger

