# vLLM Throttling Implementation Summary

## What Changed

Your scraper now has intelligent throttling to protect your local RTX 5090 from being overwhelmed with LLM requests.

## Key Features Added

### 1. **Rate Limiter** (`llm_client.py`)
- Token bucket algorithm
- Max 2 concurrent requests at any time
- Max 20 requests per minute (~3 second average gap)
- Workers wait politely when limit is reached

### 2. **Circuit Breaker** (`llm_client.py`)
- Detects when vLLM server is failing
- Opens circuit after 5 consecutive failures
- Blocks all requests for 60 seconds to allow recovery
- Auto-tests recovery and closes when server is healthy
- **Prevents cascading failures** (no elephants! 🐘)

### 3. **Exponential Backoff with Jitter** (`llm_client.py`)
- Smart retry on transient errors (timeouts, rate limits, 5xx errors)
- Starts at 1 second, doubles each retry (1s → 2s → 4s → 8s → 16s)
- Adds ±25% random jitter to prevent synchronized retries
- Max 5 retries before giving up
- Fast-fails on non-retryable errors (4xx, JSON parse errors)

### 4. **Reduced Concurrency** (`config.py`)
- Concurrent consumers per worker: 10 → 3
- Prefetch count: 3 → 1
- Prevents queueing too many messages in-memory

## Files Modified

1. **`scraper/config.py`**
   - Added vLLM throttling settings (8 new config options)
   - Reduced default worker concurrency

2. **`scraper/llm_client.py`**
   - Added `CircuitBreaker` class
   - Added `RateLimiter` class  
   - Added `LLMClient._execute_with_backoff()` method
   - Wrapped all LLM calls with throttling logic

3. **`.env.example`**
   - Documented all new throttling settings

## Files Created

1. **`VLLM_THROTTLING.md`** - Comprehensive documentation
2. **`THROTTLING_CHEATSHEET.md`** - Quick reference guide
3. **`ARCHITECTURE.txt`** - Visual diagrams
4. **`scripts/monitor_throttling.py`** - Live monitoring tool
5. **`scripts/test_throttling.py`** - Test script

## How to Use

### Basic Usage (No Changes Required)
```bash
# Just run as normal - throttling is automatic!
python -m scraper.main
```

### Monitor Throttling in Action
```bash
python -m scraper.main 2>&1 | python scripts/monitor_throttling.py
```

### Test Configuration
```bash
python scripts/test_throttling.py
```

### Tune for Your System
Edit `.env`:
```env
# Conservative (if GPU struggles)
VLLM_MAX_CONCURRENT=1
VLLM_REQUESTS_PER_MINUTE=10

# Default (balanced)
VLLM_MAX_CONCURRENT=2
VLLM_REQUESTS_PER_MINUTE=20

# Aggressive (if GPU can handle more)
VLLM_MAX_CONCURRENT=4
VLLM_REQUESTS_PER_MINUTE=40
```

## Before vs After

### Before (No Throttling)
```
❌ 40+ concurrent requests hitting vLLM
❌ GPU OOM errors
❌ Workers crashing
❌ Tasks lost
❌ Cascading failures
```

### After (With Throttling)
```
✅ Max 2 concurrent requests
✅ Smooth GPU utilization
✅ Graceful handling of overload
✅ All tasks eventually processed
✅ Self-recovery from failures
✅ No cascading elephants! 🐘
```

## Default Settings

| Setting | Value | Meaning |
|---------|-------|---------|
| `VLLM_MAX_CONCURRENT` | 2 | Max 2 requests in-flight |
| `VLLM_REQUESTS_PER_MINUTE` | 20 | ~3 second avg gap |
| `VLLM_MAX_RETRIES` | 5 | 5 retry attempts |
| `VLLM_BASE_BACKOFF` | 1.0s | Initial retry delay |
| `VLLM_MAX_BACKOFF` | 60s | Max retry delay |
| `VLLM_CIRCUIT_BREAKER_THRESHOLD` | 5 | Open after 5 fails |
| `VLLM_CIRCUIT_BREAKER_TIMEOUT` | 60s | Recovery timeout |
| `CONCURRENT_CONSUMERS_PER_WORKER` | 3 | Down from 10 |
| `PREFETCH_COUNT` | 1 | Down from 3 |

## What to Expect

### Normal Operation
- You'll see `rate_limit_waiting` logs occasionally (this is good!)
- Requests will be spaced out smoothly
- GPU usage will be steady instead of spikey
- No more OOM crashes

### Under Heavy Load
- Workers queue up politely
- Rate limiter ensures smooth flow
- Circuit breaker protects from server failures
- Backoff handles transient issues

### When vLLM Server Has Issues
- Circuit breaker opens automatically
- Requests blocked for 60 seconds
- Auto-tests recovery
- Returns to normal when server recovers

## Troubleshooting

See `THROTTLING_CHEATSHEET.md` for:
- Common issues and solutions
- Tuning presets
- Monitoring commands
- Health check procedures

## Next Steps

1. **Test It**: Run `python scripts/test_throttling.py`
2. **Monitor It**: Use `monitor_throttling.py` to watch it work
3. **Tune It**: Adjust settings in `.env` based on your GPU
4. **Read More**: Check `VLLM_THROTTLING.md` for deep dive

---

**No more flooding your 5090! Your scraper now plays nice with your GPU. 🎉**
