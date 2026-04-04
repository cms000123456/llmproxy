from __future__ import annotations

"""API Key authentication middleware for LLM Proxy."""

import secrets
from typing import TYPE_CHECKING, Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from .config import settings
from .logging_config import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

logger = get_logger(__name__)


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """Middleware to authenticate requests using API keys.

    Supports API key authentication via:
    - Authorization header (Bearer token)
    - X-API-Key header

    If no api_keys are configured, all requests are allowed (open mode).
    """

    def __init__(self, app: Any, enabled: bool = True) -> None:  # noqa: ANN401
        super().__init__(app)
        self.enabled = enabled
        self.api_keys = set(settings.api_keys) if settings.api_keys else set()

        if self.api_keys:
            logger.info(f"API key authentication enabled with {len(self.api_keys)} key(s)")
        else:
            logger.warning("API key authentication disabled - no keys configured (open mode)")

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Any]]
    ) -> Any:
        # Skip authentication if disabled or no keys configured
        if not self.enabled or not self.api_keys:
            return await call_next(request)

        # Skip authentication for health and metrics endpoints
        path = request.url.path
        if path in ("/health", "/metrics"):
            return await call_next(request)

        # Extract API key from request
        api_key = self._extract_api_key(request)

        if not api_key:
            logger.warning(f"Authentication failed: No API key provided for {path}")
            return JSONResponse(
                status_code=401,
                content={
                    "error": "Unauthorized",
                    "message": "API key required. Provide via 'Authorization: Bearer <key>' or 'X-API-Key: <key>' header",
                },
            )

        if not self._validate_api_key(api_key):
            logger.warning(f"Authentication failed: Invalid API key for {path}")
            return JSONResponse(
                status_code=401, content={"error": "Unauthorized", "message": "Invalid API key"}
            )

        # Add authenticated client info to request state
        request.state.api_key = api_key[:8] + "..." if len(api_key) > 8 else api_key

        return await call_next(request)

    def _extract_api_key(self, request: Request) -> str | None:
        """Extract API key from request headers.

        Checks in order:
        1. Authorization: Bearer <key>
        2. X-API-Key: <key>
        """
        # Check Authorization header (Bearer token)
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            return auth_header[7:].strip()

        # Check X-API-Key header
        api_key_header = request.headers.get("x-api-key", "")
        if api_key_header:
            return api_key_header.strip()

        return None

    def _validate_api_key(self, api_key: str) -> bool:
        """Validate API key using constant-time comparison to prevent timing attacks."""
        return any(
            secrets.compare_digest(api_key, valid_key)
            for valid_key in self.api_keys
        )


def generate_api_key(prefix: str = "llmproxy") -> str:
    """Generate a secure random API key.

    Format: <prefix>_<32-char-random-string>

    Example: llmproxy_a3f8b2c9d1e4f5a6b7c8d9e0f1a2b3c4
    """
    import secrets
    import string

    alphabet = string.ascii_letters + string.digits
    random_part = "".join(secrets.choice(alphabet) for _ in range(32))
    return f"{prefix}_{random_part}"


class APIKeyManager:
    """Utility class for managing API keys."""

    @staticmethod
    def add_key(new_key: str) -> bool:
        """Add a new API key to the configuration."""
        if not new_key:
            return False

        current_keys = set(settings.api_keys)
        if new_key in current_keys:
            return False

        current_keys.add(new_key)
        settings.api_keys = list(current_keys)
        return True

    @staticmethod
    def remove_key(key_to_remove: str) -> bool:
        """Remove an API key from the configuration."""
        current_keys = set(settings.api_keys)
        if key_to_remove not in current_keys:
            return False

        current_keys.discard(key_to_remove)
        settings.api_keys = list(current_keys)
        return True

    @staticmethod
    def list_keys() -> list[str]:
        """List all configured API keys (masked)."""
        return [key[:8] + "..." + key[-4:] if len(key) > 12 else "***" for key in settings.api_keys]

    @staticmethod
    def is_authenticated(request: Request) -> bool:
        """Check if the current request is authenticated."""
        return hasattr(request.state, "api_key")

    @staticmethod
    def get_client_id(request: Request) -> str | None:
        """Get the authenticated client ID (API key prefix) for the request."""
        return getattr(request.state, "api_key", None)  # type: ignore[return-value]
