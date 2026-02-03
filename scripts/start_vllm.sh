#!/bin/bash
# Start vLLM inference server

set -e

# Configuration from environment or defaults
MODEL_NAME=${VLLM_MODEL_NAME:-"Qwen/Qwen2.5-7B-Instruct"}
HOST=${VLLM_HOST:-"0.0.0.0"}
PORT=${VLLM_PORT:-"8000"}
MAX_MODEL_LEN=${VLLM_MAX_MODEL_LEN:-"24576"}  # Use 24k of Qwen's 32k context
GPU_MEMORY_UTIL=${VLLM_GPU_MEMORY_UTIL:-"0.9"}
MAX_NUM_SEQS=${VLLM_MAX_NUM_SEQS:-"128"}
TENSOR_PARALLEL=${VLLM_TENSOR_PARALLEL:-"1"}

echo "Starting vLLM server..."
echo "Model: $MODEL_NAME"
echo "Host: $HOST:$PORT"
echo "Max model length: $MAX_MODEL_LEN"
echo "GPU memory utilization: $GPU_MEMORY_UTIL"
echo "Max concurrent sequences: $MAX_NUM_SEQS"

# Start vLLM server
python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL_NAME" \
    --host "$HOST" \
    --port "$PORT" \
    --max-model-len "$MAX_MODEL_LEN" \
    --gpu-memory-utilization "$GPU_MEMORY_UTIL" \
    --max-num-seqs "$MAX_NUM_SEQS" \
    --tensor-parallel-size "$TENSOR_PARALLEL" \
    --enable-prefix-caching \
    --dtype auto

# Alternative: use vllm serve command (newer versions)
# vllm serve "$MODEL_NAME" \
#     --host "$HOST" \
#     --port "$PORT" \
#     --max-model-len "$MAX_MODEL_LEN" \
#     --gpu-memory-utilization "$GPU_MEMORY_UTIL" \
#     --max-num-seqs "$MAX_NUM_SEQS" \
#     --tensor-parallel-size "$TENSOR_PARALLEL" \
#     --enable-prefix-caching \
#     --dtype auto
