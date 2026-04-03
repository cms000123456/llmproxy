# LLM Proxy - How-To Guide

A practical guide for using the LLM Proxy and Coding Agent CLI.

## Table of Contents

- [Quick Start](#quick-start)
- [Installation](#installation)
- [Running the Proxy](#running-the-proxy)
- [Using the Coding Agent](#using-the-coding-agent)
- [Project Workflow](#project-workflow)
- [Session Management](#session-management)
- [Environment Setup](#environment-setup)
- [Docker Deployment](#docker-deployment)
- [Troubleshooting](#troubleshooting)

---

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd llmproxy
source .venv/bin/activate

# 2. Configure your API key
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# 3. Start the proxy
./llmproxy.sh proxy

# 4. In another terminal, use the agent
cd ~/projects/my-project
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
```

---

## Installation

### Prerequisites

- Python 3.11+
- (Optional) Docker & Docker Compose
- (Optional) NVIDIA GPU for Ollama local models

### Local Installation

```bash
# Create virtual environment
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Verify Installation

```bash
./llmproxy.sh test        # Run unit tests
./llmproxy.sh bench-local # Run local benchmark
```

---

## Running the Proxy

### Option 1: Local (Development)

```bash
# Set required environment variables
export LLM_PROXY_UPSTREAM_BASE_URL="https://api.moonshot.cn/v1"
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# Start the proxy
./llmproxy.sh proxy

# Proxy is now running at http://localhost:8080
```

### Option 2: Docker (Production)

```bash
# Ensure Docker has GPU support (for Ollama)
docker compose up -d

# Pull a local model for compression
docker exec ollama ollama pull llama3.2

# Check status
curl http://localhost:8080/health
```

### Verify Proxy is Running

```bash
curl http://localhost:8080/health
# Expected: {"status":"ok"}

curl http://localhost:8080/metrics
# Shows usage metrics and cache stats
```

---

## Using the Coding Agent

### Start Interactive Mode

```bash
# Navigate to your project directory
cd ~/projects/my-awesome-project

# Start the agent (creates new session automatically)
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
```

### What You'll See

```
╭──────────────────── Welcome ─────────────────────╮
│ Coding Agent                                     │
│ Model: kimi-for-coding                           │
│ Base URL: http://localhost:8080/v1               │
│ Workspace: /home/cms/projects/my-awesome-project │
│ Session: 20250403_143022_a1b2c3d4...            │
│ Tokens: 0 (↑0 ↓0) | Est. cost: $0.0000          │
╰──────────────────────────────────────────────────╯
You: 
```

### Example Commands

```
You: Create a Python FastAPI app with user authentication
You: Read the main.py file and explain what it does
You: Find all TODO comments in this codebase
You: Run pytest and fix any failing tests
You: Create a Dockerfile for this project
```

### One-Shot Mode (Non-Interactive)

```bash
# Run a single command without entering interactive mode
./llmproxy.sh run "Create a README.md for this project"

# With custom model
./llmproxy.sh run -m gpt-4 "Refactor this code to use async/await"
```

---

## Project Workflow

### 1. Create New Project

```bash
# Create project directory
mkdir ~/projects/my-new-api
cd ~/projects/my-new-api

# Start coding with AI assistant
/media/cms/data/repositories/llmproxy/llmproxy.sh agent

# Ask the agent to scaffold the project
You: Create a FastAPI project structure with tests folder
```

### 2. Work on Existing Project

```bash
cd ~/projects/existing-project

# List previous sessions
/media/cms/data/repositories/llmproxy/llmproxy.sh agent --list

# Resume where you left off
/media/cms/data/repositories/llmproxy/llmproxy.sh agent --resume
```

### 3. Switch Between Projects

Sessions are **completely isolated** by directory:

```bash
# Project A - Web API
cd ~/projects/web-api
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
# → New session for web-api

# Project B - Data Pipeline  
cd ~/projects/data-pipeline
/media/cms/data/repositories/llmproxy/llmproxy.sh agent
# → New session for data-pipeline (separate context!)
```

---

## Session Management

### List Saved Sessions

```bash
./llmproxy.sh agent --list

# Output:
# ┏━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━┓
# ┃ Session ID          ┃ Created        ┃ Updated        ┃ Tokens  ┃
# ┡━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━┩
# │ 20250403_143022_... │ 2025-04-03 14:30│ 2025-04-03 15:45│ 12,453  │
# │ 20250403_101511_... │ 2025-04-03 10:15│ 2025-04-03 10:45│ 3,210   │
# └─────────────────────┴────────────────┴────────────────┴─────────┘
```

### Resume Previous Session

```bash
# Interactive selection
./llmproxy.sh agent --resume

# Resume specific session by ID
./llmproxy.sh agent --session-id 20250403_143022_a1b2c3d4
```

### How Sessions Work

- **Location**: `~/.local/share/llmproxy/conversations/`
- **Per-project**: Each directory has isolated sessions
- **Auto-saved**: Every message is saved automatically
- **Persistent**: Survive system restarts
- **Not in git**: Stored outside your project directory

---

## Environment Setup

### Required Variables

```bash
# API Configuration (required)
export LLM_PROXY_UPSTREAM_BASE_URL="https://api.moonshot.cn/v1"
export LLM_PROXY_UPSTREAM_API_KEY="your-api-key"

# Proxy Settings (optional)
export LLM_PROXY_HOST="0.0.0.0"
export LLM_PROXY_PORT="8080"

# Agent Settings (optional)
export LLM_PROXY_MODEL="kimi-for-coding"
export LLM_PROXY_BASE_URL="http://localhost:8080/v1"
```

### Using .env File

```bash
# Copy template
cp .env-example .env

# Edit with your keys
nano .env

# Load environment
export $(grep -v '^#' .env | xargs)
```

---

## Docker Deployment

### Full Stack (Proxy + Ollama with GPU)

```bash
# Start services
docker compose up -d

# Verify
docker ps

# View logs
docker logs llmproxy
docker logs ollama

# Pull local model
docker exec ollama ollama pull llama3.2

# Stop
docker compose down
```

### Verify GPU is Used

```bash
docker logs ollama | grep -i "cuda\|gpu"
# Should show: "CUDA0 model buffer size = ..."
```

---

## Troubleshooting

### Agent Can't Connect

```bash
# Check proxy is running
curl http://localhost:8080/health

# If not running:
./llmproxy.sh proxy
```

### API Key Errors

```bash
# Verify key is set
echo $LLM_PROXY_UPSTREAM_API_KEY

# Set it if empty
export LLM_PROXY_UPSTREAM_API_KEY="your-key-here"
```

### Port Already in Use

```bash
# Find what's using port 8080
sudo lsof -i :8080

# Kill it or change port in .env
export LLM_PROXY_PORT=8081
```

### Session Not Found

```bash
# List all sessions for current directory
./llmproxy.sh agent --list

# Check session storage location
ls ~/.local/share/llmproxy/conversations/
```

### Out of Memory (Ollama)

```bash
# Check GPU memory
nvidia-smi

# Use smaller model
docker exec ollama ollama pull llama3.2:1b
```

---

## Pro Tips

### Add Alias to Shell

Add to `~/.bashrc` or `~/.zshrc`:

```bash
alias agent='/media/cms/data/repositories/llmproxy/llmproxy.sh agent'
alias agent-run='/media/cms/data/repositories/llmproxy/llmproxy.sh run'
alias agent-list='/media/cms/data/repositories/llmproxy/llmproxy.sh agent --list'
```

Then use:
```bash
cd ~/projects/my-app
agent          # Start interactive mode
agent-list     # Show sessions
```

### Best Practices

1. **One project per directory** - Sessions are isolated by path
2. **Resume long tasks** - Use `--resume` to continue multi-step work
3. **Check usage** - Token costs are displayed after each response
4. **Save frequently** - Sessions auto-save, but complex tasks benefit from explicit saves
5. **Use specific prompts** - "Create a FastAPI app" vs "Build a web server"

---

## Example Workflows

### Web API Project

```bash
mkdir ~/projects/task-api && cd ~/projects/task-api
agent

# Then:
# You: Create a FastAPI app for a task management API
# You: Add CRUD endpoints for tasks
# You: Add tests for all endpoints
# You: Create a Dockerfile
```

### Data Analysis

```bash
mkdir ~/projects/data-analysis && cd ~/projects/data-analysis
agent

# Then:
# You: Load data.csv and show the first 5 rows
# You: Create visualizations for the sales data
# You: Train a simple prediction model
```

### Bug Fixing

```bash
cd ~/projects/existing-project
agent --resume  # Continue from previous session

# Then:
# You: The tests are failing, investigate and fix
```

---

## Support

- **Issues**: Check logs with `docker logs llmproxy` or `./llmproxy.sh proxy` output
- **Metrics**: Visit http://localhost:8080/metrics
- **Health**: Check http://localhost:8080/health
