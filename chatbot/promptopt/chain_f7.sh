#!/bin/bash
# 3번 F7: Qwen3-8B 에서 만든 뱅크를 재학습 없이 Gemma-3-12B 에 그대로 붙여 test 150명 비교 (각 1표본, 동시에)
#  지금 방식(SHORT + 블록) / seed 뱅크 turn / p1 최적 turn / p1 최적 system  (+ p2 최적 turn 은 p2 끝나면)
cd /data2/yumin/sdx_guardrail
PY=/data2/yumin/env/bin/python
O=out/promptopt
until curl -s -m5 localhost:18621/v1/models | grep -q gemma; do sleep 30; done
echo "$(date) GEMMA_UP"
$PY -c "import json;print('\n'.join(json.loads(l)['id'] for l in open('out/scenes_test.jsonl') if l.strip()))" > $O/test_ids.txt
$PY chatbot/gym/run.py --profiles out/scenes_test.jsonl --ids-file $O/test_ids.txt --samples 1 --chatbot gemma12b --prompt short \
  --config config_po.json --out $O/f7_gemma_baseline_short --workers 50 > $O/f7_gemma_baseline_short.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --chatbot gemma12b --position turn --config config_po.json --workers 50 \
  --out $O/f7_gemma_seed_turn > $O/f7_gemma_seed_turn.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --chatbot gemma12b --position turn --config config_po.json --workers 50 \
  --bank $O/p1_turn/bank_best.json --out $O/f7_gemma_p1best_turn > $O/f7_gemma_p1best_turn.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --chatbot gemma12b --position system --config config_po.json --workers 50 \
  --bank $O/p1_turn/bank_best.json --out $O/f7_gemma_p1best_system > $O/f7_gemma_p1best_system.log 2>&1 &
wait
echo "$(date) F7_MAIN_DONE"
until grep -q P2_OPT_EXIT /data2/yumin/logs/po_p2.log; do sleep 120; done
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --chatbot gemma12b --position turn --config config_po.json --workers 100 \
  --bank $O/p2_turn/bank_best.json --out $O/f7_gemma_p2best_turn > $O/f7_gemma_p2best_turn.log 2>&1
echo "$(date) F7_DONE"
