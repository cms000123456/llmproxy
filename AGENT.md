# Project Agent Configuration

This file contains project-specific instructions for the coding agent.
Run `/init` in the agent to create this file with defaults.

## Project Context

<!-- Describe your project here - what it does, its architecture, etc. -->

This is an LLM Proxy that provides filtering, compression, caching, and routing capabilities for LLM API calls.

## Technology Stack

<!-- List the main technologies, frameworks, versions -->

- **Language**: Python 3.9+
- **Framework**: FastAPI
- **Key Dependencies**: pydantic, httpx, tiktoken, opentelemetry
- **Testing**: pytest
- **Linting**: ruff, mypy

## Code Style Guidelines

<!-- Project-specific coding conventions -->

- Use type hints everywhere
- Follow Google docstring style
- Keep functions under 50 lines when possible
- Use `from __future__ import annotations` in all files
- Prefer `pathlib.Path` over `os.path`

## Architecture Decisions

<!-- Important architectural patterns or constraints -->

- All I/O is async using `aiofiles` and `httpx.AsyncClient`
- Configuration uses Pydantic Settings with env var support
- Storage backends are pluggable (memory, redis)
- Middleware pattern for request/response processing

## Common Tasks

<!-- Typical workflows for this project -->

### Adding a new endpoint
1. Add route handler in `llmproxy/server.py`
2. Add tests in `tests/test_*.py`
3. Update documentation

### Adding a new filter
1. Add filter function in `llmproxy/filters.py`
2. Add test in `tests/test_filters.py`
3. Register in filter pipeline

## Project-Specific Notes

<!-- Any other context the agent should know -->

- The proxy sits between clients and upstream LLM APIs
- Supports A/B testing between different upstream providers
- Has built-in cost tracking and metrics
- Uses structured logging with structlog
