#!/bin/bash
# Type checking script for LLM Proxy

echo "Running mypy type checker..."
. .venv/bin/activate

# Run mypy with explicit list of files to check
mypy llmproxy \
  --ignore-missing-imports \
  --show-error-codes \
  --pretty

echo ""
echo "Type checking complete."
