#!/bin/bash
# Check system status and requirements

set -e

echo "===== System Status Check ====="
echo ""

# Check Python version
echo "Python version:"
python --version
echo ""

# Check pip packages
echo "Checking key dependencies:"
pip list | grep -E "(vllm|aio-pika|aiohttp|pydantic|structlog)" || echo "Dependencies not installed yet"
echo ""

# Check podman (for RabbitMQ)
echo "podman status:"
if command -v podman &> /dev/null; then
    podman --version
    echo "podman is installed ✓"
    
    # Check if RabbitMQ container exists
    if podman ps --format '{{.Names}}' | grep -q "transfermarkt-rabbitmq"; then
        echo "RabbitMQ container is running ✓"
    else
        echo "RabbitMQ container not running (use ./scripts/start_rabbitmq.sh)"
    fi
else
    echo "podman not found ✗"
    echo "Install podman to run RabbitMQ: https://podman.io/getting-started/installation"
fi
echo ""

# Check GPU (for vLLM)
echo "GPU status:"
if command -v nvidia-smi &> /dev/null; then
    nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader
    echo "NVIDIA GPU detected ✓"
else
    echo "nvidia-smi not found ✗"
    echo "vLLM requires CUDA-capable GPU"
fi
echo ""

# Check vLLM server
echo "vLLM server status:"
if curl -s http://localhost:8000/health &> /dev/null; then
    echo "vLLM server is running ✓"
else
    echo "vLLM server not running (use ./scripts/start_vllm.sh)"
fi
echo ""

# Check RabbitMQ API
echo "RabbitMQ API status:"
if curl -s http://localhost:15672 &> /dev/null; then
    echo "RabbitMQ management UI is accessible ✓"
    echo "URL: http://localhost:15672 (guest/guest)"
else
    echo "RabbitMQ not accessible"
fi
echo ""

# Check data directories
echo "Data directories:"
for dir in data/extracted logs; do
    if [ -d "$dir" ]; then
        echo "  $dir/ exists ✓"
        echo "    Files: $(find $dir -type f 2>/dev/null | wc -l)"
    else
        echo "  $dir/ not found"
    fi
done
echo ""

# Check environment
echo "Environment configuration:"
if [ -f .env ]; then
    echo "  .env exists ✓"
    echo "  Model: $(grep VLLM_MODEL_NAME .env | cut -d= -f2)"
    echo "  Workers: Discovery=$(grep DISCOVERY_WORKERS .env | cut -d= -f2), Extraction=$(grep EXTRACTION_WORKERS .env | cut -d= -f2)"
else
    echo "  .env not found ✗"
    echo "  Copy .env.example to .env and configure"
fi
echo ""

echo "===== Status Check Complete ====="
