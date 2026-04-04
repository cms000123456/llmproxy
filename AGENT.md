# Project Agent Configuration

This file contains project-specific instructions for the coding agent.
Edit this file to customize how the agent works with your project.

## Project Context

<!-- 
Describe what this project does, its purpose, and high-level architecture.
Example: "A web API for managing user data with FastAPI and PostgreSQL"
-->

This is an LLM Proxy that provides filtering, compression, caching, and routing capabilities for LLM API calls.

## Technology Stack

<!-- 
List the main technologies, frameworks, and versions the project uses.
This helps the agent use correct syntax and patterns.
-->

- **Language**: Python 3.9+
- **Framework**: FastAPI
- **Key Dependencies**: pydantic, httpx, tiktoken, opentelemetry
- **Testing**: pytest
- **Linting**: ruff, mypy

## Code Style Guidelines

<!-- 
Project-specific coding conventions not covered by general guidelines.
-->

- Use type hints everywhere
- Follow Google docstring style
- Keep functions under 50 lines when possible
- Use `from __future__ import annotations` in all files
- Prefer `pathlib.Path` over `os.path`

## Common Tasks

<!-- 
Typical workflows or patterns for this project.
The agent will follow these when appropriate.
-->

1. Read existing code before modifying
2. Write tests for new features  
3. Run linting before committing
4. Update AGENT.md with project-specific context

## Important Files/Directories

<!-- 
Key files or directories the agent should know about.
-->

- `llmproxy/` - Main source code
- `tests/` - Test files
- `docs/` - Documentation
- `AGENT.md` - This file (project context for agent)

## Project-Specific Notes

<!-- 
Any other context that would help the agent work effectively with this codebase.
-->

- The proxy sits between clients and upstream LLM APIs
- Supports A/B testing between different upstream providers
- Has built-in cost tracking and metrics
- Uses structured logging with structlog
- Middleware pattern for request/response processing
