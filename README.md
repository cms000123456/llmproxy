# LLM Proxy

A lightweight, OpenAI-compatible proxy that sits between your application and a paid LLM API (e.g., Moonshot / Kimi Code). It filters irrelevant context, compresses long conversations, caches responses, and can offload grunt-work to a **local Ollama model** so you save both time and money.

## Features

- **Smart Filtering**: Deduplicates system messages, strips empty messages, optionally removes large base64 images, and truncates overly long individual messages.
- **Conversation Compression**: Keeps the system prompt and recent messages. Optionally uses a **local Ollama model** to summarize old context instead of bluntly deleting it.
- **Relevance Filtering (Ollama)**: Ask a local model to score older messages against the latest user query and drop low-relevance fluff.
- **Response Caching**: Caches identical requests in memory with TTL to avoid redundant paid API calls.
- **🔐 API Key Authentication**: Secure your proxy with API key authentication. Supports Bearer tokens and X-API-Key headers.
- **🛡️ PII Sanitization**: Automatically redacts sensitive data (credit cards, emails, API keys, SSNs) from requests and responses.
- **📊 Metrics Endpoint**: Real-time visibility into requests, cache hit rate, tokens saved, and latency.
- **🔄 Graceful Shutdown**: Handles SIGTERM/SIGINT properly, waits for inflight requests to complete.
- **OpenAI-Compatible**: Drop-in replacement for the base URL—works with any client that speaks the OpenAI chat completions API.
- **Coding Agent CLI**: A Kimi-Code/Claude-Code style terminal agent with filesystem tools (read, write, shell, grep, ls).
- **Dockerized**: One-command deployment with Docker Compose, including an optional Ollama sidecar.

## Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure via environment variables
export LLM_PROXY_UPSTREAM_BASE_URL="https://api.moonshot.cn/v1"
export LLM_PROXY_UPSTREAM_API_KEY="your-upstream-api-key"
export LLM_PROXY_MAX_TOTAL_TOKENS=120000
export LLM_PROXY_ENABLE_CACHE=true

# 3. Run
python main.py
```

### Convenience Wrapper

A shell wrapper script is included so you don't have to remember Python paths:

```bash
./llmproxy.sh proxy          # Start the proxy server
./llmproxy.sh agent          # Start the interactive coding agent CLI
./llmproxy.sh run "..."      # Run a one-shot agent prompt
./llmproxy.sh bench-local    # Run local token-savings benchmark
./llmproxy.sh test           # Run unit tests
```

The proxy listens on `http://localhost:8080` by default.

## Quick Start (Docker Compose)

```bash
# 1. Set your upstream key
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# 2. Start the proxy + Ollama (with GPU support)
docker compose up -d

# 3. Pull a lightweight local model for compression/relevance work
docker exec ollama ollama pull llama3.2
```

> **Note:** The Ollama container is configured with GPU support (`deploy.resources.reservations.devices`). The proxy will talk to Ollama automatically on the internal Docker network at `http://ollama:11434`.

## Usage with a Client

Point your client at the proxy instead of the upstream API:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="your-upstream-api-key",  # forwarded to upstream
)

response = client.chat.completions.create(
    model="moonshot-v1-128k",
    messages=[...],
)
```

### With API Key Authentication

If you've configured `LLM_PROXY_API_KEYS`, clients must authenticate:

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="llmproxy_your_proxy_api_key",  # Proxy auth key
    default_headers={"X-Upstream-API-Key": "your-upstream-api-key"}  # If different
)
```

Or using `X-API-Key` header:

```bash
curl -H "X-API-Key: llmproxy_your_key" \
     -H "Content-Type: application/json" \
     -d '{"model": "moonshot-v1-128k", "messages": [{"role": "user", "content": "Hello"}]}' \
     http://localhost:8080/v1/chat/completions
```

## Endpoints

- `POST /v1/chat/completions` — proxied with filtering, compression, and caching
- `GET /health` — health check (shows inflight requests)
- `GET /metrics` — proxy metrics and cache stats
- All other paths — transparently forwarded to the upstream API

