# Quick Start Guide

## 1-Minute Setup

```bash
# 1. Install dependencies (if not done)
make install

# 2. Check system status
make status

# 3. Start RabbitMQ (in terminal 1)
make rabbitmq

# 4. Start vLLM (in terminal 2) - REQUIRES GPU
make vllm

# 5. Run scraper (in terminal 3)
make run-dev
```

## What Each Component Does

### vLLM Server
- Runs local Llama-3.1-8B-Instruct model
- Provides OpenAI-compatible API at http://localhost:8000
- Handles ~100+ concurrent requests with continuous batching
- **First run**: Downloads ~16GB model (takes 10-30 min depending on internet)

### RabbitMQ
- Message queue broker (runs in Podman)
- 3 priority queues: discovery, extraction, repair
- Management UI: http://localhost:15672 (guest/guest)

### Discovery Workers
- Fetch Transfermarkt pages
- Extract links matching patterns (leagues → clubs → players)
- Classify page types (player_profile, club_transfers, etc.)
- Publish high-value pages to extraction queue
- Publish crawl targets back to discovery queue

### Extraction Workers
- Consume pages from extraction queue
- Send HTML snippets to vLLM for structured extraction
- Parse LLM JSON responses into Pydantic models
- Save results to `data/extracted/{page_type}_{date}.jsonl`
- On failure: send to repair queue

### Repair Workers
- Consume failed extractions from repair queue
- Ask vLLM to suggest new CSS selectors
- Retry extraction with updated metadata

## Configuration

Edit `.env` to customize:

```bash
# Model selection (options)
VLLM_MODEL_NAME=meta-llama/Meta-Llama-3.1-8B-Instruct  # Default
# VLLM_MODEL_NAME=mistralai/Mistral-7B-Instruct-v0.3   # Alternative
# VLLM_MODEL_NAME=Qwen/Qwen2.5-7B-Instruct             # Alternative

# Worker counts (tune based on your hardware)
DISCOVERY_WORKERS=2      # I/O bound, 2-4 is fine
EXTRACTION_WORKERS=4     # LLM bound, match GPU capacity
REPAIR_WORKERS=1         # Low volume, 1 is enough

# Concurrent consumers per worker
CONCURRENT_CONSUMERS_PER_WORKER=10  # Higher = more concurrent LLM requests

# Scraping politeness
REQUEST_DELAY_MIN=2.0    # Min seconds between requests
REQUEST_DELAY_MAX=5.0    # Max seconds between requests
```

## Monitoring

### Queue Depths
```bash
make queues
```

### Logs (JSON format)
```bash
make logs
# Or specific patterns:
tail -f logs/*.log | jq 'select(.event=="extraction_success")'
```

### GPU Usage
```bash
watch -n 1 nvidia-smi
```

### Extracted Data
```bash
# Count transfers
wc -l data/extracted/player_transfers_*.jsonl

# View sample
cat data/extracted/player_transfers_*.jsonl | head -1 | jq .

# Find high-value transfers
cat data/extracted/player_transfers_*.jsonl | \
  jq 'select(.transfers[].fee.amount > 50000000)' | \
  jq -r '.transfers[] | "\(.player_name): \(.fee.amount) \(.fee.currency)"'
```

## Troubleshooting

### "vllm not found"
```bash
# Reinstall with CUDA support
pip install vllm --extra-index-url https://download.pytorch.org/whl/cu121
```

### "RabbitMQ connection refused"
```bash
# Check Podman is running
podman ps

# Restart RabbitMQ
podman restart transfermarkt-rabbitmq
```

### "Workers not consuming"
1. Check RabbitMQ is running: `make queues`
2. Check queue has messages: http://localhost:15672
3. Verify workers started: check logs for "worker_starting"
4. Ensure `.env` is loaded

### "Extraction always fails"
1. Check vLLM is running: `curl http://localhost:8000/health`
2. Test vLLM directly:
```bash
curl http://localhost:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "meta-llama/Meta-Llama-3.1-8B-Instruct",
    "messages": [{"role": "user", "content": "Hello!"}]
  }'
```

## Performance Tuning

### For Maximum Throughput
```bash
# In .env:
DISCOVERY_WORKERS=4
EXTRACTION_WORKERS=8
CONCURRENT_CONSUMERS_PER_WORKER=20

# vLLM settings (in start_vllm.sh or env):
export VLLM_MAX_NUM_SEQS=256
export VLLM_GPU_MEMORY_UTIL=0.95
```

### For Stability/Testing
```bash
# In .env:
DISCOVERY_WORKERS=1
EXTRACTION_WORKERS=2
CONCURRENT_CONSUMERS_PER_WORKER=5

# Slower crawl:
REQUEST_DELAY_MIN=5.0
REQUEST_DELAY_MAX=10.0
```

## Next Steps

Once running smoothly:

1. **Monitor for 1-2 hours** to ensure stability
2. **Check data quality**: Review extracted JSONs for accuracy
3. **Adjust prompts**: Edit `llm_client.py` if extraction quality is poor
4. **Add page types**: Extend patterns in `discovery_worker.py`
5. **Build database**: Design PostgreSQL schema for persistence
6. **Add normalization**: Currency conversion, position mapping, deduplication

## Data Schema (Current Output)

Each `.jsonl` file contains one JSON object per line:

```json
{
  "success": true,
  "page_type": "player_transfers",
  "url": "https://...",
  "transfers": [
    {
      "player_tm_id": "12345",
      "player_name": "Cristiano Ronaldo",
      "from_club": "Real Madrid",
      "to_club": "Juventus",
      "transfer_date": "2018-07-10",
      "season": "18/19",
      "transfer_type": "permanent",
      "fee": {
        "amount": 100000000.0,
        "currency": "EUR",
        "is_disclosed": true,
        "has_addons": false
      }
    }
  ],
  "extracted_at": "2026-02-02T12:00:00Z"
}
```

## Architecture Diagram

```
┌─────────────┐
│ Seed URLs   │
│ (Top 5      │
│  Leagues)   │
└──────┬──────┘
       │
       ▼
┌─────────────────────────────────────────────────────┐
│           RabbitMQ Priority Queues                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐          │
│  │Discovery │  │Extraction│  │  Repair  │          │
│  │Pri: 0-3  │  │Pri: 4-7  │  │Pri: 8-10 │          │
│  └──────────┘  └──────────┘  └──────────┘          │
└─────────────────────────────────────────────────────┘
       │               │               │
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ Discovery   │ │ Extraction  │ │   Repair    │
│  Workers    │ │  Workers    │ │   Workers   │
│  (2-4 proc) │ │  (4-8 proc) │ │  (1 proc)   │
└──────┬──────┘ └──────┬──────┘ └──────┬──────┘
       │               │               │
       │               ▼               │
       │        ┌─────────────┐        │
       │        │    vLLM     │        │
       │        │   Server    │◄───────┘
       │        │ (Llama 3.1) │
       │        └─────────────┘
       │               │
       ▼               ▼
  [New URLs]    [Structured Data]
       │               │
       └───────────────▼
           ┌─────────────────┐
           │ data/extracted/ │
           │   (JSONL files) │
           └─────────────────┘
```
