"""FastAPI server that proxies requests to an upstream LLM API with filtering, compression, and caching."""

import asyncio
import json
import logging
import signal
import sys
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


# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Maximum request body size (10MB)
MAX_BODY_SIZE = 10 * 1024 * 1024

# Graceful shutdown settings
GRACEFUL_SHUTDOWN_TIMEOUT = 30.0  # seconds to wait for inflight requests
_shutdown_event = asyncio.Event()
_inflight_requests = 0
_inflight_lock = asyncio.Lock()


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


class InflightRequestMiddleware(BaseHTTPMiddleware):
    """Track inflight requests for graceful shutdown."""
    async def dispatch(self, request, call_next):
        global _inflight_requests
        async with _inflight_lock:
            _inflight_requests += 1
        
        try:
            response = await call_next(request)
            return response
        finally:
            async with _inflight_lock:
                _inflight_requests -= 1


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


def _handle_signal(sig, frame):
    """Handle shutdown signals (SIGTERM, SIGINT)."""
    signal_name = signal.Signals(sig).name
    logger.info(f"Received {signal_name}, initiating graceful shutdown...")
    _shutdown_event.set()


async def _wait_for_inflight_requests(timeout: float = GRACEFUL_SHUTDOWN_TIMEOUT):
    """Wait for inflight requests to complete."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        async with _inflight_lock:
            if _inflight_requests == 0:
                logger.info("All inflight requests completed")
                return True
        logger.info(f"Waiting for {_inflight_requests} inflight requests to complete...")
        await asyncio.sleep(0.5)
    
    async with _inflight_lock:
        if _inflight_requests > 0:
            logger.warning(f"Timeout reached, {inflight_requests} requests still inflight")
    return False


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _http_client, _cache
    
    # Setup signal handlers for graceful shutdown
    if sys.platform != "win32":
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda s=sig: _handle_signal(s, None))
    else:
        # Windows doesn't support add_signal_handler
        signal.signal(signal.SIGINT, _handle_signal)
        signal.signal(signal.SIGTERM, _handle_signal)
    
    # Startup
    logger.info("Starting LLM Proxy server...")
    
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
    
    logger.info(f"Connected to upstream: {base_url}")
    logger.info(f"Cache initialized: max_size={settings.cache_max_size}, ttl={settings.cache_ttl_seconds}s")
    
    yield
    
    # Shutdown
    logger.info("Shutting down LLM Proxy server...")
    
    # Wait for inflight requests to complete
    await _wait_for_inflight_requests(GRACEFUL_SHUTDOWN_TIMEOUT)
    
    # Close HTTP client
    if _http_client:
        logger.info("Closing HTTP client connections...")
        await _http_client.aclose()
    
    # Log final metrics
    if _cache:
        stats = _cache.stats()
        logger.info(f"Cache stats at shutdown: {stats}")
    
    summary = METRICS.summary()
    logger.info(f"Final metrics: {summary}")
    logger.info("Shutdown complete")


app = FastAPI(title="LLM Proxy", version="0.1.0", lifespan=lifespan)

# Add middleware (order matters - sanitize before other processing)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(SanitizationMiddleware, enabled=True)
app.add_middleware(InflightRequestMiddleware)


@app.get("/health")
async def health():
    return {"status": "ok", "inflight_requests": _inflight_requests}


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
            cached=True,
            latency_ms=cached_latency
        )
        return Response(
            content=response_body,
            status_code=200,
            headers={"Content-Type": "application/json", "X-Cache": "HIT"}
        )

    # Proxy to upstream
    if _http_client is None:
        return JSONResponse(status_code=503, content={"error": "Proxy not ready"})

    try:
        upstream_response = await _http_client.request(
            method=method,
            url=f"/{path}",
            headers=headers,
            json=transformed_payload if transformed_payload else None,
            content=body_bytes if not transformed_payload else None,
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Upstream timeout"})
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": "Upstream connection failed"})

    latency = (time.perf_counter() - start) * 1000

    response_body = upstream_response.content
    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError:
        response_data = None

    # Cache the response if it's a chat completion
    if is_chat_completion and settings.enable_cache and _cache is not None and response_data:
        _cache.set(transformed_payload, response_data)

    # Record metrics
    downstream_tokens = 0
    if response_data and "choices" in response_data:
        for choice in response_data.get("choices", []):
            content = choice.get("message", {}).get("content", "")
            downstream_tokens += count_message_tokens(content, payload.get("model", "gpt-4"))

    METRICS.record_request(
        upstream_tokens=original_token_count,
        downstream_tokens=downstream_tokens,
        cached=False,
        latency_ms=latency
    )

    return Response(
        content=response_body,
        status_code=upstream_response.status_code,
        headers={"Content-Type": "application/json", "X-Cache": "MISS"}
    )
