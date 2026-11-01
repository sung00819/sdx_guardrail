#!/bin/bash
# NemoGuard 8B v3 (Nemotron Content Safety), GPU $1, 포트 $2 (2026-11-01 30B 대화 비교용)
export HF_HOME=/data/minseok/yumin/hf TMPDIR=/data/minseok/yumin/tmp HF_HUB_OFFLINE=1 CUDA_VISIBLE_DEVICES=$1 VLLM_ENGINE_READY_TIMEOUT_S=3600
exec /home/minseok/.conda/envs/vllm_qwen/bin/vllm serve /data/minseok/yumin/models/Nemotron-Safety-Guard-8B-v3 --served-model-name nemoguard --host 127.0.0.1 --port $2 --max-model-len 8192 --gpu-memory-utilization 0.90 --enable-prefix-caching
