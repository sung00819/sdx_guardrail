#!/bin/bash
# 84번 tmux 에서 혼자 끝까지: 정책 서버(LoRA) 확인 → 점검(smoke.py) → GRPO 반복 (rlver_rl.py).
# 끊겨도 같은 명령으로 다시 돌리면 끝난 반복은 건너뛴다.
#   tmux new-window -t yumin_rlver -n rl "bash chatbot/rlver/train/chain.sh r1 20"
RUN=${1:-r1}
ITERS=${2:-20}
cd "$(dirname "$0")/../../.."
PY=/data2/yumin/env/bin/python
LOG=out/rlver_rl/chain_$RUN.log
mkdir -p out/rlver_rl
exec > >(tee -a "$LOG") 2>&1
echo "$(date '+%F %T') 시작 run=$RUN iters=$ITERS"
for i in $(seq 1 90); do curl -s -m 3 localhost:18602/v1/models | grep -q Qwen && break; sleep 10; done
if [ ! -f out/rlver_rl/smoke/SMOKE_OK ]; then
  cd chatbot/rlver/train && $PY -u smoke.py --episodes ../../../out/rlver/eval_bank_8b/episodes.jsonl | tee /dev/stderr | grep -q SMOKE_OK \
    && touch ../../../out/rlver_rl/smoke/SMOKE_OK; cd - > /dev/null
  [ -f out/rlver_rl/smoke/SMOKE_OK ] || { echo "$(date '+%F %T') 점검 실패 → 멈춤"; exit 1; }
fi
cd chatbot/rlver/train && $PY -u rlver_rl.py --run "$RUN" --iters "$ITERS"
echo "$(date '+%F %T') RL_EXIT $?"
