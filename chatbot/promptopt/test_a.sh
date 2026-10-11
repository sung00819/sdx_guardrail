#!/bin/bash
# A안 최종: 최적화가 끝나면 test 150명으로 지금 방식 / seed 뱅크(turn) / 최적 뱅크(turn) 비교 (각 1표본)
cd /data2/yumin/sdx_guardrail
PY=/data2/yumin/env/bin/python
O=out/promptopt
until grep -q OPT_EXIT /data2/yumin/logs/po_chain_a.log; do sleep 120; done
$PY -c "import json;print('\n'.join(json.loads(l)['id'] for l in open('out/scenes_test.jsonl') if l.strip()))" > $O/test_ids.txt
$PY chatbot/gym/run.py --profiles out/scenes_test.jsonl --ids-file $O/test_ids.txt --samples 1 --chatbot qwen8b --prompt short \
  --config config_po.json --out $O/test_baseline_short --workers 48 > $O/test_baseline_short.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --position turn --config config_po.json --workers 48 \
  --out $O/test_seed_turn > $O/test_seed_turn.log 2>&1 &
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --position turn --config config_po.json --workers 48 \
  --bank $O/p1_turn/bank_best.json --out $O/test_best_turn > $O/test_best_turn.log 2>&1 &
wait
echo "$(date) TEST_DONE"
