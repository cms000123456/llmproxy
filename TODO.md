# LLM Proxy TODO List

**Last Updated:** 2025-01-15  
**Status:** Active Development

---

## 🔴 HIGH PRIORITY (Do First)

### Security
- [x] ~~**TODO-001:**~~ Add API key authentication middleware
  - **File:** `llmproxy/auth.py` (new)
  - **Config:** Add `api_keys: list[str]` to Settings
  - **Tests:** Add auth tests to `tests/test_server.py`
  - **Time Estimate:** 1 day

- [x] ~~**TODO-002:**~~ Add request/response sanitization for PII
  - **File:** `llmproxy/middleware/sanitize.py` (new)
  - **Features:** Credit card, API key, email redaction
  - **Time Estimate:** 4 hours
  - **Note:** Completed 2025-01-15

### Reliability
- [x] ~~**TODO-003:**~~ Implement request retry with exponential backoff
  - **File:** `llmproxy/server.py` - Added `_upstream_request_with_retry()` function
  - **Config:** Added `max_retries: int = 3`, `retry_backoff: float = 2.0`, `retry_max_wait: float = 60.0`
  - **Features:** 
    - Retries on: timeouts, connection errors, 5xx errors, 429 rate limits
    - Exponential backoff with ±25% jitter to avoid thundering herd
    - Respects Retry-After header for 429 responses
    - Returns last response for 5xx after retries, raises for connection/timeout errors
  - **Tests:** `tests/test_retry.py` - 13 comprehensive tests
  - **Time Estimate:** 4 hours
  - **Note:** Completed 2025-01-15

- [x] ~~**TODO-004:**~~ Add graceful shutdown handling
  - **File:** Modify `llmproxy/server.py` lifespan
  - **Features:** Close HTTP client, flush cache on SIGTERM
  - **Time Estimate:** 2 hours

---

## 🟡 MEDIUM PRIORITY (Short-term)

### Performance
- [x] ~~**TODO-005:**~~ Add streaming response support for `/chat/completions`
  - **File:** Modify `llmproxy/server.py`
  - **Features:** SSE streaming, chunked responses
  - **Time Estimate:** 2-3 days
  - **Depends on:** TODO-004 (graceful shutdown for stream cleanup)

- [x] ~~**TODO-006:**~~ Convert file I/O to async (aiofiles)
  - **File:** `llmproxy/tools.py`
  - **Functions:** `read_file()`, `write_file()`, `grep()`
  - **Time Estimate:** 1 day

### Storage & Cache
- [x] ~~**TODO-007:**~~ Create abstract storage backend interface
  - **File:** `llmproxy/storage/base.py` (new)
  - **Implement:** MemoryBackend (current), RedisBackend
  - **Time Estimate:** 2 days
  - **Note:** Keep backward compatibility

- [x] ~~**TODO-008:**~~ Add Redis cache backend option
  - **File:** `llmproxy/storage/redis.py` (new)
  - **Config:** Add `cache_backend: str = "memory"`
  - **Time Estimate:** 1 day
  - **Depends on:** TODO-007

### Cost Management
- [x] ~~**TODO-009:**~~ Add per-API-key cost tracking
  - **File:** `llmproxy/cost_tracker.py` (new)
  - **Features:** Track spending, set budgets, alerts
  - **Time Estimate:** 1 day
  - **Depends on:** TODO-001 (authentication)

### Observability
- [x] ~~**TODO-010:**~~ Add structured logging with structlog
  - **File:** `llmproxy/logging_config.py` (new)
  - **Config:** Add `log_format: str = "console"` (console or json)
  - **Time Estimate:** 4 hours
  - **Note:** Completed 2025-01-15
  - **Note:** Completed 2025-01-15

- [x] ~~**TODO-011:**~~ Add Prometheus metrics endpoint
  - **File:** `llmproxy/metrics/prometheus.py` (new)
  - **Endpoint:** `/metrics/prometheus`
  - **Time Estimate:** 4 hours
  - **Note:** Completed 2025-01-15

---

## 🟢 LOW PRIORITY (Long-term / Nice to Have)

### Features
- [ ] **TODO-012:** Implement prompt templates with variables
  - **File:** `llmproxy/templates.py` (new)
  - **Config:** Add `prompt_templates` dictionary
  - **Time Estimate:** 1 day

- [ ] **TODO-013:** Add A/B testing for model routing
  - **File:** Modify `llmproxy/server.py`
  - **Config:** Add `experimental_upstream_url`, `traffic_split`
  - **Time Estimate:** 1 day

- [ ] **TODO-014:** Add distributed tracing (OpenTelemetry)
  - **File:** `llmproxy/tracing.py` (new)
  - **Features:** Jaeger/Zipkin integration
  - **Time Estimate:** 1-2 days

### Developer Experience
- [ ] **TODO-015:** Add request/response examples to documentation
  - **File:** Update `HOWTO.md`
  - **Time Estimate:** 2 hours

- [ ] **TODO-016:** Create docker-compose for local development
  - **File:** `docker-compose.dev.yml`
  - **Features:** Redis, Jaeger, Prometheus stack
  - **Time Estimate:** 2 hours

---

## ✅ Recently Completed

| TODO | Description | Date Completed |
|------|-------------|----------------|
| TODO-011 | Prometheus metrics endpoint | 2025-01-15 |
| TODO-010 | Structured logging with structlog | 2025-01-15 |
| TODO-009 | Per-API-key cost tracking | 2025-01-15 |
| TODO-005 | Streaming response support | 2025-01-14 |
| TODO-004 | Graceful shutdown handling | 2025-01-14 |
