#!/bin/bash
# 2026-10-09 OpenRouter 키 한도 초과 → 가드레일 oracle (시뮬레이터 실제 코드) 로 같은 조건 재비교 (사용자 결정)
#  F7: test 150 × {Qwen3-8B, Gemma-3-12B} × {지금 방식, seed, p1 최적, p1 최적+suffix}  — 동시에
#  1번: p1 최적+suffix 에서 oracle 로 최적화(p3) → 끝나면 두 모델로 test
cd /data2/yumin/sdx_guardrail
PY=/data2/yumin/env/bin/python
O=out/promptopt
G="--guardrail oracle --config config_po.json"
for m in qwen8b gemma12b; do
  $PY chatbot/gym/run.py --profiles out/scenes_test.jsonl --ids-file $O/test_ids.txt --samples 1 --chatbot $m --prompt short $G \
    --out $O/or_${m}_now --workers 50 > $O/or_${m}_now.log 2>&1 &
  for b in seed:chatbot/promptopt/seed_bank.json p1best:$O/p1_turn/bank_best.json p1suffix:chatbot/promptopt/bank_p2_seed.json; do
    $PY chatbot/promptopt/optimize.py eval --split test --samples 1 --chatbot $m --position turn $G --workers 50 \
      --bank ${b#*:} --out $O/or_${m}_${b%%:*} > $O/or_${m}_${b%%:*}.log 2>&1 &
  done
done
$PY chatbot/promptopt/optimize.py opt --run p3_oracle --position turn $G --workers 120 --iters 8 \
  --bank chatbot/promptopt/bank_p2_seed.json --blame_w T1=1,T2=0.2,T3=0.3 --seed 3
echo "$(date) P3_OPT_EXIT"
for m in qwen8b gemma12b; do
  $PY chatbot/promptopt/optimize.py eval --split test --samples 1 --chatbot $m --position turn $G --workers 75 \
    --bank $O/p3_oracle/bank_best.json --out $O/or_${m}_p3best > $O/or_${m}_p3best.log 2>&1 &
done
wait
echo "$(date) ORACLE_DONE"
