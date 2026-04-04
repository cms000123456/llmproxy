# Load Testing Guide

This document covers load testing the LLM Proxy using the `load_test.py` tool.

## Quick Start

```bash
# Basic load test (30 seconds, 10 concurrent connections)
python load_test.py http://localhost:8080

# Extended test with higher concurrency
python load_test.py http://localhost:8080 --duration 60 --concurrent 50

# Test cache effectiveness
python load_test.py http://localhost:8080 --test-cache

# Stress test with ramp-up
python load_test.py http://localhost:8080 --stress-test

# JSON output for CI/CD
python load_test.py http://localhost:8080 --duration 60 --json
```

## Load Test Types

### 1. Basic Load Test

Tests the proxy under steady load:

```bash
python load_test.py http://localhost:8080 \
  --duration 60 \
  --concurrent 20 \
  --test-type default
```

**Parameters:**
- `--duration`: Test duration in seconds (default: 30)
- `--concurrent`: Number of concurrent connections (default: 10)
- `--test-type`: Payload type (default, long_context, streaming)

**Output:**
```
============================================================
LOAD TEST RESULTS
============================================================
Duration:          60.23s
Total Requests:    5847
Successful:        5801 (99.2%)
Failed:            46
Throughput:        97.08 req/s

LATENCY (ms)
  P50:             45.23
  P95:             89.45
  P99:             125.67

CACHE PERFORMANCE
  Hits:            2345
  Misses:          3456
  Hit Rate:        40.4%
============================================================
```

### 2. Cache Effectiveness Test

Tests how well the cache is working:

```bash
python load_test.py http://localhost:8080 --test-cache
```

This sends 100 identical requests and measures:
- Cache hit rate (should be high for repeated requests)
- Latency improvement for cached responses

### 3. Stress Test (Ramp-up)

Gradually increases load to find breaking points:

```bash
python load_test.py http://localhost:8080 --stress-test
```

Tests these concurrency levels:
1. 10 concurrent connections (15 seconds)
2. 25 concurrent connections (15 seconds)
3. 50 concurrent connections (15 seconds)
4. 100 concurrent connections (15 seconds)

## Test Payload Types

| Type | Description | Use Case |
|------|-------------|----------|
| `default` | Simple chat completion | Basic throughput testing |
| `long_context` | 500-token context | Memory/CPU stress testing |
| `streaming` | Streaming response | SSE connection testing |

## Interpreting Results

### Key Metrics

| Metric | Good | Warning | Critical |
|--------|------|---------|----------|
| **Success Rate** | >99% | 95-99% | <95% |
| **Throughput** | >50 req/s | 10-50 req/s | <10 req/s |
| **P95 Latency** | <100ms | 100-500ms | >500ms |
| **Cache Hit Rate** | >30% | 10-30% | <10% |

### Common Issues

**Rate Limiting (HTTP 429):**
The proxy has built-in rate limiting (100 req/min per IP). For load testing:
- Increase rate limits temporarily in config
- Use multiple test clients
- Test from different IPs

**High Latency:**
- Check upstream API latency
- Verify cache is enabled
- Monitor CPU/memory usage

**Low Cache Hit Rate:**
- Increase cache TTL
- Check for cache key differences
- Verify cache backend is working

## CI/CD Integration

### GitHub Actions Example

```yaml
- name: Load Test
  run: |
    python load_test.py http://localhost:8080 \
      --duration 30 \
      --concurrent 20 \
      --json > results.json
    
    # Check success rate
    SUCCESS_RATE=$(jq '.success_rate' results.json)
    if (( $(echo "$SUCCESS_RATE < 95" | bc -l) )); then
      echo "Success rate too low: $SUCCESS_RATE%"
      exit 1
    fi
```

### Expected JSON Output

```json
{
  "duration": 30.45,
  "total_requests": 2847,
  "successful": 2834,
  "failed": 13,
  "success_rate": 99.54,
  "throughput": 93.48,
  "latency_ms": {
    "p50": 42.15,
    "p95": 78.32,
    "p99": 98.45
  },
  "cache": {
    "hits": 1145,
    "misses": 1689,
    "hit_rate": 40.39
  }
}
```

## Performance Tuning Tips

### Before Load Testing

1. **Enable caching:**
   ```bash
   export LLM_PROXY_ENABLE_CACHE=true
   export LLM_PROXY_CACHE_BACKEND=redis
   ```

2. **Adjust rate limits** (for testing only):
   ```python
   # In server.py, temporarily increase:
   RATE_LIMIT_REQUESTS = 1000  # from 100
   ```

3. **Use Redis for caching:**
   ```bash
   docker run -d -p 6379:6379 redis:7-alpine
   export LLM_PROXY_CACHE_BACKEND=redis
   export LLM_PROXY_REDIS_URL=redis://localhost:6379
   ```

### Monitoring During Tests

Watch these metrics in real-time:

```bash
# Terminal 1: Run load test
python load_test.py http://localhost:8080 --duration 120

# Terminal 2: Watch proxy metrics
curl -s http://localhost:8080/metrics | jq '.metrics'

# Terminal 3: Watch Prometheus
curl -s 'http://localhost:9091/api/v1/query?query=rate(llmproxy_requests_total[5m])'
```

## Troubleshooting

### "Rate limit exceeded" errors
This is expected! The proxy protects itself. For testing:
- Reduce `--concurrent` value
- Increase delay between requests (modify script)
- Temporarily disable rate limiting

### Connection errors
- Check proxy is running: `curl http://localhost:8080/health`
- Verify network connectivity
- Check firewall rules

### High failure rate
- Check upstream API availability
- Verify API key is valid
- Review proxy logs: `docker compose logs proxy`

## Benchmark Comparison

Typical results on modest hardware (4 CPU, 8GB RAM):

| Scenario | Throughput | P95 Latency | Success Rate |
|----------|-----------|-------------|--------------|
| Simple requests | 100-200 req/s | 50-100ms | 99%+ |
| With caching | 300-500 req/s | 10-20ms | 99%+ |
| Long context | 20-50 req/s | 200-500ms | 99%+ |
| Streaming | 50-100 req/s | 100-200ms | 99%+ |
