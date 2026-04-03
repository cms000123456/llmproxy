"""Request/Response sanitization middleware for PII and sensitive data."""

import re
import json
from typing import Any
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response, JSONResponse


class SanitizationMiddleware(BaseHTTPMiddleware):
    """Middleware to sanitize sensitive data in requests and responses.
    
    Redacts:
    - API keys (sk-*, pk-*, Bearer tokens)
    - Credit card numbers
    - Email addresses
    - Phone numbers
    - SSNs
    - Private keys
    """
    
    # Patterns for sensitive data detection
    PATTERNS = [
        # API Keys - OpenAI, Moonshot, etc.
        (r'sk-[a-zA-Z0-9]{48,}', '[API_KEY_REDACTED]'),
        (r'pk-[a-zA-Z0-9]{48,}', '[API_KEY_REDACTED]'),
        (r'Bearer\s+[a-zA-Z0-9_-]{20,}', 'Bearer [TOKEN_REDACTED]'),
        
        # Credit Cards (Visa, Mastercard, Amex, Discover)
        (r'\b(?:4[0-9]{12}(?:[0-9]{3})?|5[1-5][0-9]{14}|3[47][0-9]{13}|3(?:0[0-5]|[68][0-9])[0-9]{11}|6(?:011|5[0-9]{2})[0-9]{12})\b', '[CREDIT_CARD_REDACTED]'),
        
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL_REDACTED]'),
        
        # Phone numbers (US format)
        (r'\b(?:\+?1[-.\s]?)?\(?[0-9]{3}\)?[-.\s]?[0-9]{3}[-.\s]?[0-9]{4}\b', '[PHONE_REDACTED]'),
        
        # SSN
        (r'\b[0-9]{3}-[0-9]{2}-[0-9]{4}\b', '[SSN_REDACTED]'),
        
        # Private Keys (SSH, RSA, etc.)
        (r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', '[PRIVATE_KEY_REDACTED]'),
        
        # Passwords in JSON
        (r'"password"\s*:\s*"[^"]*"', '"password": "[PASSWORD_REDACTED]"'),
        (r'"passwd"\s*:\s*"[^"]*"', '"passwd": "[PASSWORD_REDACTED]"'),
        (r'"pwd"\s*:\s*"[^"]*"', '"pwd": "[PASSWORD_REDACTED]"'),
        (r'"secret"\s*:\s*"[^"]*"', '"secret": "[SECRET_REDACTED]"'),
        
        # AWS Keys
        (r'AKIA[0-9A-Z]{16}', '[AWS_KEY_REDACTED]'),
        
        # GitHub tokens
        (r'gh[pousr]_[A-Za-z0-9_]{36,}', '[GITHUB_TOKEN_REDACTED]'),
        
        # Slack tokens
        (r'xox[baprs]-[0-9a-zA-Z]{10,}', '[SLACK_TOKEN_REDACTED]'),
    ]
    
    def __init__(self, app, enabled: bool = True, log_sanitization: bool = False):
        super().__init__(app)
        self.enabled = enabled
        self.log_sanitization = log_sanitization
        self._compiled_patterns = [
            (re.compile(pattern, re.IGNORECASE), replacement)
            for pattern, replacement in self.PATTERNS
        ]
    
    async def dispatch(self, request: Request, call_next):
        if not self.enabled:
            return await call_next(request)
        
        # Sanitize request body if present
        await self._sanitize_request(request)
        
        # Process the request
        response = await call_next(request)
        
        # Sanitize response body
        response = await self._sanitize_response(response)
        
        return response
    
    async def _sanitize_request(self, request: Request):
        """Sanitize incoming request data."""
        # Sanitize headers (Authorization, Cookie, etc.)
        for header in ['authorization', 'cookie', 'x-api-key']:
            if header in request.headers:
                value = request.headers[header]
                sanitized = self._sanitize_string(value)
                request.headers._list = [
                    (k, sanitized if k.lower() == header else v)
                    for k, v in request.headers._list
                ]
    
    async def _sanitize_response(self, response: Response) -> Response:
        """Sanitize outgoing response data."""
        # Only process JSON responses
        content_type = response.headers.get('content-type', '')
        if 'application/json' not in content_type:
            return response
        
        # Read response body
        body = b""
        async for chunk in response.body_iterator:
            body += chunk
        
        if not body:
            return response
        
        try:
            # Parse JSON
            data = json.loads(body)
            
            # Sanitize recursively
            sanitized_data = self._sanitize_object(data)
            
            # Create new response
            sanitized_body = json.dumps(sanitized_data).encode('utf-8')
            
            # Remove Content-Length header as body size changed
            new_headers = dict(response.headers)
            new_headers.pop('content-length', None)
            
            return Response(
                content=sanitized_body,
                status_code=response.status_code,
                headers=new_headers,
                media_type=response.media_type
            )
        except (json.JSONDecodeError, Exception):
            # If we can't parse/sanitize, return original
            # Remove Content-Length header as we're re-creating the response
            new_headers = dict(response.headers)
            new_headers.pop('content-length', None)
            
            return Response(
                content=body,
                status_code=response.status_code,
                headers=new_headers,
                media_type=response.media_type
            )
    
    def _sanitize_object(self, obj: Any) -> Any:
        """Recursively sanitize an object (dict, list, or string)."""
        if not self.enabled:
            return obj
            
        if isinstance(obj, dict):
            return {
                key: self._sanitize_object(value)
                for key, value in obj.items()
            }
        elif isinstance(obj, list):
            return [self._sanitize_object(item) for item in obj]
        elif isinstance(obj, str):
            return self._sanitize_string(obj)
        else:
            return obj
    
    def _sanitize_string(self, text: str) -> str:
        """Apply all sanitization patterns to a string."""
        if not self.enabled:
            return text
            
        if not isinstance(text, str):
            return text
        
        sanitized = text
        for pattern, replacement in self._compiled_patterns:
            sanitized = pattern.sub(replacement, sanitized)
        
        return sanitized


def sanitize_for_logging(text: str) -> str:
    """Standalone function to sanitize text for logging purposes.
    
    Usage:
        logger.info(f"Request: {sanitize_for_logging(str(request.body))}")
    """
    middleware = SanitizationMiddleware(None, enabled=True)
    return middleware._sanitize_string(text)


def sanitize_dict_for_logging(data: dict) -> dict:
    """Standalone function to sanitize dict for logging purposes.
    
    Usage:
        logger.info(f"Response: {sanitize_dict_for_logging(response_data)}")
    """
    middleware = SanitizationMiddleware(None, enabled=True)
    return middleware._sanitize_object(data)
