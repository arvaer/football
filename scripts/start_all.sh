#!/bin/bash
# Full stack startup script

set -e

echo "===== Starting Transfermarkt Scraper Stack ====="
echo ""

# Load environment variables
if [ -f .env ]; then
    echo "Loading environment variables from .env..."
    set -a
    source .env
    set +a
else
    echo "Warning: .env file not found, using defaults"
fi

echo ""
echo "Step 1: Starting RabbitMQ..."
./scripts/start_rabbitmq.sh

echo ""
echo "Step 2: Waiting for RabbitMQ to be ready..."
sleep 5

echo ""
echo "Step 3: Starting vLLM server..."
echo "Note: This will download the model if not cached locally"
echo "Press Ctrl+C to skip vLLM and start manually in another terminal"
echo ""

# Start vLLM in background (or manually in another terminal)
# ./scripts/start_vllm.sh &
# VLLM_PID=$!

echo "Please start vLLM in another terminal:"
echo "  ./scripts/start_vllm.sh"
echo ""
echo "Or if you prefer to run without vLLM (will fail on extraction):"
echo "  Press Enter to continue..."
read -r

echo ""
echo "Step 4: Seeding initial tasks..."
python -m scraper.main --seed-only

echo ""
echo "Step 5: Starting workers..."
echo "Starting with default worker counts (can override with CLI args)"
echo ""

# Start the main scraper
python -m scraper.main

echo ""
echo "===== Scraper Stopped ====="
