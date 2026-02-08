.PHONY: help install status rabbitmq vllm seed run clean league-tiers

help:
	@echo "Transfermarkt Agentic Scraper - Makefile Commands"
	@echo ""
	@echo "Setup:"
	@echo "  make install     - Install Python dependencies"
	@echo "  make status      - Check system status and requirements"
	@echo ""
	@echo "Infrastructure:"
	@echo "  make rabbitmq    - Start RabbitMQ (Podman)"
	@echo "  make vllm        - Start vLLM inference server"
	@echo ""
	@echo "Scraping:"
	@echo "  make seed        - Seed initial tasks only"
	@echo "  make run         - Run scraper with default settings"
	@echo "  make run-dev     - Run with fewer workers for testing"
	@echo "  make league-tiers - Extract league tier data (standalone)"
	@echo ""
	@echo "Utilities:"
	@echo "  make clean       - Clean logs and extracted data"
	@echo "  make logs        - Tail logs in JSON format"
	@echo "  make queues      - Show RabbitMQ queue stats"

install:
# 	pip install -r requirements.txt
	uv sync
status:
	./scripts/check_status.sh

rabbitmq:
	./scripts/start_rabbitmq.sh

vllm:
	./scripts/start_vllm.sh

seed:
# 	python -m scraper.main --seed-only
	uv run python -m scraper.main --seed-only

run:
	uv run python -m scraper.main

run-dev:
	uv run python -m scraper.main --discovery-workers 1 --extraction-workers 2 --repair-workers 1

league-tiers:
	@echo "Running league tier extraction (standalone)..."
	uv run python scripts/run_league_tier_extraction.py

clean:
	@echo "Cleaning logs and data..."
	rm -rf logs/*.log
	rm -rf data/extracted/*.jsonl
	@echo "Clean complete"

logs:
	@if [ -f logs/*.log ]; then \
		tail -f logs/*.log | jq .; \
	else \
		echo "No log files found"; \
	fi

queues:
	@echo "RabbitMQ Queue Stats:"
	@podman exec transfermarkt-rabbitmq rabbitmqctl list_queues name messages consumers || echo "RabbitMQ not running"
