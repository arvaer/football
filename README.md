# Agentic Transfermarkt Scraper

LLM-powered web scraper using vLLM and RabbitMQ for autonomous football transfer data collection from Transfermarkt.

## 🚀 Features

- **Smart vLLM Throttling**: Protects your local GPU with rate limiting, backoff, and circuit breaker
- **LLM-Based Extraction**: Structured data extraction with context-aware prompts
- **Distributed Queue**: RabbitMQ with priority support for efficient task management
- **Self-Healing**: Automatic selector repair on extraction failures
- **Graceful Degradation**: Circuit breaker prevents cascading failures

## Architecture

- **vLLM**: Local LLM inference server for structured data extraction and selector repair
  - **Rate Limiter**: Token bucket algorithm prevents GPU overload
  - **Circuit Breaker**: Auto-recovery from server failures
  - **Smart Retry**: Exponential backoff with jitter
- **RabbitMQ**: Distributed task queue with priority support
- **3 Worker Types**:
  - Discovery Workers: Crawl pages, extract links, classify page types
  - Extraction Workers: LLM-based structured data extraction (throttled)
  - Repair Workers: LLM-based selector repair on failures
- **Configuration**: Pydantic Settings with environment variables
- **Data Models**: Pydantic models for players, clubs, transfers, fees
- **Output**: JSONL files organized by date and page type

## Quick Start

### 1. Install Dependencies

```bash
# Activate venv
source venv/bin/activate.fish  # or source venv/bin/activate for bash

# Install requirements
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example env file
cp .env.example .env

# Edit .env with your settings
# Key variables for vLLM throttling:
# - VLLM_MAX_CONCURRENT=2          # Max concurrent requests (protect your GPU!)
# - VLLM_REQUESTS_PER_MINUTE=20    # Rate limit (~3 sec avg gap)
# - CONCURRENT_CONSUMERS_PER_WORKER=3  # Reduced to avoid flooding
# - PREFETCH_COUNT=1               # Only fetch 1 message at a time

# See VLLM_THROTTLING.md for tuning guide
```

### 3. Start Infrastructure

**Option A: Manual (recommended for first run)**

```bash
# Terminal 1: Start RabbitMQ
./scripts/start_rabbitmq.sh

# Terminal 2: Start vLLM (will download model on first run)
./scripts/start_vllm.sh

# Terminal 3: Run scraper
python -m scraper.main
```

**Option B: All-in-one script**

```bash
./scripts/start_all.sh
```

## Usage

### Seed Initial Tasks

```bash
python -m scraper.main --seed-only
```

### Run with Custom Worker Counts

```bash
python -m scraper.main \
    --discovery-workers 4 \
    --extraction-workers 8 \
    --repair-workers 2
```

### Monitor vLLM Throttling (NEW!)

Watch the rate limiting and circuit breaker in action:

```bash
# Pipe logs to the monitoring script
python -m scraper.main 2>&1 | python scripts/monitor_throttling.py
```

You'll see:
- ✅ Successful requests with timing
- 🔄 Retries with backoff delays  
- ⏳ Rate limiting in action
- 🔴 Circuit breaker opens/closes
- 📊 Live stats every 10 requests

### Monitor Queues

RabbitMQ Management UI: http://localhost:15672 (guest/guest)

### Check Logs

Logs are written to `logs/` directory in JSON format.

### View Extracted Data

```bash
# View extracted transfers
cat data/extracted/player_transfers_*.jsonl | jq .

# Count total transfers
cat data/extracted/player_transfers_*.jsonl | wc -l
```

## Project Structure

```
fb/
├── scraper/
│   ├── config.py           # Pydantic Settings configuration
│   ├── models.py           # Data models (Player, Transfer, Club, etc.)
│   ├── queue.py            # RabbitMQ queue management
│   ├── llm_client.py       # vLLM client wrapper
│   ├── main.py             # Main orchestrator
│   └── workers/
│       ├── discovery_worker.py    # Page discovery and crawling
│       ├── extraction_worker.py   # LLM-based data extraction
│       └── repair_worker.py       # Selector repair agent
├── scripts/
│   ├── start_vllm.sh       # Start vLLM server
│   ├── start_rabbitmq.sh   # Start RabbitMQ (Podman)
│   └── start_all.sh        # Start full stack
├── data/extracted/         # Output JSONL files
├── logs/                   # Structured JSON logs
├── requirements.txt
└── .env                    # Configuration (copy from .env.example)
```

