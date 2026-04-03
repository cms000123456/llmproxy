#!/usr/bin/env bash
# Convenience wrapper for LLM Proxy
# Usage: ./llmproxy.sh [proxy|agent|run|bench|bench-local|test|help]

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_PYTHON="${SCRIPT_DIR}/.venv/bin/python"
ENV_FILE="${SCRIPT_DIR}/.env"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

usage() {
    cat <<EOF
LLM Proxy wrapper

Usage:
  ./llmproxy.sh proxy                    Start the proxy server
  ./llmproxy.sh agent                    Start the interactive coding agent CLI
  ./llmproxy.sh agent --resume           Resume a previous session
  ./llmproxy.sh agent --list             List saved sessions for this project
  ./llmproxy.sh run "..."                Run a one-shot agent prompt
  ./llmproxy.sh bench                    Run live benchmark against the proxy
  ./llmproxy.sh bench-local              Run local token-savings benchmark
  ./llmproxy.sh test                     Run unit tests
  ./llmproxy.sh help                     Show this message

Agent options (pass after 'agent'):
  -r, --resume       Resume a previous session (interactive selection)
  -s, --session-id   Resume a specific session by ID
  -l, --list         List saved sessions for current project

Examples:
  ./llmproxy.sh agent --resume
  ./llmproxy.sh agent --list
  ./llmproxy.sh run "Explain this codebase"
EOF
}

ensure_venv() {
    if [[ ! -x "$VENV_PYTHON" ]]; then
        echo "Error: virtual environment not found at ${SCRIPT_DIR}/.venv"
        echo "Run: uv venv && uv pip install -r requirements.txt"
        exit 1
    fi
}

load_env() {
    if [[ -f "$ENV_FILE" ]]; then
        set -a
        # shellcheck source=/dev/null
        source "$ENV_FILE"
        set +a
    fi
}

# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

CMD="${1:-help}"

case "$CMD" in
    proxy|server)
        ensure_venv
        load_env
        echo "Starting LLM Proxy on ${LLM_PROXY_HOST:-0.0.0.0}:${LLM_PROXY_PORT:-8080}..."
        exec "$VENV_PYTHON" "${SCRIPT_DIR}/main.py"
        ;;

    agent|cli)
        ensure_venv
        load_env
        shift  # Remove 'agent' from args
        exec "$VENV_PYTHON" "${SCRIPT_DIR}/agent.py" "$@"
        ;;

    run|prompt)
        if [[ $# -lt 2 ]]; then
            echo "Usage: ./llmproxy.sh run \"Your prompt here\""
            exit 1
        fi
        ensure_venv
        load_env
        shift
        exec "$VENV_PYTHON" "${SCRIPT_DIR}/agent.py" "$@"
        ;;

    bench|benchmark)
        ensure_venv
        load_env
        PROXY_URL="${2:-http://localhost:8080}"
        echo "Running live benchmark against ${PROXY_URL}..."
        exec "$VENV_PYTHON" "${SCRIPT_DIR}/benchmark.py" "$PROXY_URL"
        ;;

    bench-local|local-benchmark)
        ensure_venv
        echo "Running local token-savings benchmark..."
        exec "$VENV_PYTHON" "${SCRIPT_DIR}/benchmark_local.py"
        ;;

    test|tests)
        ensure_venv
        exec "$VENV_PYTHON" "${SCRIPT_DIR}/test_proxy.py"
        ;;

    help|--help|-h|*)
        usage
        exit 0
        ;;
esac
