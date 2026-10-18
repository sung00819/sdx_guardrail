"""rlver GRPO 한 반복 (84번 GPU 3–6). rlver_rl.py 가 만든 턴 샘플로 Qwen3-8B LoRA 를 업데이트한다.
../../gym/train/gym_grpo_step.py 를 가져와 rlver 에 맞췄다: 자체 생각 블록(<think>…</think>)이 답에 들어가므로
--native_think 면 프롬프트를 enable_thinking=True 로 만든다 (vLLM 이 생성할 때와 같은 토큰). RLVER 설정: KL 0 (기본 beta 0),
미니배치 1 (ppo_mini_batch_size = train_batch_size = 32 → 반복마다 업데이트 한 번).

샘플 = 챗봇이 실제로 받은 입력(시스템 + 대화) + 챗봇 원문 답(생각 블록 포함) + 이점. 손실은 챗봇 토큰에만.
이점 = 같은 사용자(배경 × 설정) 그룹 안에서 (r − 평균) / 표준편차, 에피소드의 모든 턴에 같은 값.

손실 (토큰 단위):
  ratio = exp(logp − logp_old)                     logp_old: 업데이트 전 정책 (= 롤아웃 정책)
  pg    = −min(ratio·A, clip(ratio, 1±ε)·A)
  kl    = exp(logp_ref − logp) − (logp_ref − logp) − 1   기준 = 어댑터를 끈 원래 Qwen3-8B
  loss  = Σ (pg + β·kl) / 전체 완성 토큰 수

  accelerate launch --num_processes 4 grpo_step.py --model Qwen/Qwen3-8B --batch b.jsonl --policy_in none --out r1/it001 --native_think
"""

import argparse
import json
import math
import os
import random

import torch
import torch.distributed as dist
from accelerate import Accelerator
from peft import LoraConfig, PeftModel, get_peft_model
from transformers import AutoModelForCausalLM, AutoTokenizer

TARGETS = ["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"]


def encode(tok, rows, max_len, native_think=False):
    out, skipped = [], 0
    for r in rows:
        prompt = tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True,
                                         enable_thinking=native_think)
        p_ids = tok(prompt, add_special_tokens=False).input_ids
        c_ids = tok(r["completion"] + tok.eos_token, add_special_tokens=False).input_ids
        if len(p_ids) + len(c_ids) > max_len:
            skipped += 1
            continue
        out.append({"ids": p_ids + c_ids, "n_c": len(c_ids), "adv": float(r["adv"])})
    return out, skipped


