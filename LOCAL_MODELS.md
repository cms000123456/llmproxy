# Local LLM Mode - Offline Coding

Run LLM Proxy entirely offline using local models via [Ollama](https://ollama.com). No API keys, no internet required, complete privacy.

## Quick Start

```bash
# 1. Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# 2. Run setup script (detects your hardware, recommends models)
./scripts/setup-local-models.sh

# 3. Configure local mode
cat > .env << 'EOF'
LLM_PROXY_LOCAL_MODE=true
LLM_PROXY_LOCAL_MODEL=qwen2.5-coder:14b
LLM_PROXY_AUTH_ENABLED=false
EOF

# 4. Start proxy
./llmproxy.sh proxy

# 5. Test
curl http://localhost:8080/v1/models
curl http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "local-coder", "messages": [{"role": "user", "content": "Hello!"}]}'
```

## Best Local Coding Models (2025)

| Model | Size | VRAM | Speed | Best For |
|-------|------|------|-------|----------|
| **qwen2.5-coder:14b** | 14B | 16GB | Fast | ★ **Best overall** - balanced quality & speed |
| **qwen2.5-coder:7b** | 7B | 8GB | Very Fast | Laptops, quick tasks, documentation |
| **qwen2.5-coder:32b** | 32B | 32GB | Medium | Complex projects, architecture |
| **deepseek-coder:6.7b** | 6.7B | 8GB | Fast | Algorithms, math, problem-solving |
| **deepseek-coder:33b** | 33B | 48GB | Slow | Complex algorithms, research |
| **codellama:13b** | 13B | 16GB | Fast | Reliable all-rounder from Meta |
| **codellama:7b** | 7B | 8GB | Very Fast | Entry-level, simple tasks |
| **llama3.3:latest** | 70B | 64GB | Slow | General purpose + coding |

### Model Aliases

Use convenient aliases instead of full model names:

| Alias | Resolves To | Use Case |
|-------|-------------|----------|
| `local-coder` | qwen2.5-coder:14b | Default coding model |
| `local-coder-small` | qwen2.5-coder:7b | Fast, low VRAM |
| `local-coder-large` | qwen2.5-coder:32b | Maximum quality |
| `local-deepseek` | deepseek-coder:6.7b | Algorithms |
| `local-codellama` | codellama:13b | Meta's code model |
| `local` | llama3.3:latest | General purpose |

## Hardware Requirements

### Minimum (CPU only)
- 16GB RAM
- Any modern CPU
- Expect 5-10 tokens/sec

### Recommended (GPU)
- NVIDIA GPU with 16GB+ VRAM (RTX 4060 Ti, 4070, etc.)
- 32GB RAM
- 50+ tokens/sec

### Optimal (High-end)
- NVIDIA GPU with 32GB+ VRAM (RTX 4090, A100, etc.)
- 64GB+ RAM
- 100+ tokens/sec

## Configuration

### Environment Variables

```bash
# Enable local-only mode
LLM_PROXY_LOCAL_MODE=true

# Default model for requests without explicit model
LLM_PROXY_LOCAL_MODEL=qwen2.5-coder:14b

# Ollama server URL (default: http://localhost:11434)
LLM_PROXY_OLLAMA_BASE_URL=http://localhost:11434

# Optional: API key if Ollama is behind auth
LLM_PROXY_OLLAMA_API_KEY=

# Disable auth for pure local use
LLM_PROXY_AUTH_ENABLED=false
```

### Using with the Coding Agent

```bash
# Use default local model
./llmproxy.sh agent --model local-coder

# Use specific model
./llmproxy.sh agent --model qwen2.5-coder:7b

# Or set in environment
export LLM_PROXY_MODEL=local-coder
./llmproxy.sh agent
```

### Using with OpenAI Client

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="local"  # any string works if auth disabled
)

# Use alias
response = client.chat.completions.create(
    model="local-coder",
    messages=[{"role": "user", "content": "Write a Python function to..."}]
)

# Or full model name
response = client.chat.completions.create(
    model="qwen2.5-coder:14b",
    messages=[...]
)
```

## Managing Models

### Pull Models

```bash
# Pull a model
ollama pull qwen2.5-coder:14b

# Pull multiple
ollama pull qwen2.5-coder:7b qwen2.5-coder:14b deepseek-coder:6.7b
```

### List Installed

```bash
ollama list
# or via API
curl http://localhost:8080/v1/models
```

### Remove Models

```bash
ollama rm qwen2.5-coder:14b
```

## Performance Tips

### 1. Use Quantized Models

Ollama automatically uses quantized versions. Smaller quant = faster:
- `qwen2.5-coder:14b-q4_0` - Fastest, slight quality loss
- `qwen2.5-coder:14b-q5_0` - Balanced
- `qwen2.5-coder:14b-q8_0` - Best quality

### 2. GPU Offloading

Ollama automatically uses GPU. Check with:
```bash
ollama ps  # Shows which models are loaded and on GPU
```

### 3. Keep Models Loaded

First request loads the model into VRAM. Keep it loaded:
```bash
# In another terminal, keep model warm
ollama run qwen2.5-coder:14b
```

### 4. Context Window

Default context is usually 2048-4096 tokens. For larger codebases:
```python
# In your request
response = client.chat.completions.create(
    model="local-coder",
    messages=[...],
    max_tokens=4000,  # Response tokens
    # Ollama handles context automatically
)
```

## Comparison: Local vs Cloud

| Aspect | Local (Ollama) | Cloud (OpenAI/Moonshot) |
|--------|---------------|------------------------|
| **Cost** | Free (electricity only) | $0.002-0.03 per 1K tokens |
| **Privacy** | Complete | Sent to provider |
| **Speed** | Depends on GPU | Fast |
| **Quality** | Good (7B-32B) | Excellent (GPT-4 class) |
| **Offline** | ✅ Yes | ❌ No |
| **Rate limits** | None | Yes |
| **Setup** | Requires GPU for speed | Zero setup |

## Troubleshooting

### "Cannot connect to Ollama"

```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

### "Model not found"

```bash
# Pull the model first
ollama pull qwen2.5-coder:14b

# Verify it's available
ollama list
```

### "Out of memory"

- Use smaller model (7B instead of 14B)
- Close other GPU applications
- Use CPU mode (slower but works): `OLLAMA_GPU_OVERHEAD=1GB ollama serve`

### Slow responses

- Ensure GPU is being used: `nvidia-smi` during inference
- Use smaller quantized model
- Reduce context window in requests

### "CUDA out of memory"

```bash
# Force Ollama to use less VRAM
export OLLAMA_GPU_OVERHEAD=2GB
ollama serve
```

## Hybrid Mode (Coming Soon)

Route different requests to different providers:
- Simple tasks → Local model
- Complex reasoning → Cloud API
- Automatic fallback

## Resources

- [Ollama Models](https://ollama.com/library)
- [Qwen2.5-Coder](https://github.com/QwenLM/Qwen2.5-Coder)
- [DeepSeek Coder](https://github.com/deepseek-ai/DeepSeek-Coder)
- [CodeLlama](https://github.com/facebookresearch/codellama)