### Health Endpoint

```bash
curl http://localhost:8080/health
# {"status": "ok", "inflight_requests": 3}
```

### Metrics Endpoint

```bash
curl http://localhost:8080/metrics
# Shows: requests_total, cache_hits, cache_misses, tokens_saved, avg_latency_ms
```

## Coding Agent CLI

A built-in terminal agent that talks through the proxy (or directly to any OpenAI-compatible endpoint) and can read files, write code, run shell commands, search your codebase, and list directories.

```bash
# Interactive REPL
python agent.py

# One-shot prompt
python agent.py "Refactor the README to be more concise"

# Point at the local proxy (default)
python agent.py -b http://localhost:8080/v1 -m kimi-for-coding "List files and explain the project"
```

### CLI Environment Variables

| Variable | Default | Description |
|-----------|---------|-------------|
| `LLM_PROXY_BASE_URL` | `http://localhost:8080/v1` | API base URL for the agent |
| `LLM_PROXY_UPSTREAM_API_KEY` | `''` | API key |
| `LLM_PROXY_MODEL` | `kimi-for-coding` | Model ID |

## Security Features

### API Key Authentication

Protect your proxy with API key authentication:

```bash
# Generate a key
python -c "from llmproxy.auth import generate_api_key; print(generate_api_key())"

# Configure (JSON array of keys)
export LLM_PROXY_API_KEYS='["llmproxy_abc123...", "llmproxy_xyz789..."]'
export LLM_PROXY_AUTH_ENABLED=true  # default: true
```

Features:
- Supports `Authorization: Bearer <key>` and `X-API-Key: <key>` headers
- Constant-time key comparison (prevents timing attacks)
- Health and metrics endpoints remain public
- When no keys configured, proxy operates in open mode (useful for local dev)

### PII Sanitization

Automatic redaction of sensitive data from requests and responses:

- Credit card numbers
- Email addresses
- Phone numbers
- SSNs
- API keys (various formats)
- Private keys (SSH, RSA)
- AWS/GitHub/Slack tokens
- Passwords in JSON payloads

Always active via `SanitizationMiddleware`.

### Rate Limiting

Basic rate limiting per IP (100 requests/minute by default).

### Security Headers

All responses include:
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `X-XSS-Protection: 1; mode=block`
- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `Content-Security-Policy: default-src 'self'`

### Body Size Limits

Maximum request body size: 10MB (configurable).

## Benchmarking Savings

Measure how much the proxy saves in tokens and estimated cost without making any network calls:

```bash
python benchmark_local.py
```

Example output on an 8K token budget:

| Scenario | Raw Tokens | After Proxy | Saved | Reduction |
|----------|-----------|-------------|-------|-----------|
| Long context chat | 24,050 | 7,818 | 16,232 | **67.5%** |
| Massive history | 24,067 | 7,628 | 16,439 | **68.3%** |
| Image bloat (base64) | 62,546 | 24 | 62,522 | **100%** |
| **Overall batch** | 116,115 | 20,914 | 95,201 | **82.0%** |

You can also benchmark live against a running proxy instance:

```bash
python benchmark.py http://localhost:8080
```

