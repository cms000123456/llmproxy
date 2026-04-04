from __future__ import annotations

"""Lightweight async client for a local Ollama instance."""

from typing import Any

import httpx

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaClient:
    def __init__(
        self,
        base_url: str = DEFAULT_OLLAMA_URL,
        timeout: float = 60.0,
        api_key: str | None = None,
    ):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.api_key = api_key

        # Setup headers with optional auth
        headers: dict[str, str] = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        self._client = httpx.AsyncClient(timeout=timeout, headers=headers)

    async def generate(
        self,
        model: str,
        prompt: str,
        system: str | None = None,
        stream: bool = False,
        options: dict | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "stream": stream,
        }
        if system:
            payload["system"] = system
        if options:
            payload["options"] = options

        resp = await self._client.post(
            f"{self.base_url}/api/generate",
            json=payload,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        response_text = data.get("response", "")
        return str(response_text).strip() if response_text else ""

    async def chat(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        options: dict | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": model,
            "messages": messages,
            "stream": stream,
        }
        if options:
            payload["options"] = options

        resp = await self._client.post(
            f"{self.base_url}/api/chat",
            json=payload,
        )
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        message = data.get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""
        return str(content).strip() if content else ""

    async def list_models(self) -> list[str]:
        resp = await self._client.get(f"{self.base_url}/api/tags")
        resp.raise_for_status()
        data: dict[str, Any] = resp.json()
        models = data.get("models", [])
        return [str(m["name"]) for m in models if isinstance(m, dict) and "name" in m]

    async def is_available(self) -> bool:
        try:
            await self._client.get(f"{self.base_url}/", timeout=2.0)
            return True
        except Exception:
            return False

    async def aclose(self) -> None:
        await self._client.aclose()
