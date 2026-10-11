"""회복 챗봇 LoRA SFT (Qwen3-8B). 데이터: chatbot/sim/build_sft.py 출력.

입력 = 챗봇이 실제로 받는 형식 그대로 (짧은 시스템 프롬프트 + 대화 + 마지막 사용자 메시지 뒤 [guardrail: 모드] 지시).
Qwen3 생각 모드는 끈 템플릿(enable_thinking=False)으로 만들고, 손실은 정답 답변에만 건다.

  accelerate launch --num_processes 8 train_sft.py --data train.jsonl --out lora_sft_v1
"""

import argparse
import json
import math
import os
import random

import torch

from datasets import Dataset
from peft import LoraConfig
from transformers import AutoTokenizer
from trl import SFTConfig, SFTTrainer


RISK_MODES = {"support", "assess", "urgent", "other"}


def load(path, tok, max_len, oversample=1, seed=0):
    """oversample: 위험 모드(support/assess/urgent/other) 턴을 몇 번 반복할지. 데이터의 ~90% 가 normal 이라서"""
    rows = []
    for line in open(path):
        s = json.loads(line)
        repeat = oversample if s.get("meta", {}).get("response") in RISK_MODES else 1
        msgs = s["messages"]
        prompt = tok.apply_chat_template(msgs[:-1], tokenize=False, add_generation_prompt=True, enable_thinking=False)
        completion = msgs[-1]["content"] + tok.eos_token  # <|im_end|>
        if len(tok(prompt + completion).input_ids) > max_len:
            continue  # 자르면 정답이 잘려 나가므로 버린다
        rows.extend({"prompt": prompt, "completion": completion} for _ in range(repeat))
    random.Random(seed).shuffle(rows)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="Qwen/Qwen3-8B")
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--epochs", type=float, default=2)
    ap.add_argument("--lr", type=float, default=1e-4)
    ap.add_argument("--rank", type=int, default=16)
    ap.add_argument("--max_len", type=int, default=4096)
    ap.add_argument("--batch", type=int, default=1, help="GPU 당")
    ap.add_argument("--grad_accum", type=int, default=4)
    ap.add_argument("--eval_frac", type=float, default=0.03)
    ap.add_argument("--max_steps", type=int, default=-1, help="점검용 (예: 2)")
    ap.add_argument("--oversample", type=int, default=3, help="위험 모드 턴 반복 횟수")
    args = ap.parse_args()

    tok = AutoTokenizer.from_pretrained(args.model)
    rows = load(args.data, tok, args.max_len, args.oversample)
    n_eval = max(1, int(len(rows) * args.eval_frac))
    train, evals = Dataset.from_list(rows[n_eval:]), Dataset.from_list(rows[:n_eval])
    print(f"학습 {len(train)} · 검증 {len(evals)}")
    world = int(os.environ.get("WORLD_SIZE", 1))  # transformers 5 에는 warmup_ratio 가 없다 → 3% 를 스텝으로
    total = math.ceil(len(train) * args.epochs / (args.batch * args.grad_accum * world))
    warmup = max(1, int(0.03 * (args.max_steps if args.max_steps > 0 else total)))

    cfg = SFTConfig(
        output_dir=args.out, num_train_epochs=args.epochs, learning_rate=args.lr, lr_scheduler_type="cosine",
        warmup_steps=warmup, per_device_train_batch_size=args.batch, per_device_eval_batch_size=args.batch,
        gradient_accumulation_steps=args.grad_accum, gradient_checkpointing=True, bf16=torch.cuda.is_available(),
        max_steps=args.max_steps, use_cpu=not torch.cuda.is_available(),
        max_length=args.max_len, completion_only_loss=True, logging_steps=10, eval_strategy="steps",
        eval_steps=100, save_strategy="steps", save_steps=200, save_total_limit=3, report_to="none",
        ddp_find_unused_parameters=False, seed=0,
        # fp32 로 읽으면 프로세스당 RAM ~33GB → 8개면 54번(251GB)에서 OOM. bf16 으로 읽는다
        model_init_kwargs={"dtype": torch.bfloat16 if torch.cuda.is_available() else torch.float32})
    lora = LoraConfig(r=args.rank, lora_alpha=2 * args.rank, lora_dropout=0.05, task_type="CAUSAL_LM",
                      target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"])
    trainer = SFTTrainer(model=args.model, args=cfg, train_dataset=train, eval_dataset=evals,
                         processing_class=tok, peft_config=lora)
    trainer.train()
    trainer.save_model(args.out)
    tok.save_pretrained(args.out)
    print("SAVED", args.out)


if __name__ == "__main__":
    main()
