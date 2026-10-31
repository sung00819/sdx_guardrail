#!/bin/bash
# 가드레일·시뮬레이터용 vLLM 서버 (README '2. 모델 서버' 와 같은 명령, 24GB GPU 기준). 주소는 config_local.json (guard.py 기본) 의 포트와 같다.
#   bash chatbot/rlver/serve_vllm.sh chatbot      # 챗봇 Qwen3-8B, GPU 0 한 장, 포트 18602
#   bash chatbot/rlver/serve_vllm.sh sim          # 시뮬레이터·30B 챗봇 Qwen3-30B-A3B FP8, GPU 1·2 두 장, 포트 18601
# GPU 번호는 GPU=...로 바꾼다 (예: GPU=3 bash serve_vllm.sh chatbot). 드라이버가 낮아 컴파일에서 멈추면 EAGER=1 (84번은 그랬다).
# 30B FP8 은 43번 A100 에서는 안 떴다 (84번 3090 은 됐다). 챗봇에 --reasoning-parser 를 붙이지 말 것: 답에 <think> 블록이 그대로 와야 한다.
set -e
EXTRA=""; if [ "${EAGER:-0}" = 1 ]; then EXTRA=--enforce-eager; fi
case "$1" in
  chatbot)
    CUDA_VISIBLE_DEVICES=${GPU:-0} vllm serve Qwen/Qwen3-8B --host 127.0.0.1 --port ${PORT:-18602} \
      --gpu-memory-utilization 0.90 --max-model-len 16384 --seed 0 $EXTRA ;;
  sim)
    CUDA_VISIBLE_DEVICES=${GPU:-1,2} vllm serve Qwen/Qwen3-30B-A3B-Instruct-2507-FP8 --host 127.0.0.1 --port ${PORT:-18601} \
      --tensor-parallel-size 2 --gpu-memory-utilization 0.90 --max-model-len 16384 --seed 0 $EXTRA ;;
  *)
    echo "사용법: bash serve_vllm.sh chatbot|sim"; exit 1 ;;
esac
