# syntax=docker/dockerfile:1
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast package management (optional but nice)
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Copy deps and install
COPY requirements.txt .
RUN uv pip install --system -r requirements.txt

# Copy source
COPY . .

EXPOSE 8080

ENV PYTHONUNBUFFERED=1
ENV LLM_PROXY_HOST=0.0.0.0
ENV LLM_PROXY_PORT=8080

CMD ["python", "main.py"]
