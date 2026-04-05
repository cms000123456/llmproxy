#!/bin/bash
# Setup script for local LLM models with Ollama
# This script helps you download and configure the best coding models

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if Ollama is installed
if ! command -v ollama &> /dev/null; then
    echo -e "${RED}Ollama not found!${NC}"
    echo "Please install Ollama first:"
    echo "  curl -fsSL https://ollama.com/install.sh | sh"
    echo ""
    echo "Or visit: https://ollama.com/download"
    exit 1
fi

echo -e "${GREEN}✓ Ollama is installed${NC}"

# Check if Ollama is running
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo -e "${YELLOW}⚠ Ollama is not running${NC}"
    echo "Starting Ollama..."
    ollama serve &
    sleep 3
    
    if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
        echo -e "${RED}Failed to start Ollama${NC}"
        echo "Please start it manually: ollama serve"
        exit 1
    fi
fi

echo -e "${GREEN}✓ Ollama is running${NC}"
echo ""

# Function to check VRAM
get_vram_gb() {
    if command -v nvidia-smi &> /dev/null; then
        nvidia-smi --query-gpu=memory.total --format=csv,noheader,nounits | head -1 | awk '{print int($1/1024)}'
    else
        echo "0"
    fi
}

VRAM_GB=$(get_vram_gb)

if [ "$VRAM_GB" -gt 0 ]; then
    echo -e "${BLUE}Detected GPU with ${VRAM_GB}GB VRAM${NC}"
else
    echo -e "${YELLOW}No GPU detected - will use CPU (slower)${NC}"
fi
echo ""

# Model recommendations based on VRAM
echo "========================================="
echo "Recommended Models for Coding (2025)"
echo "========================================="
echo ""

MODELS_LIST=(
    "qwen2.5-coder:7b|Fast coding assistant|8|★ Best for laptops, quick tasks"
    "qwen2.5-coder:14b|Balanced quality & speed|16|★ Best overall choice"
    "qwen2.5-coder:32b|Premium coding model|32|Excellent for complex projects"
    "deepseek-coder:6.7b|Algorithm specialist|8|Great for math/algorithms"
    "codellama:7b|Reliable all-rounder|8|Meta's code model"
    "codellama:13b|Strong performer|16|Good balance"
    "llama3.3:latest|General purpose|24|Latest Llama for code+chat"
)

echo "Model                        | VRAM  | Description"
echo "-----------------------------|-------|----------------------------------------"
for model_info in "${MODELS_LIST[@]}"; do
    IFS='|' read -r model desc vram note <<< "$model_info"
    printf "%-28s | %4sG | %s\n" "$model" "$vram" "$desc"
done

echo ""
echo "Your hardware: ${VRAM_GB}GB VRAM"
echo ""

# Auto-recommend models
RECOMMENDED=()

if [ "$VRAM_GB" -ge 32 ] || [ "$VRAM_GB" -eq 0 ]; then
    # 0 means CPU mode - can run any but slower
    RECOMMENDED+=("qwen2.5-coder:14b")
    RECOMMENDED+=("deepseek-coder:6.7b")
    [ "$VRAM_GB" -ge 32 ] && RECOMMENDED+=("qwen2.5-coder:32b")
elif [ "$VRAM_GB" -ge 16 ]; then
    RECOMMENDED+=("qwen2.5-coder:14b")
    RECOMMENDED+=("deepseek-coder:6.7b")
    RECOMMENDED+=("codellama:13b")
elif [ "$VRAM_GB" -ge 8 ]; then
    RECOMMENDED+=("qwen2.5-coder:7b")
    RECOMMENDED+=("deepseek-coder:6.7b")
    RECOMMENDED+=("codellama:7b")
else
    RECOMMENDED+=("qwen2.5-coder:7b")
    echo -e "${YELLOW}Warning: Limited VRAM. Models will be slow on CPU.${NC}"
fi

echo "Recommended for your setup:"
for model in "${RECOMMENDED[@]}"; do
    echo "  - $model"
done
echo ""

# Ask user what to install
INSTALL_ALL=false
if [ "$1" == "--all" ]; then
    INSTALL_ALL=true
fi

pull_model() {
    local model=$1
    echo -e "${BLUE}Pulling $model...${NC}"
    if ollama pull "$model"; then
        echo -e "${GREEN}✓ $model installed${NC}"
        return 0
    else
        echo -e "${RED}✗ Failed to pull $model${NC}"
        return 1
    fi
}

if [ "$INSTALL_ALL" = true ]; then
    echo "Installing all recommended models..."
    for model in "${RECOMMENDED[@]}"; do
        pull_model "$model"
    done
else
    echo "Select models to install:"
    select model in "${RECOMMENDED[@]}" "All recommended" "Skip"; do
        case $model in
            "All recommended")
                for m in "${RECOMMENDED[@]}"; do
                    pull_model "$m"
                done
                break
                ;;
            "Skip")
                echo "Skipping model installation"
                break
                ;;
            *)
                if [ -n "$model" ]; then
                    pull_model "$model"
                fi
                break
                ;;
        esac
    done
fi

echo ""
echo "========================================="
echo "Installed models:"
ollama list
echo ""

# Configuration advice
echo "========================================="
echo "Configuration"
echo "========================================="
echo ""
echo "To use local models, add to your .env file:"
echo ""
echo -e "${GREEN}# Enable local mode (no upstream API needed)"
echo "LLM_PROXY_LOCAL_MODE=true"
echo "LLM_PROXY_LOCAL_MODEL=qwen2.5-coder:14b"
echo ""
echo "# Optional: configure Ollama URL"
echo "LLM_PROXY_OLLAMA_BASE_URL=http://localhost:11434"
echo ""
echo "# Disable auth for local use"
echo "LLM_PROXY_AUTH_ENABLED=false${NC}"
echo ""

echo "Then start the proxy:"
echo "  ./llmproxy.sh proxy"
echo ""

echo "Test with:"
echo "  curl http://localhost:8080/v1/models"
echo ""

echo "Use with the agent:"
echo "  ./llmproxy.sh agent --model local-coder"
echo ""

echo "Model aliases available:"
echo "  local-coder        -> qwen2.5-coder:14b"
echo "  local-coder-small  -> qwen2.5-coder:7b"
echo "  local-coder-large  -> qwen2.5-coder:32b"
echo "  local-deepseek     -> deepseek-coder:6.7b"
echo "  local-codellama    -> codellama:13b"
echo "  local              -> llama3.3:latest"
echo ""

echo -e "${GREEN}Setup complete!${NC}"
