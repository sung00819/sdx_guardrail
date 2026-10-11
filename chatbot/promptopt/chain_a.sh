#!/bin/bash
# A안 첫 실행 (84번 tmux yumin_po): 기준선 3개를 같은 검증 인물로 → 더 나은 위치(system/turn)로 최적화
#  1. 지금 방식: SHORT 프롬프트 + [guardrail] 블록 (gym run.py)
#  2. seed 뱅크, position=system
#  3. seed 뱅크, position=turn
cd /data2/yumin/sdx_guardrail
PY=/data2/yumin/env/bin/python
O=out/promptopt
$PY chatbot/gym/run.py --ids-file $O/val_ids.txt --samples 2 --chatbot qwen8b --prompt short --config config_po.json \
  --out $O/eval_baseline_short --workers 24 > $O/eval_baseline_short.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --position system --config config_po.json --workers 24 --out $O/eval_seed_system > $O/eval_seed_system.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --position turn --config config_po.json --workers 24 --out $O/eval_seed_turn > $O/eval_seed_turn.log 2>&1 &
wait
echo "$(date) BASELINES_DONE"
tail -1 $O/eval_seed_system.log $O/eval_seed_turn.log
POS=$($PY -c "
import json
s=json.load(open('$O/eval_seed_system/summary.json'))['summary']['R']
t=json.load(open('$O/eval_seed_turn/summary.json'))['summary']['R']
print('system' if s >= t else 'turn')")
echo "position = $POS"
# seed 뱅크 검증 대화는 이미 있다 → 최적화의 it000 으로 재사용 (run 은 있는 (id, sample) 을 건너뛴다)
mkdir -p $O/p1_$POS && [ -e $O/p1_$POS/val_it000.jsonl ] || cp $O/eval_seed_$POS/episodes_val.jsonl $O/p1_$POS/val_it000.jsonl
$PY chatbot/promptopt/optimize.py opt --run p1_$POS --position $POS --config config_po.json --workers 32 --iters 20
echo "$(date) OPT_EXIT"
