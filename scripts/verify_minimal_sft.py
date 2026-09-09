#!/usr/bin/env python3
"""Reload the saved LoRA adapter and run one local generation smoke test."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

import torch
from peft import PeftModel
from transformers import AutoModelForCausalLM, AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--validation-json", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-input-length", type=int, default=4096)
    parser.add_argument("--max-new-tokens", type=int, default=64)
    args = parser.parse_args()

    with args.validation_json.open("r", encoding="utf-8") as handle:
        row = json.loads(next(line for line in handle if line.strip()))
    tokenizer = AutoTokenizer.from_pretrained(args.adapter, local_files_only=True, use_fast=True)
    tokenizer.truncation_side = "left"
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    base = AutoModelForCausalLM.from_pretrained(
        args.model,
        local_files_only=True,
        dtype=torch.bfloat16,
        low_cpu_mem_usage=True,
        attn_implementation="sdpa",
    ).to("cuda:0")
    model = PeftModel.from_pretrained(base, args.adapter).eval()
    prompt_text = tokenizer.apply_chat_template(
        row["prompt"],
        tools=row.get("tools") or None,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
    )
    encoded = tokenizer(
        prompt_text,
        return_tensors="pt",
        add_special_tokens=False,
        truncation=True,
        max_length=args.max_input_length,
    ).to("cuda:0")
    with torch.no_grad():
        generated = model.generate(
            **encoded,
            max_new_tokens=args.max_new_tokens,
            do_sample=False,
            use_cache=True,
            pad_token_id=tokenizer.pad_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    new_ids = generated[0, encoded["input_ids"].shape[1] :]
    text = tokenizer.decode(new_ids, skip_special_tokens=False)
    result = {
        "status": "PASS" if new_ids.numel() > 0 else "FAIL",
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "sample_id": row["id"],
        "input_tokens": int(encoded["input_ids"].shape[1]),
        "generated_tokens": int(new_ids.numel()),
        "generated_text": text,
        "adapter": str(args.adapter.resolve()),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
