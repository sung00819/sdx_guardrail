"""시드 → 페르소나 → 배경 → 검수 (OpenRouter). 프롬프트는 sim_text.py, 설계는 SIMULATOR_PERSONA.md.

ResidencyRL 3.1 의 Stage 2(생성)·3(LLM 검수: accept/modify/reject)·4(TF-IDF 중복 제거)를 따른다.
키: 환경변수 OPENROUTER_API_KEY 또는 저장소 위쪽 .env.

  python chatbot/gen_scene.py --seeds out/pilot_seeds.json --model openai/gpt-6-luna \\
      --check-model openai/gpt-6-sol --out out/pilot_luna.jsonl
  python chatbot/gen_scene.py --dedup out/scenes_train.jsonl
"""

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "common"))
from jev_client import read_dotenv  # noqa: E402
from sim_text import CHECK_PROMPT, PERSONA_PROMPT, describe_persona_seed, describe_state, scene_prompt  # noqa: E402

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
DEDUP_THRESHOLD = 0.9


def api_key():
    if os.environ.get("OPENROUTER_API_KEY"):
        return os.environ["OPENROUTER_API_KEY"]
    for path in (os.path.join(HERE, "..", ".env"), os.path.join(HERE, "..", "..", ".env")):
        key = read_dotenv(path).get("OPENROUTER_API_KEY")
        if key:
            return key
    raise SystemExit("OPENROUTER_API_KEY 를 환경변수나 .env 파일에 설정하세요.")


def chat_json(session, model, prompt, retries=4):
    """JSON 응답 한 번. 반환: (dict 또는 None, 비용 $, 원문). 파싱 실패 = 거절 또는 형식 오류."""
    body = {"model": model, "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}, "usage": {"include": True}}
    for attempt in range(retries):
        try:
            r = session.post(ENDPOINT, json=body, timeout=180)
        except requests.exceptions.RequestException:
            time.sleep(min(2 ** attempt, 30))
            continue
        if r.status_code == 200:
            data = r.json()
            text = data["choices"][0]["message"].get("content") or ""
            cost = (data.get("usage") or {}).get("cost") or 0.0
            try:
                return json.loads(text), cost, text
            except json.JSONDecodeError:
                return None, cost, text
        if r.status_code in (429, 500, 502, 503, 504):
            time.sleep(min(2 ** attempt, 30))
            continue
        return None, 0.0, f"HTTP {r.status_code}: {r.text[:300]}"
    return None, 0.0, "retries exhausted"


def apply_fixes(persona, scene, fixes):
    for field, value in (fixes or {}).items():
        if field in scene:
            scene[field] = value
        elif field in persona:
            persona[field] = value


def generate(session, seed, model, check_model):
    out = {"id": seed["id"], "seed": seed, "model": model, "check_model": check_model, "cost": 0.0, "error": None}
    persona, c, raw = chat_json(session, model, PERSONA_PROMPT.format(seed=describe_persona_seed(seed)))
    out["cost"] += c
    if persona is None:
        out["error"] = {"step": "persona", "raw": raw[:500]}
        return out
    scene, c, raw = chat_json(session, model, scene_prompt(seed, persona))
    out["cost"] += c
    if scene is None:
        out.update(persona=persona, error={"step": "scene", "raw": raw[:500]})
        return out
    check, c, raw = chat_json(session, check_model, CHECK_PROMPT.format(
        seed=describe_persona_seed(seed), state=describe_state(seed),
        expected_risk=(f"a hidden risk detail of type '{seed['risk_fact']}'" if seed["risk_fact"] else
                       "null by design (this character has no hidden risk detail; do not fill it)"),
        generated=json.dumps({"persona": persona, "scene": scene}, ensure_ascii=False, indent=1)))
    out["cost"] += c
    if check and check.get("verdict") == "modify":
        apply_fixes(persona, scene, check.get("fixes"))
    out.update(persona=persona, scene=scene, check=check or {"verdict": "check_failed", "raw": raw[:500]})
    return out


def dedup(path):
    """배경·핵심 고통 글자 3-gram TF-IDF 코사인 ≥ 0.9 쌍을 찾아 뒤쪽을 dup 으로 표시한다."""
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    rows = [json.loads(l) for l in open(path)]
    ok = [i for i, r in enumerate(rows) if r.get("scene")]
    texts = [rows[i]["scene"]["core_concern"] + " " + rows[i]["scene"]["background"] for i in ok]
    sim = cosine_similarity(TfidfVectorizer(analyzer="char", ngram_range=(3, 3)).fit_transform(texts))
    dups = 0
    for a in range(len(ok)):
        for b in range(a + 1, len(ok)):
            if sim[a, b] >= DEDUP_THRESHOLD and not rows[ok[b]].get("dup_of"):
                rows[ok[b]]["dup_of"] = rows[ok[a]]["id"]
                dups += 1
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"중복 {dups}개 표시 / {len(ok)}개")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", help="build_profile.py 출력 (.jsonl) 또는 목록 (.json)")
    ap.add_argument("--model", default="openai/gpt-6-luna")
    ap.add_argument("--check-model", default="openai/gpt-6-sol")
    ap.add_argument("--out")
    ap.add_argument("--limit", type=int)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--dedup", help="생성 결과 파일에 중복 표시만 한다")
    ap.add_argument("--redo-reject", action="store_true", help="검수 reject·check_failed 도 다시 생성한다")
    args = ap.parse_args()
    if args.dedup:
        return dedup(args.dedup)

    text = open(args.seeds).read()
    seeds = json.loads(text) if args.seeds.endswith(".json") else [json.loads(l) for l in text.splitlines() if l]
    seeds = seeds[: args.limit] if args.limit else seeds
    # 끝난 것은 하나씩 바로 쓰고, 다시 실행하면 오류 없이 끝난 id 는 건너뛴다 (이어 돌리기)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    done = {}
    if os.path.exists(args.out):
        for line in open(args.out):
            r = json.loads(line)
            verdict = (r.get("check") or {}).get("verdict")
            if not r.get("error") and not (args.redo_reject and verdict in ("reject", "check_failed")):
                done[r["id"]] = r
    todo = [s for s in seeds if s["id"] not in done]
    print(f"{len(done)}개 완료됨, {len(todo)}개 생성", flush=True)
    session = requests.Session()
    session.headers["Authorization"] = f"Bearer {api_key()}"
    session.mount("https://", requests.adapters.HTTPAdapter(pool_maxsize=args.workers))
    with open(args.out, "w") as f:
        for r in done.values():
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        with ThreadPoolExecutor(args.workers) as ex:
            futures = [ex.submit(generate, session, s, args.model, args.check_model) for s in todo]
            for i, fut in enumerate(as_completed(futures), 1):
                r = fut.result()
                done[r["id"]] = r
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                f.flush()
                if i % 25 == 0:
                    print(f"  {i}/{len(todo)}", flush=True)
    results = list(done.values())
    verdicts = {}
    for r in results:
        v = r["error"]["step"] + "_failed" if r["error"] else (r.get("check") or {}).get("verdict")
        verdicts[v] = verdicts.get(v, 0) + 1
    print(f"{args.model}: {len(results)}개, 판정 {verdicts}, 비용 ${sum(r['cost'] for r in results):.4f} → {args.out}")


if __name__ == "__main__":
    main()
