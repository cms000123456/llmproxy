from __future__ import annotations

"""Local LLM provider using Ollama - OpenAI-compatible API.

This module provides a full OpenAI-compatible chat completions endpoint
using local Ollama models. This enables fully offline/local operation
without requiring any upstream API.

Best models for coding (2025):
- qwen2.5-coder:7b / 14b / 32b  - Excellent coding performance, various sizes
- deepseek-coder:6.7b / 33b     - Great for complex algorithms
- codellama:7b / 13b / 34b      - Meta's code-optimized Llama
- llama3.3 / llama4:latest      - General purpose, good for coding
- magicoder:7b                  - Speed + quality balance

VRAM Requirements:
- 7B models:  ~8-16GB VRAM
- 14B models: ~16-24GB VRAM  
- 32B models: ~32-48GB VRAM
- 70B models: ~64GB+ VRAM

Example usage with ollama CLI:
    ollama pull qwen2.5-coder:14b
    ollama run qwen2.5-coder:14b
"""

import json
import time
import uuid
from typing import Any, AsyncIterator

import httpx
from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from .config import settings
from .logging_config import get_logger

logger = get_logger(__name__)

# Model aliases for convenience
MODEL_ALIASES = {
    # Coding-optimized models
    "local-coder": "qwen2.5-coder:14b",
    "local-coder-small": "qwen2.5-coder:7b",
    "local-coder-large": "qwen2.5-coder:32b",
    # General purpose
    "local": "llama3.3:latest",
    "local-fast": "llama3.2:3b",
    # DeepSeek variants
    "local-deepseek": "deepseek-coder:6.7b",
    "local-deepseek-large": "deepseek-coder:33b",
    # CodeLlama variants
    "local-codellama": "codellama:13b",
    "local-codellama-small": "codellama:7b",
    "local-codellama-large": "codellama:34b",
}

# Recommended models with descriptions
RECOMMENDED_MODELS = {
    "qwen2.5-coder:14b": {
        "description": "Best balance of quality and speed for coding",
        "vram_gb": 16,
        "strengths": ["Code generation", "Debugging", "Refactoring"],
    },
    "qwen2.5-coder:7b": {
        "description": "Fast coding assistant for everyday tasks",
        "vram_gb": 8,
        "strengths": ["Quick completions", "Simple debugging", "Documentation"],
    },
    "deepseek-coder:6.7b": {
        "description": "Strong algorithmic reasoning",
        "vram_gb": 8,
        "strengths": ["Complex algorithms", "Math", "Problem solving"],
    },
    "codellama:13b": {
        "description": "Reliable all-rounder from Meta",
        "vram_gb": 16,
        "strengths": ["General coding", "Multiple languages", "Explanations"],
    },
    "llama3.3:latest": {
        "description": "Latest general-purpose model",
        "vram_gb": 24,
        "strengths": ["General tasks", "Code + chat", "Reasoning"],
    },
}


