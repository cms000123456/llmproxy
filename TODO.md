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

- [x] ~~**TODO-NEW:**~~ Local-only mode with Ollama (Offline)
  - **File:** `llmproxy/local_provider.py` (new)
  - **Features:** 
    - Run entirely offline without upstream API
    - OpenAI-compatible endpoints using Ollama
    - Model aliases (local-coder, local-deepseek, etc.)
    - Support for Qwen2.5-Coder, DeepSeek, CodeLlama
  - **Config:** `local_mode: bool`, `local_model: str`
  - **Scripts:** `scripts/setup-local-models.sh` for easy setup
  - **Docs:** `LOCAL_MODELS.md` with hardware requirements and recommendations
  - **Time Estimate:** 1 day
  - **Note:** Completed 2026-04-04

- [x] ~~**TODO-NEW:**~~ Automatic GPU-based model download
  - **File:** `llmproxy/gpu_detector.py`, `llmproxy/model_manager.py`
  - **Features:**
    - Auto-detect GPU (NVIDIA/AMD/Apple)
    - Calculate VRAM requirements for models
    - Auto-download recommended models on startup
    - API endpoints for GPU info and model management
  - **Config:** `auto_download_models: bool`, `auto_download_best_only: bool`
  - **Endpoints:** `/system/gpu`, `/models/download`, `/models/auto-download`
  - **Time Estimate:** 4 hours
  - **Note:** Completed 2026-04-05

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

- [x] ~~**TODO-011:**~~ Add Prometheus metrics endpoint
  - **File:** `llmproxy/metrics/prometheus.py` (new)
  - **Endpoint:** `/metrics/prometheus`
  - **Time Estimate:** 4 hours
  - **Note:** Completed 2025-01-15

---

## 🟢 LOW PRIORITY (Long-term / Nice to Have)

### Features
- [x] ~~**TODO-012:**~~ Implement prompt templates with variables
  - **File:** `llmproxy/templates.py` (new)
  - **Config:** Add `prompt_templates` dictionary
  - **Features:**
    - Jinja2-style template syntax: `{{ variable }}`, `{{ variable | default('value') }}`
    - 6 built-in templates: code_review, explain_code, refactor, summarize_text, translate, debug_error
    - Custom templates via config file or env vars
    - API endpoints: `/templates`, `/templates/render`, `/templates/validate`
  - **Tests:** `tests/test_templates.py` - 41 tests
  - **Time Estimate:** 1 day
  - **Note:** Completed 2025-01-15

- [x] ~~**TODO-013:**~~ Add A/B testing for model routing
  - **File:** `llmproxy/server.py` - `_get_ab_test_variant()`, variant selection
  - **Config:** `ab_test_enabled`, `experimental_upstream_base_url`, `ab_test_traffic_split`
  - **Features:** Sticky sessions, traffic splitting, per-variant metrics
  - **Tests:** `tests/test_ab_testing.py` (9 tests), `tests/test_ab_integration.py` (6 tests)
  - **Endpoint:** `/ab-test/status` for monitoring
  - **Time Estimate:** 1 day
  - **Note:** Completed 2025-04-03 - fully integrated with request routing

- [x] ~~**TODO-014:**~~ Add distributed tracing (OpenTelemetry)
  - **File:** `llmproxy/tracing.py` (new)
  - **Features:** OpenTelemetry SDK, OTLP exporter, Jaeger integration
  - **Config:** `tracing_enabled`, `otel_exporter_endpoint`
  - **Tests:** `tests/test_tracing.py` - 9 tests
  - **Time Estimate:** 1-2 days
  - **Note:** Completed 2025-04-03

### Developer Experience
- [x] ~~**TODO-015:**~~ Add development stack documentation
  - **File:** Update `HOWTO.md`
  - **Features:** Document docker-compose.dev.yml with Redis, Jaeger, Prometheus, Grafana
  - **Time Estimate:** 2 hours
  - **Note:** Completed 2025-01-15

- [x] ~~**TODO-016:**~~ Create docker-compose for local development
  - **File:** `docker-compose.dev.yml`
  - **Features:** 
    - LLM Proxy with Redis cache backend
    - Ollama for local LLM tasks
    - Redis for caching
    - Jaeger for distributed tracing (UI on port 16686)
    - Prometheus for metrics (port 9090)
    - Grafana for dashboards (port 3000, admin/admin)
  - **Time Estimate:** 2 hours
  - **Note:** Completed 2025-01-15

### Code Quality
- [x] ~~**TODO-017:**~~ Add linting with Ruff
  - **File:** `pyproject.toml` - Ruff configuration
  - **Features:** Auto-formatting, import sorting, code style enforcement
  - **Time Estimate:** 2 hours
  - **Note:** Completed 2025-04-03

- [x] ~~**TODO-018:**~~ Add type checking with mypy
  - **File:** `pyproject.toml` - mypy configuration
  - **Features:** Static type checking, gradual migration strategy
  - **Time Estimate:** 2-3 hours
  - **Status:** Completed - ~40 errors remaining (non-critical, gradual fix)
  - **Note:** Added `scripts/typecheck.sh` for running mypy
  - **Completed:** 2025-04-03

---

## ✅ Recently Completed

| TODO | Description | Date Completed |
|------|-------------|----------------|
| TODO-013 | A/B testing for model routing (sticky sessions, traffic split, metrics) | 2025-04-03 |
| TODO-018 | Type checking with mypy (setup complete, ~40 non-critical errors remaining) | 2025-04-03 |
| TODO-014 | Distributed tracing with OpenTelemetry (Jaeger integration) | 2025-04-03 |
| TODO-017 | Linting with Ruff (1000+ issues fixed, full codebase reformatted) | 2025-04-03 |
| TODO-016 | Docker-compose dev stack (Redis, Jaeger, Prometheus, Grafana) | 2025-01-15 |
| TODO-015 | Development stack documentation in HOWTO.md | 2025-01-15 |
| TODO-012 | Prompt templates with variables | 2025-01-15 |
| TODO-011 | Prometheus metrics endpoint | 2025-01-15 |
| TODO-010 | Structured logging with structlog | 2025-01-15 |
| TODO-009 | Per-API-key cost tracking | 2025-01-15 |
| TODO-005 | Streaming response support | 2025-01-14 |
| TODO-004 | Graceful shutdown handling | 2025-01-14 |
