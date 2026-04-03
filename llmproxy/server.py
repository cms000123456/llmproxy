"""FastAPI server that proxies requests to an upstream LLM API with filtering, compression, and caching."""

import asyncio
import json
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .cache import LRUCache
from .metrics import METRICS
from .filters import filter_messages
from .compressors import compress_messages, count_message_tokens
from .middleware.sanitize import SanitizationMiddleware


# Maximum request body size (10MB)
MAX_BODY_SIZE = 10 * 1024 * 1024


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add security headers to all responses."""
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Content-Security-Policy"] = "default-src 'self'"
        return response


class BodySizeLimitMiddleware(BaseHTTPMiddleware):
    """Limit request body size to prevent memory exhaustion."""
    async def dispatch(self, request, call_next):
        if request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and int(content_length) > MAX_BODY_SIZE:
                return JSONResponse(
                    status_code=413,
                    content={"error": "Request body too large (max 10MB)"}
                )
        return await call_next(request)


# Simple in-memory rate limiter
_rate_limit_store = {}
RATE_LIMIT_REQUESTS = 100  # requests per window
RATE_LIMIT_WINDOW = 60     # seconds


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple rate limiting per client IP."""
    async def dispatch(self, request, call_next):
        client_ip = request.client.host if request.client else "unknown"
        now = time.time()
        
        # Clean old entries and check current window
        window_start = now - RATE_LIMIT_WINDOW
        _rate_limit_store[client_ip] = [
            ts for ts in _rate_limit_store.get(client_ip, [])
            if ts > window_start
        ]
        
        if len(_rate_limit_store[client_ip]) >= RATE_LIMIT_REQUESTS:
            return JSONResponse(
                status_code=429,
                content={"error": "Rate limit exceeded. Try again later."}
            )
        
        _rate_limit_store[client_ip].append(now)
        return await call_next(request)


def _kimi_code_headers() -> dict:
    device_id = settings.kimi_code_device_id or str(uuid.uuid4())
    return {
        "User-Agent": f"KimiCLI/{settings.kimi_code_version}",
        "X-Msh-Platform": "kimi_cli",
        "X-Msh-Version": settings.kimi_code_version,
        "X-Msh-Device-Name": settings.kimi_code_device_name,
        "X-Msh-Device-Id": device_id,
    }


# Shared state
_http_client: httpx.AsyncClient | None = None
_cache: LRUCache | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client, _cache
    # Avoid double /v1 when base_url already ends with it and client sends /v1/chat/completions
    base_url = settings.upstream_base_url
    if base_url.rstrip("/").endswith("/v1"):
        base_url = base_url.rstrip("/")[:-3]
    default_headers = {}
    if settings.upstream_api_key:
        default_headers["Authorization"] = f"Bearer {settings.upstream_api_key}"
    if settings.kimi_code_compat:
        default_headers.update(_kimi_code_headers())
    _http_client = httpx.AsyncClient(
        base_url=base_url,
        headers=default_headers,
        timeout=httpx.Timeout(120.0, connect=10.0),
    )
    _cache = LRUCache(max_size=settings.cache_max_size, ttl_seconds=settings.cache_ttl_seconds)
    yield
    await _http_client.aclose()


app = FastAPI(title="LLM Proxy", version="0.1.0", lifespan=lifespan)

# Add security middleware (order matters - sanitize before other processing)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SanitizationMiddleware, enabled=True)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/metrics")
async def metrics_endpoint():
    summary = METRICS.summary()
    cache_stats = _cache.stats() if _cache else {}
    return {"metrics": summary, "cache": cache_stats}


@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def proxy(request: Request, path: str):
    global _http_client, _cache

    method = request.method
    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("content-length", None)

    # Authorization override: use proxy config if no client key provided, else forward client key
    if not headers.get("authorization") and settings.upstream_api_key:
        headers["authorization"] = f"Bearer {settings.upstream_api_key}"

    # Kimi Code compatibility: inject agent headers and strip client fingerprints
    if settings.kimi_code_compat:
        # Remove any incoming user-agent so it doesn't get concatenated with KimiCLI
        headers.pop("user-agent", None)
        for k, v in _kimi_code_headers().items():
            headers[k] = v

    body_bytes = await request.body()
    payload = {}
    if body_bytes:
        try:
            payload = json.loads(body_bytes)
        except json.JSONDecodeError:
            pass

    # Only intercept chat completions for filtering/compression/cache
    is_chat_completion = path in ("chat/completions", "v1/chat/completions") or path.endswith("/chat/completions")

    original_token_count = 0
    transformed_payload = dict(payload)

    if is_chat_completion and isinstance(payload.get("messages"), list):
        messages = payload["messages"]
        original_token_count = count_message_tokens(messages, payload.get("model", "gpt-4"))

        # 1. Filter
        messages = filter_messages(messages, settings)
        # 2. Compress
        messages = compress_messages(messages, settings, payload.get("model", "gpt-4"))

        transformed_payload["messages"] = messages

    # Cache lookup
    cached = None
    if is_chat_completion and settings.enable_cache and _cache is not None:
        cached = _cache.get(transformed_payload)

    start = time.perf_counter()

    if cached is not None:
        response_data = cached
        # Recreate the response structure to match upstream format
        response_body = json.dumps(response_data).encode("utf-8")
        cached_latency = (time.perf_counter() - start) * 1000
        METRICS.record_request(
            upstream_tokens=original_token_count,
            downstream_tokens=count_message_tokens(
                response_data.get("choices", [{}])[0].get("message", {}).get("content", ""),
                payload.get("model", "gpt-4")
            ),
            latency_ms=cached_latency,
            cached=True
        )
        return Response(
            content=response_body,
            status_code=200,
            headers={"Content-Type": "application/json", "X-Cache": "HIT"}
        )

    # Upstream request
    try:
        upstream_resp = await _http_client.request(
            method=method,
            url=f"/{path}",
            headers=headers,
            json=transformed_payload if payload else None,
        )
        upstream_resp.raise_for_status()
        response_data = upstream_resp.json()
    except httpx.HTTPStatusError as e:
        METRICS.record_error()
        return JSONResponse(
            status_code=e.response.status_code,
            content={"error": f"Upstream error: {e.response.text}"}
        )
    except Exception as e:
        METRICS.record_error()
        return JSONResponse(
            status_code=502,
            content={"error": f"Proxy error: {str(e)}"}
        )

    # Record metrics
    latency_ms = (time.perf_counter() - start) * 1000
    downstream_messages = response_data.get("choices", [{}])[0].get("message", {}).get("content", "")
    downstream_tokens = count_message_tokens(downstream_messages, payload.get("model", "gpt-4"))

    METRICS.record_request(
        upstream_tokens=original_token_count,
        downstream_tokens=downstream_tokens,
        latency_ms=latency_ms,
        cached=False
    )

    # Cache the response
    if is_chat_completion and settings.enable_cache and _cache is not None:
        _cache.set(transformed_payload, response_data)

    response_body = json.dumps(response_data).encode("utf-8")
    return Response(
        content=response_body,
        status_code=upstream_resp.status_code,
        headers={"Content-Type": "application/json", "X-Cache": "MISS"}
    )