## Configuration

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `LLM_PROXY_UPSTREAM_BASE_URL` | `https://api.moonshot.cn/v1` | Upstream API base URL |
| `LLM_PROXY_UPSTREAM_API_KEY` | `''` | Upstream API key |
| `LLM_PROXY_API_KEYS` | `[]` | JSON array of valid API keys for client authentication |
| `LLM_PROXY_AUTH_ENABLED` | `true` | Enable/disable API key authentication |
| `LLM_PROXY_HOST` | `0.0.0.0` | Proxy bind host |
| `LLM_PROXY_PORT` | `8080` | Proxy bind port |
| `LLM_PROXY_ENABLE_FILTERING` | `true` | Enable request filtering |
| `LLM_PROXY_ENABLE_COMPRESSION` | `true` | Enable prompt compression |
| `LLM_PROXY_COMPRESSION_STRATEGY` | `truncate_oldest` | `truncate_oldest` or `summarize_oldest` |
| `LLM_PROXY_MAX_TOTAL_TOKENS` | `120000` | Target token budget for compressed prompts |
| `LLM_PROXY_MAX_MESSAGE_LENGTH` | `32000` | Max characters per individual message |
| `LLM_PROXY_ENABLE_CACHE` | `true` | Enable response caching |
| `LLM_PROXY_CACHE_TTL_SECONDS` | `300` | Cache entry TTL |
| `LLM_PROXY_CACHE_MAX_SIZE` | `1000` | Max cached entries |
| `LLM_PROXY_OLLAMA_BASE_URL` | `http://localhost:11434` | Local Ollama instance URL |
| `LLM_PROXY_OLLAMA_API_KEY` | `''` | Optional API key for Ollama (if behind auth proxy) |
| `LLM_PROXY_OLLAMA_MODEL` | `llama3.2` | Model name for local grunt work |
| `LLM_PROXY_OLLAMA_ENABLE_COMPRESSION` | `true` | Use Ollama to summarize old context |
| `LLM_PROXY_OLLAMA_ENABLE_RELEVANCE_FILTER` | `false` | Use Ollama to drop low-relevance older messages |
| `LLM_PROXY_OLLAMA_RELEVANCE_THRESHOLD` | `0.5` | Minimum relevance score (0–1) to keep a message |
| `LLM_PROXY_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## Architecture

```
Client Request
    │
    ▼
┌─────────────────┐
│  Security Check │ ← Body size limit, API key auth, rate limiting
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Sanitization  │ ← PII redaction (credit cards, emails, keys)
└────────┬────────┘
         │
         ▼
┌─────────────┐
│   Filter    │ ← dedupe system msgs, strip empties, truncate long msgs
└──────┬──────┘
       │
       ▼
┌──────────────────┐
│ Relevance Filter │ ← (optional) Ollama scores older messages vs latest query
│  (Ollama)        │   drops low-scoring messages
└──────┬───────────┘
       │
       ▼
┌──────────────────┐
│  Compress        │ ← truncate oldest, or ask Ollama to summarize old context
│  (Rules/Ollama)  │
└──────┬───────────┘
       │
       ▼
┌─────────────┐
│    Cache    │ ← return cached response if exact match exists
└──────┬──────┘
       │
       ▼
┌─────────────┐
│   Upstream  │ ← paid LLM API
└─────────────┘
```

## Extending

- Add custom filters in `llmproxy/filters.py`.
- Implement summarization in `llmproxy/compressors.py` by calling a cheaper model inside `_summarize_oldest()`.
- Swap the in-memory cache in `llmproxy/cache.py` for Redis if you need distributed caching.
- Add custom authentication logic in `llmproxy/auth.py`.
- Modify PII patterns in `llmproxy/middleware/sanitize.py`.

## Production Deployment

### Docker with Authentication

```bash
# Generate API keys
KEY1=$(python -c "from llmproxy.auth import generate_api_key; print(generate_api_key())")
KEY2=$(python -c "from llmproxy.auth import generate_api_key; print(generate_api_key())")

echo "Proxy Key 1: $KEY1"
echo "Proxy Key 2: $KEY2"

# Run with authentication
export LLM_PROXY_API_KEYS="[\"$KEY1\", \"$KEY2\"]"
export LLM_PROXY_UPSTREAM_API_KEY="your-upstream-key"
docker compose up -d
```

### Graceful Shutdown

The proxy handles SIGTERM/SIGINT gracefully:
1. Stops accepting new connections
2. Waits up to 30s for inflight requests to complete
3. Closes HTTP client connections
4. Logs final metrics

Works correctly with Docker/Kubernetes rolling updates.

## License

MIT License - see LICENSE file for details.