## Configuration

All configuration is via environment variables (see `.env.example`):

### vLLM Settings - Basic
- `VLLM_BASE_URL`: vLLM server URL
- `VLLM_MODEL_NAME`: Model to use
- `VLLM_MAX_TOKENS`: Max tokens per generation
- `VLLM_TEMPERATURE`: Sampling temperature

### vLLM Settings - Throttling (NEW!)
- `VLLM_MAX_CONCURRENT`: Max concurrent requests (default: 2)
- `VLLM_REQUESTS_PER_MINUTE`: Rate limit (default: 20)
- `VLLM_MAX_RETRIES`: Retry attempts (default: 5)
- `VLLM_BASE_BACKOFF`: Initial backoff delay (default: 1.0s)
- `VLLM_MAX_BACKOFF`: Max backoff delay (default: 60s)
- `VLLM_CIRCUIT_BREAKER_THRESHOLD`: Failures before opening (default: 5)
- `VLLM_CIRCUIT_BREAKER_TIMEOUT`: Recovery timeout (default: 60s)

**See [VLLM_THROTTLING.md](VLLM_THROTTLING.md) for detailed tuning guide.**

### RabbitMQ Settings
- `RABBITMQ_HOST`, `RABBITMQ_PORT`: Connection details
- `QUEUE_MAX_PRIORITY`: Max priority level (default: 10)

### Worker Settings
- `DISCOVERY_WORKERS`: Number of discovery workers
- `EXTRACTION_WORKERS`: Number of extraction workers
- `REPAIR_WORKERS`: Number of repair workers
- `CONCURRENT_CONSUMERS_PER_WORKER`: Async consumers per worker (default: 3)
- `PREFETCH_COUNT`: Messages to prefetch (default: 1)

### Scraper Settings
- `REQUEST_DELAY_MIN`, `REQUEST_DELAY_MAX`: Politeness delays
- `USER_AGENT`: HTTP User-Agent header
- `MAX_RETRIES`: Retry attempts per task
- `MAX_PAGES`: Maximum pages to scrape

### Seeds
- `SEED_URLS`: Comma-separated initial URLs

## Data Models

### Player
- `tm_id`, `name`, `date_of_birth`, `nationality`
- `height_cm`, `position`, `dominant_foot`, `current_club`

### Transfer
- `player_tm_id`, `player_name`
- `from_club`, `to_club` (with TM IDs)
- `transfer_date`, `season`, `transfer_type`
- `fee`: `amount`, `currency`, `is_disclosed`, `has_addons`, `notes`
- `market_value_at_transfer`

### Club
- `tm_id`, `name`, `country`, `league`, `division`

## LLM Prompts

### Extraction
System prompt includes:
- Page type context
- JSON schema for expected output
- Extraction rules (ID extraction, date normalization, etc.)
- Optional few-shot examples

### Repair
System prompt includes:
- Failed selectors context
- HTML snippet
- Request for new CSS selectors as JSON

## Monitoring

### Queue Stats
```bash
# Check queue depths
podman exec transfermarkt-rabbitmq rabbitmqctl list_queues
```

### Worker Health
Check logs for error patterns:
```bash
tail -f logs/*.log | jq 'select(.level=="error")'
```

### GPU Utilization (vLLM)
```bash
nvidia-smi dmon
```

## Troubleshooting

### vLLM won't start
- Check GPU availability: `nvidia-smi`
- Verify CUDA version compatibility
- Check model download: models cache in `~/.cache/huggingface/`

### RabbitMQ connection refused
- Ensure Podman is running
- Check container: `podman ps | grep rabbitmq`
- Restart: `./scripts/start_rabbitmq.sh`

### Workers not consuming tasks
- Check RabbitMQ connection in logs
- Verify queue declarations in Management UI
- Check prefetch settings in config

### Extraction failures
- Review HTML structure changes on Transfermarkt
- Check LLM responses in logs
- Adjust prompts in `llm_client.py`
- Inspect repair queue for patterns

## Next Steps (Not Implemented)

- [ ] PostgreSQL persistence layer
- [ ] Database schema and normalization
- [ ] Currency conversion with historical FX rates
- [ ] Deduplication across language domains
- [ ] Market value time series tracking
- [ ] Graph construction (club-club, player-club)
- [ ] Valuation model training pipeline
- [ ] Monitoring dashboard
- [ ] Incremental updates vs full recrawl

## License

MIT
