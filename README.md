# LLM Proxy

A lightweight, OpenAI-compatible proxy that sits between your application and a paid LLM API (e.g., Moonshot / Kimi Code). It filters irrelevant context, compresses long conversations, caches responses, and can offload grunt-work to a **local Ollama model** so you save both time and money.

## Features

- **Smart Filtering**: Deduplicates system messages, strips empty messages, optionally removes large base64 images, and truncates overly long individual messages.
- **Conversation Compression**: Keeps the system prompt and recent messages. Optionally uses a **local Ollama model** to summarize old context instead of bluntly deleting it.
- **Relevance Filtering (Ollama)**: Ask a local model to score older messages against the latest user query and drop low-relevance fluff.
- **Response Caching**: Caches identical requests in memory with TTL to avoid redundant paid API calls.
- **Metrics Endpoint**: Real-time visibility into requests, cache hit rate, tokens saved, and latency.
- **OpenAI-Compatible**: Drop-in replacement for the base URL—works with any client that speaks the OpenAI chat completions API.
- **Dockerized**: One-command deployment with Docker Compose, including an optional Ollama sidecar.

## Quick Start (Local)

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure via environment variables
export LLM_PROXY_UPSTREAM_BASE_URL="https://api.moonshot.cn/v1"
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"
export LLM_PROXY_MAX_TOTAL_TOKENS=120000
export LLM_PROXY_ENABLE_CACHE=true

# 3. Run
python main.py
```

The proxy listens on `http://localhost:8080` by default.

## Quick Start (Docker Compose)

```bash
# 1. Set your upstream key
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# 2. Start the proxy + Ollama
# docker compose up -d

# 3. Pull a lightweight local model for compression/relevance work
# docker exec -it ollama ollama pull llama3.2
```

> **Note:** Run `docker compose up -d` after pulling the model. The proxy will talk to Ollama automatically on the internal Docker network at `http://ollama:11434`.

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

## Endpoints

- `POST /v1/chat/completions` — proxied with filtering, compression, and caching
- `GET /health` — health check
- `GET /metrics` — proxy metrics and cache stats
- All other paths — transparently forwarded to the upstream API

## Configuration

| Environment Variable | Default | Description |
|----------------------|---------|-------------|
| `LLM_PROXY_UPSTREAM_BASE_URL` | `https://api.moonshot.cn/v1` | Upstream API base URL |
| `LLM_PROXY_UPSTREAM_API_KEY` | `''` | Upstream API key |
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
| `LLM_PROXY_OLLAMA_MODEL` | `llama3.2` | Model name for local grunt work |
| `LLM_PROXY_OLLAMA_ENABLE_COMPRESSION` | `true` | Use Ollama to summarize old context |
| `LLM_PROXY_OLLAMA_ENABLE_RELEVANCE_FILTER` | `false` | Use Ollama to drop low-relevance older messages |
| `LLM_PROXY_OLLAMA_RELEVANCE_THRESHOLD` | `0.5` | Minimum relevance score (0–1) to keep a message |

## Architecture

```
Client Request
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
