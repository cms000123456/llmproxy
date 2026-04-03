#!/usr/bin/env python3
"""Entry point for LLM Proxy."""

import uvicorn
from llmproxy.config import settings

if __name__ == "__main__":
    uvicorn.run(
        "llmproxy.server:app",
        host=settings.host,
        port=settings.port,
        log_level=settings.log_level.lower(),
    )
