"""GRPO 한 번 (멀티턴 대화, 에피소드 보상). rl_batch.py 가 만든 턴 샘플로 LoRA 를 한 반복만큼 업데이트한다.

샘플 = 챗봇이 받은 입력(이번 턴 지시 형식) + 챗봇 답 + 이점(advantage). 이점은 같은 프로필 그룹 안에서
(R − 평균) / 표준편차 이고, 에피소드의 모든 턴이 같은 이점을 받는다.

손실 (토큰 단위, PPO 식 비율 자르기 + 기준 모델 KL):
  ratio = exp(logp − logp_old),  pg = −min(ratio·A, clip(ratio, 1±ε)·A)
  kl    = exp(logp_ref − logp) − (logp_ref − logp) − 1     (k3, 기준 = SFT 어댑터)
  loss  = Σ_token (pg + β·kl) / 토큰 수
logp_old 는 업데이트 전 정책(= 롤아웃에 쓴 어댑터)으로 처음에 한 번 계산한다.

  accelerate launch --num_processes 2 grpo_step.py --batch batch.jsonl --policy_in rl/it0 \\
      --ref lora_sft_v1 --out rl/it1
"""

import argparse
import json
import math
import os
import random

import torch
import torch.distributed as dist
from accelerate import Accelerator
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def encode(tok, rows, max_len):
    out = []
    for r in rows:
        prompt = tok.apply_chat_template(r["messages"], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        p_ids = tok(prompt, add_special_tokens=False).input_ids
        c_ids = tok(r["completion"] + tok.eos_token, add_special_tokens=False).input_ids
        if len(p_ids) + len(c_ids) > max_len:
            continue
        out.append({"ids": p_ids + c_ids, "n_c": len(c_ids), "adv": float(r["adv"])})
    return out


def token_logps(model, ids, n_c, device):
    """완성 토큰의 log p. 마지막 n_c+1 위치의 logits 만 계산해 어휘(15만)×길이 메모리를 피한다"""
    x = torch.tensor([ids], device=device)
    logits = model(input_ids=x, logits_to_keep=n_c + 1).logits[0, :-1].float()
    target = x[0, -n_c:]
    return torch.log_softmax(logits, -1).gather(-1, target[:, None])[:, 0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=os.path.expanduser("~/yumin_sim/models/Qwen3-8B"))
    ap.add_argument("--batch", required=True)
    ap.add_argument("--policy_in", required=True, help="이번 반복의 시작 어댑터 (롤아웃에 쓴 것). optimizer.pt 가 있으면 이어받는다")
    ap.add_argument("--ref", required=True, help="KL 기준 어댑터 (SFT)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--lr", type=float, default=1e-5)
    ap.add_argument("--beta", type=float, default=0.02)
    ap.add_argument("--clip", type=float, default=0.2)
    ap.add_argument("--minibatches", type=int, default=4, help="한 반복의 옵티마이저 스텝 수")
    ap.add_argument("--max_len", type=int, default=4096)
    ap.add_argument("--seed", type=int, default=0)
    args = ap.parse_args()

    acc = Accelerator(mixed_precision="bf16")
    tok = AutoTokenizer.from_pretrained(args.model)
    base = AutoModelForCausalLM.from_pretrained(args.model, dtype=torch.bfloat16)
    base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    base.enable_input_require_grads()
    model = PeftModel.from_pretrained(base, args.policy_in, adapter_name="default", is_trainable=True)
    model.load_adapter(args.ref, adapter_name="ref", is_trainable=False)
    model.set_adapter("default")
    for n, p in model.named_parameters():
        p.requires_grad = "lora_" in n and ".default." in n
    for m in model.modules():  # LoRA 드롭아웃을 끈다: 켜 두면 같은 정책인데도 ratio ≠ 1 이 되어 자르기가 잡음에 반응한다
        if isinstance(m, torch.nn.Dropout):
            m.p = 0.0
    model.to(acc.device)  # 옵티마이저 상태를 불러오기 전에 GPU 로 (아니면 상태가 CPU 에 남아 스텝에서 장치 오류)
    params = [p for p in model.parameters() if p.requires_grad]
    opt = torch.optim.AdamW(params, lr=args.lr, weight_decay=0.0)
    opt_path = os.path.join(args.policy_in, "optimizer.pt")
    if os.path.exists(opt_path):
        opt.load_state_dict(torch.load(opt_path, map_location="cpu"))
        for g in opt.param_groups:
            g["lr"] = args.lr

    rows = [json.loads(l) for l in open(args.batch)]
    data = encode(tok, rows, args.max_len)
    random.Random(args.seed).shuffle(data)
    mine = data[acc.process_index::acc.num_processes]  # 랭크마다 나눠 갖는다
    acc.print(f"샘플 {len(rows)} → 사용 {len(data)} (랭크당 {len(mine)})")

    # 1) 업데이트 전 정책·기준 log p
    model.eval()
    with torch.no_grad():
        for s in mine:
            s["old"] = token_logps(model, s["ids"], s["n_c"], acc.device).cpu()
            model.set_adapter("ref")
            s["ref"] = token_logps(model, s["ids"], s["n_c"], acc.device).cpu()
            model.set_adapter("default")
            for n, p in model.named_parameters():  # set_adapter 가 requires_grad 를 바꿀 수 있어 되돌린다
                p.requires_grad = "lora_" in n and ".default." in n
    acc.print("old/ref log p 완료")

    # 2) 미니배치마다 한 스텝. 랭크마다 미니배치 수를 같게 (DDP 동기화)
    model.train()
    n_steps = args.minibatches
    per = math.ceil(len(mine) / n_steps) if mine else 0
    stats = {"pg": 0.0, "kl": 0.0, "ratio": 0.0, "clipfrac": 0.0, "tokens": 0}
    for step in range(n_steps):
        part = mine[step * per:(step + 1) * per]
        n_tok = sum(s["n_c"] for s in part)
        n_tok_all = acc.gather(torch.tensor([n_tok], device=acc.device)).sum().item()
        opt.zero_grad(set_to_none=True)
        for s in part:
            lp = token_logps(model, s["ids"], s["n_c"], acc.device)
            old, ref = s["old"].to(lp.device), s["ref"].to(lp.device)
            ratio = torch.exp(lp - old)
            a = s["adv"]
            pg = -torch.minimum(ratio * a, torch.clamp(ratio, 1 - args.clip, 1 + args.clip) * a)
            d = ref - lp
            kl = torch.exp(d) - d - 1
            # 모든 랭크 토큰 합으로 나눈다. 기울기는 랭크마다 쌓았다가 스텝마다 한 번 합친다 (DDP 를 안 쓴다:
            # 랭크마다 샘플 수가 달라 backward 횟수가 달라도 멈추지 않게)
            loss = (pg + args.beta * kl).sum() / max(1, n_tok_all)
            loss.backward()
            with torch.no_grad():
                stats["pg"] += pg.sum().item(); stats["kl"] += kl.sum().item(); stats["ratio"] += ratio.sum().item()
                stats["clipfrac"] += ((ratio - 1).abs() > args.clip).float().sum().item(); stats["tokens"] += s["n_c"]
        for p in params:
            if p.grad is None:
                p.grad = torch.zeros_like(p)
            if dist.is_initialized():
                dist.all_reduce(p.grad)  # 합 (손실이 이미 전체 토큰 수로 나뉘어 있다)
        torch.nn.utils.clip_grad_norm_(params, 1.0)
        opt.step()
        acc.print(f"스텝 {step + 1}/{n_steps}")

    tot = acc.gather(torch.tensor([stats[k] for k in ("pg", "kl", "ratio", "clipfrac", "tokens")], device=acc.device,
                                  dtype=torch.float64).view(1, -1)).sum(0).tolist()
    summary = {k: tot[i] / max(1, tot[4]) for i, k in enumerate(("pg", "kl", "ratio", "clipfrac"))}
    summary.update(tokens=int(tot[4]), samples=len(data))
    acc.wait_for_everyone()
    if acc.is_main_process:
        m = acc.unwrap_model(model)
        m.save_pretrained(args.out, selected_adapters=["default"])
        torch.save(opt.state_dict(), os.path.join(args.out, "optimizer.pt"))
        json.dump(summary, open(os.path.join(args.out, "step_stats.json"), "w"))
        print("STEP_DONE", json.dumps(summary))


if __name__ == "__main__":
    main()
