"""FastAPI server that proxies requests to an upstream LLM API with filtering, compression, and caching."""

import asyncio
import hashlib
import json
import logging
import random
import signal
import sys
from typing import AsyncIterator
import time
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.middleware.base import BaseHTTPMiddleware

from .config import settings
from .storage import create_backend, MemoryBackend
from .metrics import METRICS
from .filters import filter_messages
from .compressors import compress_messages, count_message_tokens
from .middleware.sanitize import SanitizationMiddleware
from .auth import APIKeyAuthMiddleware, APIKeyManager


# Cache key generation
def _make_cache_key(payload: dict) -> str:
    """Generate a deterministic cache key from request payload."""
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

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


def _calculate_backoff(attempt: int, base: float, max_wait: float) -> float:
    """Calculate exponential backoff with jitter.
    
    Args:
        attempt: Current retry attempt (0-indexed)
        base: Base wait time in seconds
        max_wait: Maximum wait time in seconds
    
    Returns:
        Wait time in seconds
    """
    # Exponential backoff: base * 2^attempt
    wait = base * (2 ** attempt)
    # Add jitter (±25%) to avoid thundering herd
    jitter = wait * 0.25 * (2 * random.random() - 1)
    wait = wait + jitter
    # Cap at max_wait
    return min(wait, max_wait)


