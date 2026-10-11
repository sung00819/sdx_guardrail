# archive

2026-10-07 까지 expert11 과 비교한 설계. 앞으로는 expert11 만 쓴다.

- [base](base/): 기존 감지 질문(v4i) 13개로 단계를 나눔. 마지막 질문 버전 `v4i`
- [base-eval](base-eval/): base + 전문가 추가 신호 + 자살 행동·자해의 경험과 시점 (27개). 마지막 질문 버전 `el4c`

세 설계 비교 결과는 [results/README.md](../results/README.md)에 있다. 채점 원본·비교표는 `out/archive/` 에 옮겨 두었다 (git 에 올라가지 않음).
이 폴더의 코드는 지금 `common/` 스크립트로는 돌아가지 않는다 (`rules.DESIGNS` 에서 뺌).
