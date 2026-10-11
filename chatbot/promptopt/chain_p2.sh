#!/bin/bash
# 1번 (질문 여러 개·핫라인 반복): p1 최적 + suffix 를 (a) 바로 test, (b) 이어서 최적화 → test. 동시에 돌린다
cd /data2/yumin/sdx_guardrail
PY=/data2/yumin/env/bin/python
O=out/promptopt
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --position turn --config config_po.json --workers 150 \
  --bank chatbot/promptopt/bank_p2_seed.json --out $O/test_p2seed_turn > $O/test_p2seed_turn.log 2>&1 &
$PY chatbot/promptopt/optimize.py opt --run p2_turn --position turn --config config_po.json --workers 160 --iters 8 \
  --bank chatbot/promptopt/bank_p2_seed.json --blame_w T1=1,T2=0.2,T3=0.3 --seed 2
echo "$(date) P2_OPT_EXIT"
$PY chatbot/promptopt/optimize.py eval --split test --samples 1 --position turn --config config_po.json --workers 150 \
  --bank $O/p2_turn/bank_best.json --out $O/test_p2best_turn > $O/test_p2best_turn.log 2>&1
wait
echo "$(date) P2_DONE"
