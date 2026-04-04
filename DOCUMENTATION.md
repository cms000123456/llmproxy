# LLM Proxy Documentation

Complete documentation index for the LLM Proxy project.

## 📚 Documentation Structure

| Document | Purpose | Audience |
|----------|---------|----------|
| **[README.md](README.md)** | Project overview, quick start, features | Everyone |
| **[HOWTO.md](HOWTO.md)** | Detailed how-to guides | Users, Operators |
| **[LOAD_TESTING.md](LOAD_TESTING.md)** | Performance testing guide | DevOps, Engineers |
| **[TODO.md](TODO.md)** | Development roadmap | Contributors |
| **[monitoring/README.md](monitoring/README.md)** | Observability setup | Operators |

## 🚀 Quick Navigation

### Getting Started
1. **[README.md#quick-start](README.md#quick-start)** - Get up and running in 5 minutes
2. **[HOWTO.md#quick-start](HOWTO.md#quick-start)** - Detailed setup instructions
3. **[HOWTO.md#installation](HOWTO.md#installation)** - Installation options

### Configuration
- **[README.md#configuration](README.md#configuration)** - Environment variables reference
- **[HOWTO.md#environment-setup](HOWTO.md#environment-setup)** - Environment configuration
- **[.env-example](.env-example)** - Example configuration file

### Deployment
- **[HOWTO.md#docker-deployment](HOWTO.md#docker-deployment)** - Docker deployment guide
- **[HOWTO.md#development-stack](HOWTO.md#development-stack)** - Full development environment
- **[docker-compose.yml](docker-compose.yml)** - Production compose file
- **[docker-compose.dev.yml](docker-compose.dev.yml)** - Development compose file

### Security
- **[README.md#security-features](README.md#security-features)** - Security overview
- **[HOWTO.md#security-configuration](HOWTO.md#security-configuration)** - Security setup guide
- API Key Authentication, PII Sanitization, Rate Limiting

### Monitoring & Observability
- **[README.md#monitoring](README.md#monitoring)** - Monitoring overview
- **[monitoring/README.md](monitoring/README.md)** - Complete observability setup
- **[HOWTO.md#monitoring--observability](HOWTO.md#monitoring--observability)** - Metrics guide
- **[HOWTO.md#distributed-tracing](HOWTO.md#distributed-tracing)** - Jaeger tracing

### Testing & Benchmarking
- **[LOAD_TESTING.md](LOAD_TESTING.md)** - Load testing guide
- **[HOWTO.md#load-testing](HOWTO.md#load-testing)** - Load testing quick start
- **[README.md#benchmarking-savings](README.md#benchmarking-savings)** - Token savings benchmark

### Development
- **[TODO.md](TODO.md)** - Development roadmap and tasks
- **[HOWTO.md#development-stack](HOWTO.md#development-stack)** - Development environment
- **[HOWTO.md#troubleshooting](HOWTO.md#troubleshooting)** - Common issues and solutions

## 🏗️ Architecture Overview

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Client    │────▶│  LLM Proxy  │────▶│   Upstream  │
│  (OpenAI    │     │  (This      │     │   (Moonshot/│
│   Client)   │◀────│   Project)  │◀────│   Kimi/etc) │
└─────────────┘     └──────┬──────┘     └─────────────┘
                           │
           ┌───────────────┼───────────────┐
           ▼               ▼               ▼
    ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
    │   Redis     │ │   Ollama    │ │  Prometheus │
    │   (Cache)   │ │   (Local    │ │  (Metrics)  │
    │             │ │    LLM)     │ │             │
    └─────────────┘ └─────────────┘ └──────┬──────┘
                                           │
                                    ┌──────▼──────┐
                                    │   Grafana   │
                                    │ (Dashboards)│
                                    └─────────────┘
```

## 📖 Feature Documentation

### Core Features

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Smart Filtering** | Deduplicates system messages, removes empty messages, strips base64 images | [README.md](README.md) |
| **Conversation Compression** | Summarizes old context using Ollama | [README.md](README.md) |
| **Relevance Filtering** | Scores and drops low-relevance messages | [README.md](README.md) |
| **Response Caching** | Caches identical requests with TTL | [HOWTO.md#caching](HOWTO.md) |
| **API Key Auth** | Secure with API key authentication | [HOWTO.md#security-configuration](HOWTO.md) |
| **PII Sanitization** | Automatic redaction of sensitive data | [README.md#security-features](README.md) |

### Observability Features

| Feature | Description | Documentation |
|---------|-------------|---------------|
| **Prometheus Metrics** | Request counts, latency, cache stats | [monitoring/README.md](monitoring/README.md) |
| **Grafana Dashboards** | Pre-built visualization dashboards | [monitoring/README.md](monitoring/README.md) |
| **Alerting Rules** | Pre-configured alerts for critical issues | [monitoring/README.md](monitoring/README.md) |
| **Distributed Tracing** | Jaeger integration for request flows | [HOWTO.md#distributed-tracing](HOWTO.md) |
| **Load Testing** | Performance testing tool | [LOAD_TESTING.md](LOAD_TESTING.md) |

## 🔧 Configuration Reference

### Core Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROXY_UPSTREAM_BASE_URL` | `https://api.moonshot.cn/v1` | Upstream API URL |
| `LLM_PROXY_UPSTREAM_API_KEY` | - | Upstream API key |
| `LLM_PROXY_API_KEYS` | `[]` | Proxy API keys for client auth |
| `LLM_PROXY_ENABLE_CACHE` | `true` | Enable response caching |
| `LLM_PROXY_ENABLE_FILTERING` | `true` | Enable request filtering |
| `LLM_PROXY_ENABLE_COMPRESSION` | `true` | Enable conversation compression |

### Monitoring Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROXY_TRACING_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `LLM_PROXY_OTEL_EXPORTER_ENDPOINT` | `http://localhost:4318/v1/traces` | Jaeger endpoint |

### See Full List
- **[README.md#configuration](README.md#configuration)** - Complete environment variable reference
- **[.env-example](.env-example)** - Example configuration with all options

## 🐳 Docker Services

### Production (`docker-compose.yml`)
- **llmproxy** - Main proxy service
- **ollama** - Local LLM for compression

### Development (`docker-compose.dev.yml`)
- **llmproxy** - Proxy with hot reload
- **ollama** - Local LLM
- **redis** - Cache backend
- **jaeger** - Distributed tracing
- **prometheus** - Metrics collection
- **grafana** - Metrics dashboards

### Monitoring (`docker-compose.monitoring.yml`)
- **prometheus** - Metrics collection (port 9091)
- **grafana** - Dashboards (port 3002)
- **jaeger** - Tracing UI (port 16686)

## 🧪 Testing Tools

| Tool | Purpose | Usage |
|------|---------|-------|
| `pytest` | Unit tests | `pytest` or `./llmproxy.sh test` |
| `benchmark_local.py` | Token savings benchmark | `python benchmark_local.py` |
| `benchmark.py` | Live proxy benchmark | `python benchmark.py http://localhost:8080` |
| `load_test.py` | Load testing | `python load_test.py http://localhost:8080` |

## 🛠️ Utility Scripts

| Script | Purpose |
|--------|---------|
| `llmproxy.sh` | Convenience wrapper for common tasks |
| `agent.py` | Interactive coding agent CLI |
| `main.py` | Proxy server entry point |
| `load_test.py` | Load testing tool |
| `benchmark.py` | Performance benchmarking |

## 📊 Project Statistics

- **Python Code**: ~15,000 lines
- **Test Coverage**: Core functionality tested
- **Docker Images**: 3 compose files
- **Documentation**: ~5,000 lines
- **Monitoring**: Prometheus + Grafana + Jaeger

## 🤝 Contributing

See [TODO.md](TODO.md) for:
- Current development priorities
- Planned features
- Known issues
- Architecture decisions

## 📞 Support & Troubleshooting

| Issue | Solution |
|-------|----------|
| Setup problems | [HOWTO.md#troubleshooting](HOWTO.md) |
| Performance issues | [LOAD_TESTING.md](LOAD_TESTING.md) |
| Monitoring setup | [monitoring/README.md](monitoring/README.md) |
| Configuration | [.env-example](.env-example) |

## 📝 Changelog & History

- **v1.0** - Initial release with core proxy functionality
- **v1.1** - Added caching, filtering, compression
- **v1.2** - Added Ollama integration for local LLM
- **v1.3** - Added API key authentication
- **v1.4** - Added PII sanitization
- **v1.5** - Added Prometheus metrics and Grafana dashboards
- **v1.6** - Added alerting rules
- **v1.7** - Added cost tracking panels
- **v1.8** - Added Jaeger distributed tracing
- **v1.9** - Added load testing tool

---

**Last Updated**: 2025-04-04  
**Documentation Version**: 1.9
