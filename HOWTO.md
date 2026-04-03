# LLM Proxy - How-To Guide

A practical guide for using the LLM Proxy and Coding Agent CLI.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Running the Proxy](#running-the-proxy)
- [Security Configuration](#security-configuration)
- [Using the Coding Agent](#using-the-coding-agent)
- [Project Workflow](#project-workflow)
- [Session Management](#session-management)
- [Environment Setup](#environment-setup)
- [Development Stack](#development-stack)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd llmproxy
source .venv/bin/activate

# 2. Configure your API key
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# 3. Start the proxy
./llmproxy.sh proxy

# 4. In another terminal, use the agent
cd ~/projects/my-project
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
```

---

## Installation

### Prerequisites

- Python 3.11+
- (Optional) Docker & Docker Compose
- (Optional) NVIDIA GPU for Ollama local models

### Local Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Verify Installation

```bash
./llmproxy.sh test        # Run unit tests
./llmproxy.sh bench-local # Run local benchmark
```

---

## Running the Proxy

### Option 1: Local (Development)

```bash
# Set required environment variables
export LLM_PROXY_UPSTREAM_BASE_URL="https://api.moonshot.cn/v1"
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# Start the proxy
./llmproxy.sh proxy

# Proxy is now running at http://localhost:8080
```

### Option 2: Docker (Production)

```bash
# Ensure Docker has GPU support (for Ollama)
docker compose up -d

# Pull a local model for compression
docker exec ollama ollama pull llama3.2

# Check status
curl http://localhost:8080/health
```

### Verify Proxy is Running

```bash
curl http://localhost:8080/health
# Expected: {"status":"ok", "inflight_requests": 0}

curl http://localhost:8080/metrics
# Shows usage metrics and cache stats
```

---

## Security Configuration

### API Key Authentication

Protect your proxy by requiring API keys from clients.

#### 1. Generate API Keys

```bash
# Generate a new key
python -c "from llmproxy.auth import generate_api_key; print(generate_api_key())"

# Example output: llmproxy_a3f8b2c9d1e4f5a6b7c8d9e0f1a2b3c4
```

#### 2. Configure Keys

```bash
# Single key
export LLM_PROXY_API_KEYS='["llmproxy_your_key_here"]'

# Multiple keys
export LLM_PROXY_API_KEYS='["llmproxy_key_1", "llmproxy_key_2", "llmproxy_key_3"]'

# Disable authentication (open mode - not recommended for production)
export LLM_PROXY_AUTH_ENABLED=false
```

#### 3. Use the Proxy with Authentication

**Option A: Bearer Token (recommended)**

```bash
curl -H "Authorization: Bearer llmproxy_your_key" \
     -H "Content-Type: application/json" \
     -d '{"model": "moonshot-v1-128k", "messages": [{"role": "user", "content": "Hello"}]}' \
     http://localhost:8080/v1/chat/completions
```

**Option B: X-API-Key Header**

```bash
curl -H "X-API-Key: llmproxy_your_key" \
     -H "Content-Type: application/json" \
     -d '{"model": "moonshot-v1-128k", "messages": [{"role": "user", "content": "Hello"}]}' \
     http://localhost:8080/v1/chat/completions
```

**Option C: Python OpenAI Client**

```python
from openai import OpenAI

# If proxy key equals upstream key (simplest)
client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="llmproxy_your_key"
)

# If proxy key differs from upstream key
client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="llmproxy_your_key",
    default_headers={"X-Upstream-API-Key": "your-upstream-key"}
)
```

#### 4. Public Endpoints

The following endpoints don't require authentication (even when enabled):

- `GET /health` - Health check
- `GET /metrics` - Metrics and statistics

#### 5. Managing Keys at Runtime

```python
from llmproxy.auth import APIKeyManager, generate_api_key

# List configured keys (masked)
APIKeyManager.list_keys()
# ['llmproxy...5678']

# Add a new key
new_key = generate_api_key()
APIKeyManager.add_key(new_key)

# Remove a key
APIKeyManager.remove_key(new_key)
```

### PII Sanitization

The proxy automatically redacts sensitive information from requests and responses:

**Redacted Data Types:**
- Credit card numbers (Visa, Mastercard, Amex, Discover)
- Email addresses
- Phone numbers (US format)
- Social Security Numbers
- API keys (OpenAI, AWS, GitHub, Slack)
- Private keys (SSH, RSA)
- Passwords in JSON payloads

**Example:**

```json
// Before sanitization
{
  "messages": [
    {"role": "user", "content": "My email is user@example.com and my card is 4111111111111111"}
  ]
}

// After sanitization (sent to upstream)
{
  "messages": [
    {"role": "user", "content": "My email is [EMAIL_REDACTED] and my card is [CREDIT_CARD_REDACTED]"}
  ]
}
```

PII sanitization is always active and cannot be disabled.

### Rate Limiting

Basic rate limiting is enabled by default:

- **Limit:** 100 requests per minute per IP
- **Scope:** Per-client IP address
- **Public endpoints:** Not rate limited (`/health`, `/metrics`)

If you exceed the limit:

```json
{"error": "Rate limit exceeded. Try again later."}
```

### Security Headers

All responses include security headers:

```
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 1; mode=block
Strict-Transport-Security: max-age=31536000; includeSubDomains
Content-Security-Policy: default-src 'self'
```

### Body Size Limits

Maximum request body size is 10MB by default. Requests exceeding this will receive:

```json
{"error": "Request body too large (max 10MB)"}
```

---

## Using the Coding Agent

### Start Interactive Mode

```bash
# Navigate to your project directory
cd ~/projects/my-awesome-project

# Start the agent (creates new session automatically)
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
```

### What You'll See

```
╭──────────────────── Welcome ─────────────────────╮
│ Coding Agent                                     │
│ Model: kimi-for-coding                           │
│ Base URL: http://localhost:8080/v1               │
│ Workspace: /home/cms/projects/my-awesome-project │
│ Session: 20250403_143022_a1b2c3d4...            │
│ Tokens: 0 (↑0 ↓0) | Est. cost: $0.0000          │
╰──────────────────────────────────────────────────╯
You: 
```

### Example Commands

```
You: Create a Python FastAPI app with user authentication
You: Read the main.py file and explain what it does
You: Find all TODO comments in this codebase
You: Run pytest and fix any failing tests
You: Create a Dockerfile for this project
```

### One-Shot Mode (Non-Interactive)

```bash
# Run a single command without entering interactive mode
./llmproxy.sh run "Create a README.md for this project"

# With custom model
./llmproxy.sh run -m gpt-4 "Refactor this code to use async/await"
```

---

## Project Workflow

### 1. Create New Project

```bash
# Create project directory
mkdir ~/projects/my-new-api
cd ~/projects/my-new-api

# Start coding with AI assistant
/media/cms/data/repositories/llmproxy/llmproxy.sh agent

# Ask the agent to scaffold the project
You: Create a FastAPI project structure with tests folder
```

### 2. Work on Existing Project

```bash
cd ~/projects/existing-project

# List previous sessions
/media/cms/data/repositories/llmproxy/llmproxy.sh agent --list

# Resume where you left off
/media/cms/data/repositories/llmproxy/llmproxy.sh agent --resume
```

### 3. Switch Between Projects

Sessions are **completely isolated** by directory:

```bash
# Project A - Web API
cd ~/projects/web-api
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
# → New session for web-api

# Project B - Data Pipeline  
cd ~/projects/data-pipeline
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
# → New session for data-pipeline (separate context!)
```

---

## Session Management

Sessions store conversation history and are persisted between restarts.

### Session Storage

- Location: `.llmproxy_sessions/` in each workspace
- Format: JSON files
- Naming: `{timestamp}_{hash}.json`

### List Sessions

```bash
/media/cms/data/repositories/llmproxy/llmproxy.sh agent --list
```

### Resume Last Session

```bash
/media/cms/data/repositories/llmproxy/llmproxy.sh agent --resume
```

### Switch Session

```bash
# In interactive mode
You: /switch
# Shows numbered list of sessions to choose from
```

### Session Isolation

Sessions are completely isolated by workspace:
- Different directories = different session sets
- No cross-contamination between projects
- Sessions persist in project directory (commit to git or add to .gitignore)

---

## Environment Setup

### Development Environment

Create a `.env` file in the project root:

```bash
# Copy example
cp .env-example .env

# Edit with your values
nano .env
```

Example `.env`:

```bash
# Upstream API
LLM_PROXY_UPSTREAM_BASE_URL=https://api.moonshot.cn/v1
LLM_PROXY_UPSTREAM_API_KEY=your-upstream-key

# Authentication (optional, recommended for shared environments)
LLM_PROXY_API_KEYS=["llmproxy_dev_key_123"]

# Proxy settings
LLM_PROXY_PORT=8080
LLM_PROXY_ENABLE_CACHE=true

# Ollama (optional)
LLM_PROXY_OLLAMA_ENABLE_COMPRESSION=true
LLM_PROXY_OLLAMA_MODEL=llama3.2
# LLM_PROXY_OLLAMA_API_KEY=your-key  # Only if Ollama is behind auth
```

### Production Environment

For production deployments, use stronger authentication:

```bash
# Generate strong random keys
KEY1=$(python -c "from llmproxy.auth import generate_api_key; print(generate_api_key())")
KEY2=$(python -c "from llmproxy.auth import generate_api_key; print(generate_api_key())")

# Export keys securely (use secrets manager in real production)
export LLM_PROXY_API_KEYS="[\"$KEY1\", \"$KEY2\"]"
export LLM_PROXY_UPSTREAM_API_KEY="your-upstream-key"

# Disable auth only in trusted local networks
export LLM_PROXY_AUTH_ENABLED=true

# Start server
./llmproxy.sh proxy
```

---

## Docker Deployment

### Basic Docker Compose

```bash
# Start services
docker compose up -d

# View logs
docker compose logs -f proxy

# Stop services
docker compose down
```

### With Authentication

Create a `docker-compose.override.yml`:

```yaml
services:
  proxy:
    environment:
      - LLM_PROXY_API_KEYS=["llmproxy_prod_key_abc123"]
      - LLM_PROXY_AUTH_ENABLED=true
```

### Production Docker Setup

```bash
# 1. Create environment file
cat > .env.production << 'EOF'
LLM_PROXY_UPSTREAM_BASE_URL=https://api.moonshot.cn/v1
LLM_PROXY_UPSTREAM_API_KEY=${UPSTREAM_API_KEY}
LLM_PROXY_API_KEYS=${PROXY_API_KEYS}
LLM_PROXY_AUTH_ENABLED=true
LLM_PROXY_ENABLE_CACHE=true
LLM_PROXY_CACHE_MAX_SIZE=10000
LLM_PROXY_LOG_LEVEL=INFO
EOF

# 2. Deploy with docker compose
docker compose --env-file .env.production up -d

# 3. Check health
curl -H "X-API-Key: your-key" http://localhost:8080/health
```

### Kubernetes Considerations

```yaml
# Example deployment snippet
apiVersion: apps/v1
kind: Deployment
spec:
  template:
    spec:
      containers:
      - name: llm-proxy
        image: llmproxy:latest
        env:
        - name: LLM_PROXY_API_KEYS
          valueFrom:
            secretKeyRef:
              name: llm-proxy-secrets
              key: api-keys
        - name: LLM_PROXY_UPSTREAM_API_KEY
          valueFrom:
            secretKeyRef:
              name: llm-proxy-secrets
              key: upstream-key
        lifecycle:
          preStop:
            exec:
              command: ["/bin/sh", "-c", "sleep 10"]
```

The proxy handles SIGTERM gracefully with a 30-second timeout for inflight requests.

---

---

## Development Stack

For local development with full observability, use `docker-compose.dev.yml` which includes:

- **LLM Proxy** (port 8080) - With Redis cache backend
- **Ollama** (port 11434) - Local LLM for compression & summarization
- **Redis** (port 6379) - Cache backend
- **Jaeger** (port 16686) - Distributed tracing UI
- **Prometheus** (port 9090) - Metrics collection
- **Grafana** (port 3000) - Metrics dashboards

### Starting the Development Stack

```bash
# Start all services
docker-compose -f docker-compose.dev.yml up -d

# Pull a lightweight model for Ollama
docker exec ollama-dev ollama pull llama3.2

# View logs
docker-compose -f docker-compose.dev.yml logs -f llmproxy
```

### Accessing Services

| Service | URL | Description |
|---------|-----|-------------|
| LLM Proxy | http://localhost:8080 | Main proxy endpoint |
| Jaeger UI | http://localhost:16686 | Trace visualization |
| Prometheus | http://localhost:9090 | Metrics querying |
| Grafana | http://localhost:3000 | Dashboards (login: admin/admin) |
| Redis | localhost:6379 | Cache (CLI: `redis-cli`) |
| Ollama | http://localhost:11434 | Local LLM API |

### Configuration

The development stack uses these default settings:

```yaml
# Cache backend
LLM_PROXY_CACHE_BACKEND=redis
LLM_PROXY_REDIS_URL=redis://redis:6379

# Debug logging
LLM_PROXY_LOG_LEVEL=DEBUG

# Ollama integration
LLM_PROXY_OLLAMA_BASE_URL=http://ollama:11434
LLM_PROXY_OLLAMA_ENABLE_COMPRESSION=true
```

Override via environment variables or `.env` file.

### Stopping the Stack

```bash
# Stop all services
docker-compose -f docker-compose.dev.yml down

# Stop and remove volumes (reset data)
docker-compose -f docker-compose.dev.yml down -v
```

### Grafana Dashboards

Grafana is pre-configured with Prometheus as a datasource. To create dashboards:

1. Login at http://localhost:3000 (admin/admin)
2. Go to "Create" → "Dashboard"
3. Add panels using Prometheus metrics:
   - `llmproxy_requests_total` - Total request count
   - `llmproxy_request_duration_seconds` - Request latency
   - `llmproxy_cache_hits_total` - Cache hit count
   - `llmproxy_tokens_total` - Token usage

### Jaeger Tracing

View distributed traces:

1. Open http://localhost:16686
2. Select "llmproxy" service
3. Click "Find Traces"

Each proxy request is traced with spans for:
- Request processing
- Cache lookups
- Upstream API calls
- Compression/summarization


---

## Troubleshooting

### Authentication Issues

**Problem:** Getting 401 "Unauthorized" errors

```bash
# Check if auth is enabled
curl http://localhost:8080/health
# If auth is enabled, this works without key (public endpoint)

# Test with key
curl -H "Authorization: Bearer your-key" http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "test", "messages": []}'

# Verify key is configured
python -c "from llmproxy.config import settings; print(settings.api_keys)"
```

**Problem:** Keys not being recognized

- Ensure keys are in valid JSON array format: `["key1", "key2"]`
- Check for proper quoting in shell: `export LLM_PROXY_API_KEYS='["key"]'
- Verify no trailing spaces in keys

### Connection Issues

**Problem:** Can't connect to proxy

```bash
# Check if port is in use
lsof -i :8080

# Check proxy logs
./llmproxy.sh proxy 2>&1 | head -50

# Test with verbose curl
curl -v http://localhost:8080/health
```

**Problem:** Upstream connection fails

```bash
# Check upstream connectivity
curl -H "Authorization: Bearer $LLM_PROXY_UPSTREAM_API_KEY" \
  $LLM_PROXY_UPSTREAM_BASE_URL/models
```

### Cache Issues

**Problem:** Not seeing cache hits

```bash
# Check cache stats
curl http://localhost:8080/metrics

# Clear cache by restarting proxy
# Or disable temporarily: LLM_PROXY_ENABLE_CACHE=false
```

### Ollama Issues

**Problem:** Ollama not available

```bash
# Check if Ollama is running
docker exec ollama ollama list

# Pull model manually
docker exec ollama ollama pull llama3.2

# Check Ollama logs
docker compose logs ollama
```

### Performance Issues

**Problem:** High latency

```bash
# Check metrics for bottleneck
curl http://localhost:8080/metrics | python -m json.tool

# Look for:
# - Cache hit rate (should be >20% for repeated queries)
# - Average latency
# - Token savings
```

### Getting Help

1. Check logs: `./llmproxy.sh proxy` (run without `-d` for verbose output)
2. Run tests: `./llmproxy.sh test`
3. Check [TODO.md](TODO.md) for known issues
4. Review [improvement_suggestions.md](reports/improvement_suggestions.md)

---

## Tips & Best Practices

### Security

1. **Always enable authentication** in shared environments
2. **Rotate keys regularly** using `APIKeyManager`
3. **Use different keys** for different clients/teams
4. **Store keys securely** (use Docker secrets, K8s secrets, or env files)
5. **Monitor metrics** for unusual activity

### Performance

1. **Enable caching** for repetitive queries
2. **Use Ollama compression** for long conversations
3. **Set appropriate token limits** for your use case
4. **Monitor cache hit rates** and adjust TTL if needed

### Cost Optimization

1. **Use local models** for compression/relevance filtering
2. **Cache aggressively** for deterministic queries
3. **Filter and compress** before sending to upstream
4. **Monitor metrics** to track savings

---

*For more details, see [README.md](README.md) and [TODO.md](TODO.md)*