async def _upstream_request_with_retry(
    http_client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    json_payload: dict | None,
    content: bytes | None,
    max_retries: int,
    backoff_base: float,
    max_wait: float
) -> httpx.Response:
    """Make an upstream request with exponential backoff retry logic.
    
    Retries on:
    - Timeouts (httpx.TimeoutException)
    - Connection errors (httpx.ConnectError, httpx.NetworkError)
    - 5xx server errors (500, 502, 503, 504)
    - 429 rate limit responses (with Retry-After header support)
    
    Args:
        http_client: Async HTTP client
        method: HTTP method
        url: Request URL
        headers: Request headers
        json_payload: JSON payload (if any)
        content: Raw content (if no JSON payload)
        max_retries: Maximum number of retry attempts
        backoff_base: Base backoff time in seconds
        max_wait: Maximum wait time between retries
    
    Returns:
        HTTP response
    
    Raises:
        httpx.TimeoutException: If all retries exhausted
        httpx.ConnectError: If all retries exhausted
        httpx.HTTPStatusError: For non-retryable errors (4xx except 429)
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            response = await http_client.request(
                method=method,
                url=url,
                headers=headers,
                json=json_payload,
                content=content,
            )
            
            # Check if we should retry based on status code
            if response.status_code == 429:
                # Rate limited - check for Retry-After header
                retry_after = response.headers.get("retry-after")
                if retry_after:
                    try:
                        wait_time = float(retry_after)
                    except (ValueError, TypeError):
                        wait_time = _calculate_backoff(attempt, backoff_base, max_wait)
                else:
                    wait_time = _calculate_backoff(attempt, backoff_base, max_wait)
                
                if attempt < max_retries:
                    logger.warning(f"Rate limited (429), retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
            
            if 500 <= response.status_code < 600:
                # Server error - retry
                if attempt < max_retries:
                    wait_time = _calculate_backoff(attempt, backoff_base, max_wait)
                    logger.warning(f"Upstream server error {response.status_code}, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                    await asyncio.sleep(wait_time)
                    continue
            
            # Success or non-retryable error
            return response
            
        except httpx.TimeoutException as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = _calculate_backoff(attempt, backoff_base, max_wait)
                logger.warning(f"Upstream timeout, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Upstream timeout after {max_retries + 1} attempts")
                raise
                
        except (httpx.ConnectError, httpx.NetworkError) as e:
            last_exception = e
            if attempt < max_retries:
                wait_time = _calculate_backoff(attempt, backoff_base, max_wait)
                logger.warning(f"Upstream connection error, retrying in {wait_time:.1f}s (attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait_time)
            else:
                logger.error(f"Upstream connection failed after {max_retries + 1} attempts")
                raise
    
    # Should not reach here, but just in case
    if last_exception:
        raise last_exception
    
    raise RuntimeError("Unexpected error in retry logic")


async def _stream_upstream_response(
    http_client: httpx.AsyncClient,
    method: str,
    url: str,
    headers: dict,
    json_payload: dict | None,
) -> tuple[int, dict, AsyncIterator[str]]:
    """Stream response from upstream LLM API.
    
    For streaming requests, we don't use retry logic - we fail fast.
    The client should handle reconnection if needed.
    
    Args:
        http_client: Async HTTP client
        method: HTTP method
        url: Request URL
        headers: Request headers
        json_payload: JSON payload (if any)
    
    Returns:
        Tuple of (status_code, response_headers, chunk_iterator)
    
    Raises:
        httpx.TimeoutException: If upstream times out
        httpx.ConnectError: If upstream connection fails
    """
    request = http_client.build_request(
        method=method,
        url=url,
        headers=headers,
        json=json_payload,
    )
    
    response = await http_client.send(request, stream=True)
    
    async def chunk_iterator():
        """Iterate over SSE chunks from upstream."""
        accumulated_content = []
        try:
            async for chunk in response.aiter_text():
                # Check if shutdown requested
                if _shutdown_event.is_set():
                    logger.info("Shutdown requested, closing stream")
                    break
                
                # Forward chunk as-is (it's already SSE formatted)
                yield chunk
                
                # Accumulate content for metrics (optional optimization: skip for performance)
                if chunk.startswith("data: ") and chunk != "data: [DONE]\n\n":
                    try:
                        data = json.loads(chunk[6:])  # Remove "data: " prefix
                        if "choices" in data and len(data["choices"]) > 0:
                            delta = data["choices"][0].get("delta", {})
                            if "content" in delta:
                                accumulated_content.append(delta["content"])
                    except json.JSONDecodeError:
                        pass
        finally:
            await response.aclose()
            
            # Record metrics after stream completes
            if accumulated_content:
                content = "".join(accumulated_content)
                # Note: We don't have the model here, would need to pass it in
                # For now, metrics are recorded at a higher level
    
    # Extract headers to forward
    response_headers = {
        "content-type": response.headers.get("content-type", "text/event-stream"),
        "cache-control": "no-cache",
        "x-cache": "MISS",
    }
    
    return response.status_code, response_headers, chunk_iterator()


# Shared state
_http_client: httpx.AsyncClient | None = None
_cache = None


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
            logger.warning(f"Timeout reached, {_inflight_requests} requests still inflight")
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
    # Initialize storage backend
    if settings.enable_cache:
        try:
            _cache = create_backend(
                settings.cache_backend,
                max_size=settings.cache_max_size,
                ttl_seconds=settings.cache_ttl_seconds,
                redis_url=settings.redis_url,
                redis_key_prefix=settings.redis_key_prefix
            )
            logger.info(f"Cache backend: {settings.cache_backend}")
        except Exception as e:
            logger.error(f"Failed to initialize cache backend: {e}")
            _cache = None
    else:
        _cache = None
    
    logger.info(f"Connected to upstream: {base_url}")
    logger.info(f"Cache initialized: max_size={settings.cache_max_size}, ttl={settings.cache_ttl_seconds}s")
    logger.info(f"Retry config: max_retries={settings.max_retries}, backoff={settings.retry_backoff}s")
    logger.info(f"Streaming support: enabled")
    
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

# Add middleware (order matters - first added runs first, last runs closest to handler)
# Order: SecurityHeaders -> BodySizeLimit -> Auth -> RateLimit -> Sanitize -> Inflight
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(BodySizeLimitMiddleware)
app.add_middleware(APIKeyAuthMiddleware, enabled=settings.auth_enabled)
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
    # Note: We check if authorization header contains one of our api_keys
    auth_header = headers.get("authorization", "")
    api_keys_set = set(settings.api_keys)
    
    if auth_header.startswith("Bearer "):
        provided_key = auth_header[7:].strip()
        if provided_key in api_keys_set:
            # This is our auth key, replace with upstream key
            if settings.upstream_api_key:
                headers["authorization"] = f"Bearer {settings.upstream_api_key}"
        # else: forward client's key to upstream
    elif settings.upstream_api_key:
        # No auth header, use upstream key
        headers["authorization"] = f"Bearer {settings.upstream_api_key}"
    # else: forward client's key to upstream

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
    
    # Check if this is a streaming request
    is_streaming = is_chat_completion and payload.get("stream") == True

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

    # Handle streaming requests differently
    if is_streaming:
        # Streaming requests bypass cache and use different handling
        if _http_client is None:
            return JSONResponse(status_code=503, content={"error": "Proxy not ready"})
        
        start = time.perf_counter()
        
        try:
            # For streaming, we don't retry - fail fast and let client reconnect
            status_code, response_headers, chunk_iterator = await _stream_upstream_response(
                http_client=_http_client,
                method=method,
                url=f"/{path}",
                headers=headers,
                json_payload=transformed_payload if transformed_payload else None,
            )
            
            # Return streaming response
            return StreamingResponse(
                content=chunk_iterator,
                status_code=status_code,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Cache": "MISS",
                    "X-Streaming": "true",
                }
            )
            
        except httpx.TimeoutException:
            return JSONResponse(status_code=504, content={"error": "Upstream timeout"})
        except httpx.ConnectError:
            return JSONResponse(status_code=502, content={"error": "Upstream connection failed"})
        except httpx.NetworkError as e:
            return JSONResponse(status_code=502, content={"error": f"Upstream network error: {str(e)}"})

    # Non-streaming path with caching and retry logic
    # Cache lookup
    cached = None
    if is_chat_completion and settings.enable_cache and _cache is not None:
        cached = _cache.get(_make_cache_key(transformed_payload))

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

    # Proxy to upstream with retry logic
    if _http_client is None:
        return JSONResponse(status_code=503, content={"error": "Proxy not ready"})

    try:
        upstream_response = await _upstream_request_with_retry(
            http_client=_http_client,
            method=method,
            url=f"/{path}",
            headers=headers,
            json_payload=transformed_payload if transformed_payload else None,
            content=body_bytes if not transformed_payload else None,
            max_retries=settings.max_retries,
            backoff_base=settings.retry_backoff,
            max_wait=settings.retry_max_wait
        )
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"error": "Upstream timeout after retries"})
    except httpx.ConnectError:
        return JSONResponse(status_code=502, content={"error": "Upstream connection failed after retries"})
    except httpx.NetworkError as e:
        return JSONResponse(status_code=502, content={"error": f"Upstream network error: {str(e)}"})

    latency = (time.perf_counter() - start) * 1000

    response_body = upstream_response.content
    try:
        response_data = json.loads(response_body)
    except json.JSONDecodeError:
        response_data = None

    # Cache the response if it's a chat completion
    if is_chat_completion and settings.enable_cache and _cache is not None and response_data:
        _cache.set(_make_cache_key(transformed_payload), response_data)

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

    # Forward all response headers except encoding/length (we're sending raw content)
    response_headers = dict(upstream_response.headers)
    response_headers.pop("content-encoding", None)
    response_headers.pop("content-length", None)
    response_headers.pop("transfer-encoding", None)
    response_headers["X-Cache"] = "MISS"

    return Response(
        content=response_body,
        status_code=upstream_response.status_code,
        headers=response_headers
    )
