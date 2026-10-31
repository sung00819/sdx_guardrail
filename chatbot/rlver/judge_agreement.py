"""Jev · Luna · Sol 턴 판정 일치도 (turn_judge.py 결과 두 개, 2026-11-01). python chatbot/rlver/judge_agreement.py > out/rlver/1101)jev_luna_sol_agreement.md"""
import json,sys
sys.path.insert(0,'chatbot/rlver'); from turn_gold import MERGE,MNAME,NAME,TH; from jev import QUESTIONS
RUNS=["1025)bank_jev_test_30b","1025)bank_jev_plan_test_30b_riskplan"]
rows=[]
for d in RUNS:
    E={(e['id'],e['setting']):e for e in map(json.loads,open(f"out/rlver/{d}/episodes.jsonl"))}
    L={(j['id'],j['setting'],j['turn']):set(j['yes']) for j in map(json.loads,open(f"out/rlver/{d}/turn_judge.jsonl"))}
    S={(j['id'],j['setting'],j['turn']):set(j['yes']) for j in map(json.loads,open(f"out/rlver/{d}/turn_judge_gpt-6.1-sol.jsonl"))}
    for k in L.keys()&S.keys():
        t=E[k[:2]]['turns'][k[2]]
        rows.append(({a for a,p in t['jev'].items() if p>=TH},L[k],S[k]))
def kappa(a,b):
    n=len(a); po=sum(x==y for x,y in zip(a,b))/n; pa=sum(a)/n; pb=sum(b)/n; pe=pa*pb+(1-pa)*(1-pb)
    return (po-pe)/(1-pe) if pe<1 else 1.0
m=lambda s:{MERGE.get(x,x) for x in s}
print(f"# Jev · Luna · Sol 턴 판정 일치도 (2026-11-01)\n\n30B 라우팅 + 30B 계획 칸 (위험 턴만), 두 판정이 다 있는 턴 {len(rows)}개. 셋 다 Jev 가 받은 같은 입력 (최근 사용자 메시지 3개와 사이 답, Jev 질문 정본). Jev 는 P ≥ {TH} 면 예. κ = Cohen's kappa (개발계획서 기준 κ ≥ 0.6).\n")
print("| 축 | 예 턴 수 Jev / Luna / Sol | κ Jev–Luna | κ Jev–Sol | κ Luna–Sol | Luna·Sol 둘 다 예일 때 Jev 재현율 | Luna·Sol 둘 다 아니오일 때 Jev 오탐률 |")
print("|---|---|---|---|---|---|---|")
for ax in dict.fromkeys(MERGE.get(k,k) for k in QUESTIONS):
    J=[ax in m(r[0]) for r in rows]; Lu=[ax in m(r[1]) for r in rows]; So=[ax in m(r[2]) for r in rows]
    both=[j for j,l,s in zip(J,Lu,So) if l and s]; none=[j for j,l,s in zip(J,Lu,So) if not l and not s]
    f=lambda x:f"{x:.2f}"
    print(f"| {MNAME.get(ax) or NAME[ax]} | {sum(J)} / {sum(Lu)} / {sum(So)} | {f(kappa(J,Lu))} | {f(kappa(J,So))} | {f(kappa(Lu,So))} | "
          f"{sum(both)/len(both):.0%} ({len(both)}) | {sum(none)/len(none):.0%} ({sum(none)}) |" if both else
          f"| {MNAME.get(ax) or NAME[ax]} | {sum(J)} / {sum(Lu)} / {sum(So)} | {f(kappa(J,Lu))} | {f(kappa(J,So))} | {f(kappa(Lu,So))} | - | {sum(none)/len(none):.0%} ({sum(none)}) |")
