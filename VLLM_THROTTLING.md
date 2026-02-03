# vLLM Server Throttling & Smart Retry Strategy

This system protects your local 5090 GPU from being overwhelmed with requests using multiple complementary strategies.

## 🛡️ Protection Mechanisms

### 1. **Rate Limiter** (Token Bucket Algorithm)
Prevents flooding the vLLM server with too many requests.

- **Max Concurrent**: Only 2 requests in-flight at once (configurable via `VLLM_MAX_CONCURRENT`)
- **Requests Per Minute**: Max 20 requests/minute (~3 second average gap, configurable via `VLLM_REQUESTS_PER_MINUTE`)
- **Smart Queueing**: Workers wait for available tokens before making requests

```python
# Token bucket refills at a steady rate
# Workers automatically wait when bucket is empty
```

### 2. **Circuit Breaker Pattern**
Prevents cascading failures when the vLLM server is overloaded or down.

- **Failure Threshold**: Opens circuit after 5 consecutive failures (configurable)
- **Recovery Timeout**: Waits 60 seconds before attempting recovery
- **States**: 
  - `CLOSED`: Normal operation
  - `OPEN`: Blocking all requests (server likely down/overloaded)
  - `HALF-OPEN`: Testing if server recovered

```python
# Circuit opens automatically on repeated failures
# Prevents "thundering herd" problem
# Gives server time to recover
```

### 3. **Exponential Backoff with Jitter**
Smart retry logic that backs off on transient failures.

- **Base Backoff**: Starts at 1 second
- **Exponential Growth**: Doubles each retry (1s → 2s → 4s → 8s → 16s → 32s)
- **Max Backoff**: Caps at 60 seconds
- **Jitter**: Adds ±25% randomization to prevent synchronized retries
- **Max Retries**: 5 attempts before giving up

**Retryable Errors**:
- Timeout errors
- Rate limit errors (429, "too many requests")
- Server errors (502, 503, 504)
- Connection errors

**Non-Retryable Errors** (fail fast):
- Invalid input (400)
- Authentication errors (401, 403)
- Not found (404)
- JSON parsing errors

### 4. **Queue Management**
Reduced concurrent consumers to avoid queueing too many messages.

- **Concurrent Consumers**: 3 per worker (down from 10)
- **Prefetch Count**: 1 message (down from 3)
- **Total Max Concurrent**: With 4 extraction workers × 3 consumers = 12 consumers max
- **But rate limited to**: Only 2 actual vLLM requests at once

## 📊 Configuration

### Quick Tuning Guide

**For a beefy 5090 (more aggressive)**:
```env
VLLM_MAX_CONCURRENT=4
VLLM_REQUESTS_PER_MINUTE=40
CONCURRENT_CONSUMERS_PER_WORKER=5
```

**For a loaded system (conservative)**:
```env
VLLM_MAX_CONCURRENT=1
VLLM_REQUESTS_PER_MINUTE=10
CONCURRENT_CONSUMERS_PER_WORKER=2
```

**Default (balanced for local 5090)**:
```env
VLLM_MAX_CONCURRENT=2
VLLM_REQUESTS_PER_MINUTE=20
CONCURRENT_CONSUMERS_PER_WORKER=3
PREFETCH_COUNT=1
```

### All vLLM Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `VLLM_MAX_CONCURRENT` | 2 | Max concurrent requests in-flight |
| `VLLM_REQUESTS_PER_MINUTE` | 20 | Max requests per minute (rate limit) |
| `VLLM_MAX_RETRIES` | 5 | Max retry attempts per request |
| `VLLM_BASE_BACKOFF` | 1.0 | Initial backoff delay in seconds |
| `VLLM_MAX_BACKOFF` | 60.0 | Maximum backoff delay in seconds |
| `VLLM_CIRCUIT_BREAKER_THRESHOLD` | 5 | Failures before opening circuit |
| `VLLM_CIRCUIT_BREAKER_TIMEOUT` | 60 | Seconds before attempting recovery |

## 🔍 Monitoring

Check logs for these events:

```json
// Rate limiting in action
{"event": "rate_limit_waiting", "wait_time": 1.5, "tokens": 0.3}

// Retry with backoff
{"event": "llm_request_retry", "attempt": 2, "backoff_seconds": 2.3}

// Circuit breaker opened
{"event": "circuit_breaker_opened", "failures": 5, "threshold": 5}

// Circuit breaker recovery
{"event": "circuit_breaker_half_open", "timeout_elapsed": true}
```

## 🚀 How It Works

### Request Flow

```
Worker wants to make LLM request
    ↓
Check circuit breaker
    ↓ (open? reject immediately)
Acquire rate limit token
    ↓ (wait if no tokens available)
Acquire concurrency semaphore
    ↓ (wait if at max concurrent)
Make request
    ↓
    ├─ Success → record success, release resources
    └─ Failure → check if retryable
           ↓ (retryable)
       Calculate backoff with jitter
           ↓
       Sleep for backoff period
           ↓
       Retry (up to 5 times)
           ↓
       Still failing? → record failure, open circuit breaker
```

### Example Retry Sequence

```
Attempt 1: Immediate          → Timeout
Attempt 2: Wait ~1s + jitter  → Connection Error  
Attempt 3: Wait ~2s + jitter  → Connection Error
Attempt 4: Wait ~4s + jitter  → Connection Error
Attempt 5: Wait ~8s + jitter  → Success! ✓

Total time: ~15 seconds with exponential backoff
Circuit breaker prevented from opening (one success)
```

## 💡 Benefits

1. **No More Flooding**: Rate limiter prevents overwhelming GPU
2. **Graceful Degradation**: Circuit breaker stops cascading failures
3. **Smart Retries**: Exponential backoff handles transient issues
4. **Jitter Prevents Stampedes**: Randomization prevents synchronized retries
5. **Fast Failure**: Non-retryable errors fail immediately
6. **Self-Recovery**: Circuit breaker automatically tests recovery

## 🎯 Performance Impact

**Before (no throttling)**:
- 40+ concurrent requests queued
- GPU OOM errors
- Workers crashing
- Tasks lost

**After (with throttling)**:
- Max 2 concurrent requests
- Smooth GPU utilization
- Graceful handling of overload
- All tasks eventually processed
- No cascading elephants 🐘

## 🔧 Troubleshooting

**Circuit breaker keeps opening?**
- vLLM server might be overloaded
- Check `nvidia-smi` for GPU usage
- Reduce `VLLM_MAX_CONCURRENT` or `VLLM_REQUESTS_PER_MINUTE`
- Check vLLM server logs

**Too slow?**
- Increase `VLLM_MAX_CONCURRENT` (try 3-4)
- Increase `VLLM_REQUESTS_PER_MINUTE` (try 30-40)
- Reduce `VLLM_BASE_BACKOFF` (try 0.5)

**Still getting timeouts?**
- Check vLLM server is running: `curl http://localhost:8000/v1/models`
- Increase `VLLM_MAX_RETRIES`
- Increase `VLLM_MAX_BACKOFF`
- Check network latency to vLLM server

**Logs show "rate_limit_waiting" constantly?**
- This is normal! It means protection is working
- Workers are queueing up politely instead of flooding
- Increase `VLLM_REQUESTS_PER_MINUTE` if you want faster processing
