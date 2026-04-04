# syntax=docker/dockerfile:1
# Multi-stage build for optimized production image

# Stage 1: Builder
FROM python:3.14-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install uv for faster package installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy and install dependencies
COPY requirements.txt pyproject.toml ./
RUN uv pip install --system --no-cache -r requirements.txt

# Stage 2: Production
FROM python:3.14-slim AS production

WORKDIR /app

# Create non-root user for security
RUN groupadd -r llmproxy && useradd -r -g llmproxy llmproxy \
    && mkdir -p /app/data /app/logs \
    && chown -R llmproxy:llmproxy /app

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.14/site-packages /usr/local/lib/python3.14/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application code
COPY --chown=llmproxy:llmproxy . .

# Switch to non-root user
USER llmproxy

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV LLM_PROXY_HOST=0.0.0.0
ENV LLM_PROXY_PORT=8080

# Run the application
CMD ["python", "main.py"]

# Stage 3: Development (includes dev dependencies)
FROM builder AS development

WORKDIR /app

# Install dev dependencies
RUN uv pip install --system --no-cache \
    pytest>=8.0.0 \
    pytest-asyncio>=0.23.0 \
    ruff>=0.1.0 \
    mypy>=1.8.0

# Copy full source
COPY . .

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV LLM_PROXY_HOST=0.0.0.0
ENV LLM_PROXY_PORT=8080

CMD ["python", "main.py"]
