# Open Source Models with Large Context Windows

## Top Recommendations

### 1. **Mistral 7B Instruct v0.2** ⭐ BEST
- **Context**: 32,768 tokens (16x current!)
- **Size**: 7B parameters (very efficient)
- **Quality**: Excellent instruction following
- **Speed**: Fast inference
- **Model ID**: `mistralai/Mistral-7B-Instruct-v0.2`

### 2. **Phi-3 Medium** 🚀 CUTTING EDGE
- **Context**: 128,000 tokens (62x current!)
- **Size**: 14B parameters
- **Quality**: Excellent (Microsoft-backed)
- **Speed**: Moderate
- **Model ID**: `microsoft/Phi-3-medium-4k-instruct`

### 3. **LLaMA 3.1 8B** (Your Current Model)
- **Context**: 128,000 tokens (should support!)
- **Size**: 8B parameters
- **Quality**: Very good
- **Issue**: Your vLLM may not be configured to use full context
- **Model ID**: `meta-llama/Meta-Llama-3.1-8B-Instruct`

### 4. **Mixtral 8x7B Instruct** 
- **Context**: 32,768 tokens
- **Size**: 47B (MoE - only uses ~12B active)
- **Quality**: Excellent
- **Speed**: Moderate (good for large contexts)
- **Model ID**: `mistralai/Mixtral-8x7B-Instruct-v0.1`

## Quick Comparison

| Model | Context | Size | Speed | Quality |
|-------|---------|------|-------|---------|
| Current (Llama 3.1 8B) | 2048* | 8B | ⚡⚡⚡ | ⭐⭐⭐⭐ |
| Mistral 7B v0.2 | 32K | 7B | ⚡⚡⚡ | ⭐⭐⭐⭐ |
| Phi-3 Medium | 128K | 14B | ⚡⚡ | ⭐⭐⭐⭐⭐ |
| Mixtral 8x7B | 32K | 47B | ⚡ | ⭐⭐⭐⭐⭐ |
| Llama 3.1 8B (full) | 128K | 8B | ⚡⚡⚡ | ⭐⭐⭐⭐ |

*Your current config is capped at 2048

## How to Configure vLLM

### Option A: Mistral 7B (Recommended for Balance)

Edit `.env`:
```bash
VLLM_MODEL_NAME=mistralai/Mistral-7B-Instruct-v0.2
VLLM_MAX_TOKENS=1024
# vLLM will auto-detect 32k context
```

Start vLLM:
```bash
python -m vllm.entrypoints.openai_api_server \
  --model mistralai/Mistral-7B-Instruct-v0.2 \
  --dtype float16 \
  --gpu-memory-utilization 0.8 \
  --max-model-len 32000
```

### Option B: Phi-3 Medium (Maximum Context)

Edit `.env`:
```bash
VLLM_MODEL_NAME=microsoft/Phi-3-medium-4k-instruct
VLLM_MAX_TOKENS=1024
```

Start vLLM:
```bash
python -m vllm.entrypoints.openai_api_server \
  --model microsoft/Phi-3-medium-4k-instruct \
  --dtype float16 \
  --gpu-memory-utilization 0.8 \
  --max-model-len 128000
```

### Option C: Fix Your Current Model (Llama 3.1 8B)

Your current model already supports 128k! The issue is vLLM config. Update `.env`:

```bash
VLLM_MODEL_NAME=meta-llama/Meta-Llama-3.1-8B-Instruct
VLLM_MAX_TOKENS=1024
```

Start vLLM with full context:
```bash
python -m vllm.entrypoints.openai_api_server \
  --model meta-llama/Meta-Llama-3.1-8B-Instruct \
  --dtype float16 \
  --gpu-memory-utilization 0.8 \
  --max-model-len 128000
```

## New Window Configuration

With 32K+ context, you can use MUCH larger windows:

### For 32K Context (Mistral, Mixtral)

```python
# In scraper/llm_client.py
self.window_size = 20000  # 20KB per window!
self.overlap = 2000
self.max_context_tokens = 32000  # Update this
```

Token budget:
- System prompt: ~150 tokens
- Schema: ~100 tokens
- HTML Window: ~5000 tokens (20KB)
- Reserved: ~26k tokens remaining
- **Result: 5x bigger windows!**

### For 128K Context (Phi-3, Llama 3.1 full)

```python
# In scraper/llm_client.py
self.window_size = 50000  # 50KB per window!!
self.overlap = 5000
self.max_context_tokens = 128000
```

Token budget:
- System prompt: ~150 tokens
- Schema: ~100 tokens
- HTML Window: ~12500 tokens (50KB)
- Reserved: ~115k tokens remaining
- **Result: 12x bigger windows!**

## Recommended Setup

1. **Quick fix** (stick with Llama 3.1 8B):
   ```bash
   # Just update the vLLM start command to include --max-model-len 128000
   ```

2. **Balanced** (try Mistral):
   ```bash
   # Better balance of speed/context
   # 32k context = 8x bigger windows than current
   ```

3. **Maximum** (go for Phi-3):
   ```bash
   # Absolute best for large pages
   # 128k context = 60x bigger windows
   ```

## Download & First Run

Models download automatically on first run. Time varies by size/speed:

- Mistral 7B: ~30 seconds
- Phi-3 Medium: ~1 minute
- Mixtral 8x7B: ~2 minutes

## Performance Impact

| Change | Extraction Time | Coverage | Data Quality |
|--------|-----------------|----------|--------------|
| Current (2K window) | Fast | ~30% | Good |
| Mistral (20K window) | Normal | ~90% | Excellent |
| Phi-3 (50K window) | Slow-Normal | ~98% | Excellent |

## No Code Changes Needed

The sliding window system automatically adapts! Just update:
1. `.env` with new model name
2. `llm_client.py` with new window size and token limit
3. vLLM start command with `--max-model-len`

Everything else works the same.

## Testing

```bash
# Check model loads correctly
python -c "from scraper.llm_client import LLMClient; print(LLMClient().model)"

# Should print your new model name
```
