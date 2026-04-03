# LLM Proxy TODO List

**Last Updated:** 2026-04-03  
**Status:** Active Development

---

## 🔴 HIGH PRIORITY (Do First)

### Security
- [ ] **TODO-001:** ~~Add API key authentication middleware~~ - **ON HOLD**
  - Reason: User requested to hold off on API auth for now
  - Will revisit after other security improvements

- [x] **TODO-002:** Add PII sanitization middleware ✅ **COMPLETED**
  - **File:** `llmproxy/middleware/sanitize.py` ✅
  - **Tests:** `tests/test_sanitize.py` (17 tests, all passing) ✅
  - **Integration:** Added to `server.py` middleware stack ✅
  - **Features:** 
    - API key redaction (sk-*, pk-*, Bearer tokens)
    - Credit card redaction
    - Email redaction
    - Phone number redaction
    - SSN redaction
    - Private key redaction
    - Password/secret field redaction
    - AWS/GitHub/Slack token redaction
  - **Standalone functions:** `sanitize_for_logging()`, `sanitize_dict_for_logging()`
  - **Time Estimate:** 4 hours ✅

### Reliability
- [ ] **TODO-003:** Implement request retry with exponential backoff
  - **File:** Modify `llmproxy/server.py` proxy function
  - **Config:** Add `max_retries: int = 3`, `retry_backoff: float = 2.0`
  - **Time Estimate:** 4 hours

- [ ] **TODO-004:** Add graceful shutdown handling
  - **File:** Modify `llmproxy/server.py` lifespan
  - **Features:** Close HTTP client, flush cache on SIGTERM
  - **Time Estimate:** 2 hours

---

## 🟡 MEDIUM PRIORITY (Short-term)

### Performance
- [ ] **TODO-005:** Add streaming response support for `/chat/completions`
  - **File:** Modify `llmproxy/server.py`
  - **Features:** SSE streaming, chunked responses
  - **Time Estimate:** 2-3 days
  - **Depends on:** TODO-004 (graceful shutdown for stream cleanup)

- [ ] **TODO-006:** Convert file I/O to async (aiofiles)
  - **File:** `llmproxy/tools.py`
  - **Functions:** `read_file()`, `write_file()`, `grep()`
  - **Time Estimate:** 1 day

### Storage & Cache
- [ ] **TODO-007:** Create abstract storage backend interface
  - **File:** `llmproxy/storage/base.py` (new)
  - **Implement:** MemoryBackend (current), RedisBackend
  - **Time Estimate:** 2 days
  - **Note:** Keep backward compatibility

- [ ] **TODO-008:** Add Redis cache backend option
  - **File:** `llmproxy/storage/redis.py` (new)
  - **Config:** Add `cache_backend: str = "memory"`
  - **Time Estimate:** 1 day
  - **Depends on:** TODO-007

### Cost Management
- [ ] **TODO-009:** Add per-API-key cost tracking
  - **File:** `llmproxy/cost_tracker.py` (new)
  - **Features:** Track spending, set budgets, alerts
  - **Time Estimate:** 1 day
  - **Depends on:** TODO-001 (authentication - on hold)

### Observability
- [ ] **TODO-010:** Add structured logging with structlog
  - **File:** Replace print/logging with structlog
  - **Config:** Add `log_format: str = "json"`
  - **Time Estimate:** 4 hours
  - **Note:** Can use `sanitize_for_logging()` for PII protection

- [ ] **TODO-011:** Add Prometheus metrics endpoint
  - **File:** `llmproxy/metrics/prometheus.py` (new)
  - **Endpoint:** `/metrics/prometheus`
  - **Time Estimate:** 4 hours

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
- [ ] **TODO-015:** Add pytest fixtures and async test support
  - **File:** `tests/conftest.py` (new)
  - **Features:** client fixture, mock upstream
  - **Time Estimate:** 4 hours

- [ ] **TODO-016:** Add comprehensive health checks
  - **File:** Modify `llmproxy/server.py`
  - **Checks:** Upstream, cache, disk space
  - **Time Estimate:** 2 hours

### DevOps
- [ ] **TODO-017:** Create full Docker Compose stack
  - **File:** `docker-compose.full.yml` (new)
  - **Services:** Redis, Prometheus, Grafana
  - **Time Estimate:** 4 hours

---

## ✅ COMPLETED

- [x] Create comprehensive test suite (95+ tests)
- [x] Add security middleware (rate limiting, body size, headers)
- [x] Fix path traversal vulnerability
- [x] Verify secrets not in git
- [x] **NEW:** Add PII sanitization middleware (TODO-002)
  - 17 test cases covering all PII patterns
  - Integrated into request/response pipeline
  - Standalone functions for logging

---

## 📊 Progress Tracking

```
HIGH:     1/4  complete  ██░░░░░░░░  25%
MEDIUM:   0/7  pending   ░░░░░░░░░░  0%
LOW:      0/6  pending   ░░░░░░░░░░  0%
TOTAL:    1/17 complete  █░░░░░░░░░  6%

Recently Completed:
✅ TODO-002: PII Sanitization Middleware
```

---

## 📝 Notes

### Working on a TODO?
1. Create a branch: `git checkout -b feature/TODO-XXX-description`
2. Update this file: Mark as "in progress"
3. Commit with reference: `git commit -m "Implement TODO-005: Streaming responses"`

### Adding a new TODO?
- Use next available number (TODO-018, TODO-019, etc.)
- Include time estimate
- Mark dependencies if any
- Choose appropriate priority

### Priority Guidelines
- **🔴 HIGH:** Security issues, crashes, data loss risk
- **🟡 MEDIUM:** Performance, reliability, major features
- **🟢 LOW:** Nice-to-have, experimental, minor enhancements

### Security Improvements Completed
1. ✅ Path traversal protection (realpath)
2. ✅ Rate limiting (100 req/min/IP)
3. ✅ Body size limits (10MB)
4. ✅ Security headers (CSP, HSTS, X-Frame-Options)
5. ✅ PII sanitization (17 patterns)

### Next Recommended
After PII sanitization, consider:
1. TODO-004: Graceful shutdown (stability)
2. TODO-003: Request retry logic (reliability)
3. TODO-010: Structured logging (using new sanitization functions)

---

## 🔗 Related Documents

- [Security Audit](reports/security_audit.md)
- [Codebase Audit](reports/codebase_audit_2026-04-03.md)
- [Test Report](reports/test_report.md)
- [Improvement Suggestions](reports/improvement_suggestions.md)

---

*This TODO list is a living document. Update as work progresses.*
*Last updated: 2026-04-03 after PII sanitization implementation*
