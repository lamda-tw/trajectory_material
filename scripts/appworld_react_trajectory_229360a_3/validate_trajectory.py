#!/usr/bin/env python3
"""Validate AppWorld ReAct JSONL against Qwen chat rendering and secret leakage."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--train-jsonl", type=Path, required=True)
    parser.add_argument("--gold-api-calls", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=8192)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    rows = [
        json.loads(line)
        for line in args.train_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tokenizer = AutoTokenizer.from_pretrained(args.model, local_files_only=True)
    stats: list[dict[str, Any]] = []
    for row in rows:
        prompt_ids = tokenizer.apply_chat_template(
            row["prompt"], tokenize=True, add_generation_prompt=True, enable_thinking=False
        )
        full_ids = tokenizer.apply_chat_template(
            row["prompt"] + row["completion"],
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError(f"chat-template prefix mismatch: {row['id']}")
        stats.append(
            {
                "id": row["id"],
                "prompt_tokens": len(prompt_ids),
                "completion_tokens": len(full_ids) - len(prompt_ids),
                "full_tokens": len(full_ids),
                "within_max_length": len(full_ids) <= args.max_length,
            }
        )

    gold_calls = json.loads(args.gold_api_calls.read_text(encoding="utf-8"))
    secret_values: set[str] = set()
    for call in gold_calls:
        for key, value in call.get("data", {}).items():
            if key in {"password", "access_token"} and isinstance(value, str):
                secret_values.add(value)
    train_text = args.train_jsonl.read_text(encoding="utf-8")
    leaked_secret_count = sum(value in train_text for value in secret_values)
    result = {
        "rows": len(rows),
        "max_length": args.max_length,
        "max_full_tokens": max(item["full_tokens"] for item in stats),
        "all_within_max_length": all(item["within_max_length"] for item in stats),
        "concrete_secret_leaks": leaked_secret_count,
        "chat_template_prefix_valid": True,
        "samples": stats,
    }
    if leaked_secret_count:
        raise RuntimeError(f"found {leaked_secret_count} concrete credential/token leaks")
    if not result["all_within_max_length"]:
        raise RuntimeError("one or more samples exceed max_length")
    text = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")


if __name__ == "__main__":
    main()
