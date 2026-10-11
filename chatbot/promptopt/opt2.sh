#!/bin/bash
# A안 최적화 이어 돌리기 (병렬: 한 반복에 조각 3개, 미니배치 16명, 한 풀 160 스레드). 끝나면 test_a.sh 가 이어 받는다
cd /data2/yumin/sdx_guardrail
/data2/yumin/env/bin/python chatbot/promptopt/optimize.py opt --run p1_turn --position turn --config config_po.json --workers 160 --iters 20
echo "$(date) OPT_EXIT"