def logps(model, ids, n_c, device):
    """완성 토큰의 log p. 마지막 n_c+1 위치의 logits 만 계산 (어휘 15만 × 길이 메모리를 피한다)"""
    x = torch.tensor([ids], device=device)
    logits = model(input_ids=x, logits_to_keep=n_c + 1).logits[0, :-1].float()
    return torch.log_softmax(logits, -1).gather(-1, x[0, -n_c:, None])[:, 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--batch", required=True)
    ap.add_argument("--policy_in", default="none", help="이번 반복의 시작 어댑터 (롤아웃에 쓴 것). none = 새 LoRA")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--beta", type=float, default=0.0, help="RLVER kl_coef 0")
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--rank", type=int, default=16, help="vLLM --max-lora-rank 16 이하")
    ap.add_argument("--minibatches", type=int, default=1, help="RLVER: 배치 32 = 미니배치 32")
    ap.add_argument("--max_len", type=int, default=5120)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--native_think", action="store_true", help="답에 자체 생각 블록이 있다 (Qwen3 생각 모드)")
    args = ap.parse_args()

    acc = Accelerator(mixed_precision="bf16")
    tok = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16)
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    base.enable_input_require_grads()
    if args.policy_in == "none":
        torch.manual_seed(args.seed)  # 랭크마다 같은 초기값 (B 는 0 이라 처음 정책 = 원래 모델)
        model = get_peft_model(base, LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.0,
                                                target_modules=TARGETS, task_type="CAUSAL_LM"))
    else:
        model = PeftModel.from_pretrained(base, args.policy_in, is_trainable=True)
    for m in model.modules():  # 드롭아웃을 끈다 (같은 정책인데 ratio ≠ 1 이 되지 않게)
        if isinstance(m, torch.nn.Dropout):
            m.p = 0.0
    model.to(acc.device)
    params = [p for n, p in model.named_parameters() if "lora_" in n]
    for p in params:
        p.requires_grad = True
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    opt_path = os.path.join(args.policy_in, "optimizer.pt")
    if args.policy_in != "none" and os.path.exists(opt_path):
        opt.load_state_dict(torch.load(opt_path, map_location="cpu"))
        for g in opt.param_groups:
            g["lr"] = args.lr

    rows = [json.loads(l) for l in open(args.batch)]
    data, skipped = encode(tok, rows, args.max_len, args.native_think)
    random.Random(args.seed).shuffle(data)
    mine = data[acc.process_index::acc.num_processes]
    acc.print(f"샘플 {len(rows)} → 사용 {len(data)} (길이 초과 {skipped}, 랭크당 {len(mine)})")

    model.eval()
    with torch.no_grad():
        for s in mine:
            s["old"] = logps(model, s["ids"], s["n_c"], acc.device).cpu()
            if args.beta > 0:  # KL 0 이면 기준 모델 log p 는 필요 없다
                with model.disable_adapter():
                    s["ref"] = logps(model, s["ids"], s["n_c"], acc.device).cpu()
    acc.print("old/ref log p 완료")

    model.train()
    per = math.ceil(len(mine) / args.minibatches) if mine else 0
    st = {"pg": 0.0, "kl": 0.0, "ratio": 0.0, "clipfrac": 0.0, "tokens": 0}
    for step in range(args.minibatches):
        part = mine[step * per:(step + 1) * per]
        n_all = acc.gather(torch.tensor([sum(s["n_c"] for s in part)], device=acc.device)).sum().item()
        opt.zero_grad(set_to_none=True)
        for s in part:
            lp = logps(model, s["ids"], s["n_c"], acc.device)
            old = s["old"].to(lp.device)
            ratio = torch.exp(lp - old)
            pg = -torch.minimum(ratio * s["adv"], torch.clamp(ratio, 1 - args.clip, 1 + args.clip) * s["adv"])
            if args.beta > 0:
                d = s["ref"].to(lp.device) - lp
                kl = torch.exp(d) - d - 1
            else:
                kl = torch.zeros_like(lp)
            ((pg + args.beta * kl).sum() / max(1, n_all)).backward()
            with torch.no_grad():
                st["pg"] += pg.sum().item(); st["kl"] += kl.sum().item(); st["ratio"] += ratio.sum().item()
                st["clipfrac"] += ((ratio - 1).abs() > args.clip).float().sum().item(); st["tokens"] += s["n_c"]
        # DDP 대신 기울기를 직접 합친다: 랭크마다 샘플 수가 달라 backward 횟수가 달라도 멈추지 않게
        for p in params:
            if p.grad is None:
                p.grad = torch.zeros_like(p)
            if dist.is_initialized():
                dist.all_reduce(p.grad)
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        acc.print(f"스텝 {step + 1}/{args.minibatches}")

    keys = ("pg", "kl", "ratio", "clipfrac", "tokens")
    tot = acc.gather(torch.tensor([st[k] for k in keys], device=acc.device, dtype=torch.float64).view(1, -1)).sum(0).tolist()
    summary = {k: tot[i] / max(1, tot[4]) for i, k in enumerate(keys[:4])}
    summary.update(tokens=int(tot[4]), samples=len(data), skipped=skipped)
    acc.wait_for_everyone()
    if acc.is_main_process:
        acc.unwrap_model(model).save_pretrained(args.out)
        torch.save(opt.state_dict(), os.path.join(args.out, "optimizer.pt"))
        json.dump(summary, open(os.path.join(args.out, "step_stats.json"), "w"))
        print("STEP_DONE", json.dumps(summary))


if __name__ == "__main__":
    main()