class LocalProvider:
    """OpenAI-compatible provider using local Ollama models."""

    def __init__(self, base_url: str | None = None, timeout: float = 120.0):
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            headers = {}
            if settings.ollama_api_key:
                headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=headers,
                timeout=httpx.Timeout(self.timeout, connect=10.0),
            )
        return self._client

    def _resolve_model(self, model: str) -> str:
        """Resolve model alias to actual Ollama model name."""
        return MODEL_ALIASES.get(model, model)

    async def is_available(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            client = await self._get_client()
            resp = await client.get("/api/tags", timeout=5.0)
            return resp.status_code == 200
        except Exception as e:
            logger.debug(f"Ollama not available: {e}")
            return False

    async def list_models(self) -> list[dict[str, Any]]:
        """List available Ollama models."""
        client = await self._get_client()
        try:
            resp = await client.get("/api/tags")
            resp.raise_for_status()
            data = resp.json()
            models = []
            for m in data.get("models", []):
                name = m.get("name", "")
                model_info = {
                    "id": name,
                    "object": "model",
                    "created": int(time.time()),
                    "owned_by": "ollama",
                    "ollama_details": m,
                }
                # Add our recommendations if applicable
                if name in RECOMMENDED_MODELS:
                    model_info["recommendation"] = RECOMMENDED_MODELS[name]
                models.append(model_info)
            return models
        except httpx.HTTPError as e:
            raise HTTPException(status_code=503, detail=f"Ollama error: {e}")

    async def chat_completions(
        self,
        model: str,
        messages: list[dict],
        temperature: float = 0.7,
        max_tokens: int | None = None,
        stream: bool = False,
        tools: list[dict] | None = None,
        **kwargs,
    ) -> dict | StreamingResponse:
        """Create chat completion - OpenAI compatible format."""
        resolved_model = self._resolve_model(model)
        
        # Build Ollama chat payload
        payload: dict[str, Any] = {
            "model": resolved_model,
            "messages": messages,
            "stream": stream,
            "options": {
                "temperature": temperature,
            },
        }
        
        if max_tokens:
            payload["options"]["num_predict"] = max_tokens

        # Map additional options
        if "top_p" in kwargs:
            payload["options"]["top_p"] = kwargs["top_p"]
        if "seed" in kwargs:
            payload["options"]["seed"] = kwargs["seed"]

        client = await self._get_client()

        try:
            if stream:
                return await self._stream_chat(payload, resolved_model)
            else:
                return await self._chat(payload, resolved_model)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(
                    status_code=404,
                    detail=f"Model '{resolved_model}' not found. Run: ollama pull {resolved_model}",
                )
            raise HTTPException(status_code=502, detail=f"Ollama error: {e}")
        except httpx.ConnectError:
            raise HTTPException(
                status_code=503,
                detail=f"Cannot connect to Ollama at {self.base_url}. Is it running?",
            )

    async def _chat(self, payload: dict, model: str) -> dict:
        """Non-streaming chat completion."""
        client = await self._get_client()
        resp = await client.post("/api/chat", json=payload)
        resp.raise_for_status()
        data = resp.json()

        # Convert Ollama response to OpenAI format
        content = data.get("message", {}).get("content", "")
        
        # Estimate tokens (Ollama doesn't always return this)
        prompt_tokens = data.get("prompt_eval_count", 0)
        completion_tokens = data.get("eval_count", 0)
        
        # Rough estimation if not provided
        if prompt_tokens == 0:
            prompt_tokens = sum(len(m.get("content", "")) // 4 for m in payload["messages"])
        if completion_tokens == 0:
            completion_tokens = len(content) // 4

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": "stop" if not data.get("done_reason") else data["done_reason"],
                }
            ],
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": prompt_tokens + completion_tokens,
            },
        }

    async def _stream_chat(self, payload: dict, model: str) -> StreamingResponse:
        """Streaming chat completion."""
        payload["stream"] = True
        client = await self._get_client()
        
        request = client.build_request("POST", "/api/chat", json=payload)
        
        async def event_generator() -> AsyncIterator[str]:
            completion_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
            created = int(time.time())
            
            async with client.stream(request) as response:
                response.raise_for_status()
                
                # Send initial role chunk
                yield f"data: {json.dumps({
                    'id': completion_id,
                    'object': 'chat.completion.chunk',
                    'created': created,
                    'model': model,
                    'choices': [{'index': 0, 'delta': {'role': 'assistant'}, 'finish_reason': None}],
                })}\n\n"
                
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    
                    try:
                        data = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    
                    message = data.get("message", {})
                    content = message.get("content", "")
                    
                    if content:
                        chunk = {
                            "id": completion_id,
                            "object": "chat.completion.chunk",
                            "created": created,
                            "model": model,
                            "choices": [
                                {
                                    "index": 0,
                                    "delta": {"content": content},
                                    "finish_reason": None,
                                }
                            ],
                        }
                        yield f"data: {json.dumps(chunk)}\n\n"
                    
                    if data.get("done"):
                        # Final chunk
                        yield f"data: {json.dumps({
                            'id': completion_id,
                            'object': 'chat.completion.chunk',
                            'created': created,
                            'model': model,
                            'choices': [{'index': 0, 'delta': {}, 'finish_reason': 'stop'}],
                        })}\n\n"
                        break
                
                yield "data: [DONE]\n\n"
        
        return StreamingResponse(
            content=event_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Local-Model": "true",
            },
        )

    async def embeddings(
        self,
        model: str,
        input: str | list[str],
        **kwargs,
    ) -> dict:
        """Create embeddings (if supported by Ollama model)."""
        resolved_model = self._resolve_model(model)
        
        # Ollama embeddings API
        client = await self._get_client()
        
        texts = [input] if isinstance(input, str) else input
        embeddings = []
        
        for text in texts:
            payload = {
                "model": resolved_model,
                "prompt": text,
            }
            resp = await client.post("/api/embeddings", json=payload)
            resp.raise_for_status()
            data = resp.json()
            embeddings.append(data.get("embedding", []))
        
        return {
            "object": "list",
            "data": [
                {
                    "object": "embedding",
                    "embedding": emb,
                    "index": i,
                }
                for i, emb in enumerate(embeddings)
            ],
            "model": model,
            "usage": {
                "prompt_tokens": sum(len(t) // 4 for t in texts),
                "total_tokens": sum(len(t) // 4 for t in texts),
            },
        }

    async def aclose(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global provider instance
_local_provider: LocalProvider | None = None


def get_local_provider() -> LocalProvider:
    """Get or create the global local provider instance."""
    global _local_provider
    if _local_provider is None:
        _local_provider = LocalProvider()
    return _local_provider


def reset_local_provider() -> None:
    """Reset the global provider (for testing)."""
    global _local_provider
    _local_provider = None
