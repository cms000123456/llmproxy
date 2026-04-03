"""Lightweight async client for a local Ollama instance."""

import json
import httpx
from typing import Optional

DEFAULT_OLLAMA_URL = "http://localhost:11434"


class OllamaClient:
    def __init__(self, base_url: str = DEFAULT_OLLAMA_URL, timeout: float = 60.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=timeout)

    async def generate(
        self,
        model: str,
        prompt: str,
        system: Optional[str] = None,
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str:
        payload = {
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
        data = resp.json()
        return data.get("response", "").strip()

    async def chat(
        self,
        model: str,
        messages: list[dict],
        stream: bool = False,
        options: Optional[dict] = None,
    ) -> str:
        payload = {
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
        data = resp.json()
        return data.get("message", {}).get("content", "").strip()

    async def list_models(self) -> list[str]:
        resp = await self._client.get(f"{self.base_url}/api/tags")
        resp.raise_for_status()
        data = resp.json()
        return [m["name"] for m in data.get("models", [])]

    async def is_available(self) -> bool:
        try:
            await self._client.get(f"{self.base_url}/", timeout=2.0)
            return True
        except Exception:
            return False

    async def aclose(self):
        await self._client.aclose()
