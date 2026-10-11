#!/bin/bash
# 54번 서버: 시뮬레이터 복제본을 내리고 GPU 8장으로 LoRA SFT. 맥에서 실행한다.
#   bash chatbot/train/run_sft_54.sh out/sft/train.jsonl lora_sft_v1
set -e
DATA=$1; NAME=${2:-lora_sft_v1}
HOST=${SDX_HOST54:?SDX_HOST54 (54번 서버 주소) 를 설정하세요}
R='$HOME/yumin_sim'
# 54번은 sftp 서브시스템이 없어 scp 가 안 된다 → ssh 로 보낸다
ssh -o BatchMode=yes $HOST 'cat > ~/yumin_sim/sft_train.jsonl' < "$DATA"
ssh -o BatchMode=yes $HOST 'cat > ~/yumin_sim/train_sft.py' < "$(dirname "$0")/train_sft.py"
ssh -o BatchMode=yes $HOST "bash -s" <<EOF
for p in \$(ps -u \$USER -o pid,cmd | grep "[v]llm serve Qwen/Qwen3-30B" | awk '{print \$1}'); do kill \$p; done
sleep 20
for p in \$(ps -u \$USER -o pid,cmd | grep "[V]LLM::" | awk '{print \$1}'); do kill -9 \$p; done  # 남은 워커
sleep 5
nvidia-smi --query-gpu=index,memory.used --format=csv,noheader | tr '\n' ' '; echo
cd ~/yumin_sim
tmux kill-session -t sft 2>/dev/null || true
tmux new-session -d -s sft "export HF_HOME=$R/hf HF_HUB_OFFLINE=1; $R/train_env/bin/accelerate launch --num_processes 8 --mixed_precision bf16 train_sft.py --model $R/models/Qwen3-8B --data sft_train.jsonl --out $NAME 2>&1 | tee logs/$NAME.log"
echo "started tmux session sft on $HOST"
EOF
