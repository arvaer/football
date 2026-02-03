# vLLM Throttling - Quick Reference Card

## 🎯 Quick Tuning Presets

### Conservative (Low-End GPU / Shared System)
```env
VLLM_MAX_CONCURRENT=1
VLLM_REQUESTS_PER_MINUTE=10
CONCURRENT_CONSUMERS_PER_WORKER=2
PREFETCH_COUNT=1
```
- 1 request at a time
- 6 second average gap between requests
- Safest for resource-constrained systems

### Balanced (Default - RTX 5090 Local)
```env
VLLM_MAX_CONCURRENT=2
VLLM_REQUESTS_PER_MINUTE=20
CONCURRENT_CONSUMERS_PER_WORKER=3
PREFETCH_COUNT=1
```
- 2 requests at a time
- 3 second average gap between requests
- Good balance of speed and safety

### Aggressive (Dedicated GPU / No Other Load)
```env
VLLM_MAX_CONCURRENT=4
VLLM_REQUESTS_PER_MINUTE=40
CONCURRENT_CONSUMERS_PER_WORKER=5
PREFETCH_COUNT=2
```
- 4 requests at a time
- 1.5 second average gap between requests
- Maximum throughput

## 🔧 Common Adjustments

### GPU Running Hot?
```env
VLLM_MAX_CONCURRENT=1           # Reduce concurrent
VLLM_REQUESTS_PER_MINUTE=15     # Slow down rate
```

### Processing Too Slow?
```env
VLLM_MAX_CONCURRENT=3           # More concurrent
VLLM_REQUESTS_PER_MINUTE=30     # Faster rate
CONCURRENT_CONSUMERS_PER_WORKER=4  # More consumers
```

### Too Many Retries?
```env
VLLM_MAX_RETRIES=8              # More attempts
VLLM_MAX_BACKOFF=120.0          # Longer max backoff
VLLM_BASE_BACKOFF=2.0           # Slower initial retry
```

### Circuit Breaker Opening Too Much?
```env
VLLM_CIRCUIT_BREAKER_THRESHOLD=10   # More tolerance
VLLM_CIRCUIT_BREAKER_TIMEOUT=120    # Longer recovery
```

## 📊 Monitoring Commands

### Watch Live Throttling
```bash
python -m scraper.main 2>&1 | python scripts/monitor_throttling.py
```

### Test Throttling Config
```bash
python scripts/test_throttling.py
```

### Check vLLM Server
```bash
curl http://localhost:8000/v1/models
```

### Watch GPU Usage
```bash
watch -n 1 nvidia-smi
```

### RabbitMQ Queue Status
```bash
# Web UI
firefox http://localhost:15672

# Or CLI
./scripts/check_status.sh
```

## 🚨 Troubleshooting

| Problem | Likely Cause | Solution |
|---------|-------------|----------|
| Circuit breaker keeps opening | vLLM overloaded | Reduce `MAX_CONCURRENT` and `REQUESTS_PER_MINUTE` |
| GPU OOM errors | Too many concurrent | Set `MAX_CONCURRENT=1` |
| Very slow processing | Too conservative | Increase `REQUESTS_PER_MINUTE` |
| Constant timeouts | vLLM not responding | Check vLLM server logs, increase `MAX_BACKOFF` |
| "rate_limit_waiting" spam | High queue backlog | Normal! Workers waiting politely |
| Retries exhausted | Network/server issues | Increase `MAX_RETRIES`, check connection |

## 📐 Math Reference

### Requests Per Minute → Gap Between Requests
- RPM=60 → 1.0s gap
- RPM=30 → 2.0s gap
- RPM=20 → 3.0s gap (default)
- RPM=15 → 4.0s gap
- RPM=10 → 6.0s gap

### Backoff Progression (base=1.0s)
- Attempt 1: ~1s
- Attempt 2: ~2s
- Attempt 3: ~4s
- Attempt 4: ~8s
- Attempt 5: ~16s
- Attempt 6+: ~32s (capped at MAX_BACKOFF=60s)

### Total Workers × Consumers
```
EXTRACTION_WORKERS=4
CONCURRENT_CONSUMERS_PER_WORKER=3
Total consumers = 4 × 3 = 12

But only MAX_CONCURRENT=2 actually hit vLLM at once!
The other 10 wait in queue (this is good!)
```

## 🎓 Key Concepts

**Rate Limiter**: Controls how fast requests are made (requests/minute)
**Concurrency Limit**: Controls how many requests happen at once  
**Circuit Breaker**: Stops all requests when server is failing  
**Backoff**: Wait time between retry attempts (grows exponentially)  
**Jitter**: Random variation to prevent synchronized retries

## 📝 Config File Locations

```
.env                    # Your config (copy from .env.example)
.env.example            # Template with defaults
VLLM_THROTTLING.md      # Full documentation
ARCHITECTURE.txt        # Visual diagrams
```

## ✅ Quick Health Check

```bash
# 1. Is vLLM running?
curl http://localhost:8000/v1/models

# 2. Is RabbitMQ running?
curl -u guest:guest http://localhost:15672/api/overview

# 3. Test throttling
python scripts/test_throttling.py

# 4. Check current config
python -c "from scraper.config import settings; \
  print(f'Concurrent: {settings.vllm.max_concurrent_requests}'); \
  print(f'RPM: {settings.vllm.requests_per_minute}'); \
  print(f'Retries: {settings.vllm.max_retries}')"
```

---

**Remember**: Start conservative and tune up! Better to be slow than to crash. 🐢 > 💥
