#!/usr/bin/env python3
"""Validate inputs and select the two longest samples for a 32K memory probe."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise ValueError(f"empty JSONL: {path}")
    return rows


def rendered_length(tokenizer: Any, row: dict[str, Any]) -> int:
    return len(
        tokenizer.apply_chat_template(
            row["prompt"] + row["completion"],
            tools=row.get("tools") or None,
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=32768)
    args = parser.parse_args()

    dataset_dir = args.dataset_dir.resolve()
    output_dir = args.output_dir.resolve()
    train_path = dataset_dir / "train.jsonl"
    validation_path = dataset_dir / "splits" / "task_holdout_60_7" / "validation.jsonl"
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    validation = json.loads((dataset_dir / "validation.json").read_text(encoding="utf-8"))
    if validation.get("status") != "PASS":
        raise ValueError("converted dataset validation status is not PASS")
    if manifest["counts"]["tasks"] != 67 or manifest["counts"]["decision_samples"] != 640:
        raise ValueError("unexpected converted dataset counts")

    train_rows = read_jsonl(train_path)
    validation_rows = read_jsonl(validation_path)
    task_ids = {row["metadata"]["task_id"] for row in train_rows}
    validation_task_ids = {row["metadata"]["task_id"] for row in validation_rows}
    if len(task_ids) != 67 or len(validation_task_ids) != 7:
        raise ValueError("unexpected task coverage")
    if not validation_task_ids.issubset(task_ids):
        raise ValueError("diagnostic validation tasks are not a subset of all-data training")

    tokenizer = AutoTokenizer.from_pretrained(
        args.model.resolve(), local_files_only=True, use_fast=True, padding_side="right"
    )
    lengths = [(rendered_length(tokenizer, row), row) for row in train_rows]
    lengths.sort(key=lambda item: (-item[0], item[1]["id"]))
    if lengths[0][0] > args.max_length:
        raise ValueError(f"longest sample {lengths[0][0]} exceeds max length {args.max_length}")
    probe_rows = [item[1] for item in lengths[:2]]
    output_dir.mkdir(parents=True, exist_ok=True)
    probe_path = output_dir / "probe_longest.jsonl"
    with probe_path.open("w", encoding="utf-8") as handle:
        for row in probe_rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")

    config = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_model": str(args.model.resolve()),
        "dataset_dir": str(dataset_dir),
        "train_json": str(train_path),
        "diagnostic_validation_json": str(validation_path),
        "dataset_manifest_sha256": sha256_file(dataset_dir / "manifest.json"),
        "dataset_validation_sha256": sha256_file(dataset_dir / "validation.json"),
        "train_sha256": sha256_file(train_path),
        "diagnostic_validation_sha256": sha256_file(validation_path),
        "train_tasks": len(task_ids),
        "train_decision_samples": len(train_rows),
        "diagnostic_validation_tasks": len(validation_task_ids),
        "diagnostic_validation_samples": len(validation_rows),
        "validation_overlap_policy": "The 7-task validation subset is included in the 67-task all-data training set; its loss is diagnostic only. AppWorld Dev is the held-out end-to-end evaluation.",
        "max_length": args.max_length,
        "enable_thinking": False,
        "loss_policy": "assistant_completion_only",
        "epochs": 1,
        "per_gpu_batch_size": 1,
        "world_size": 2,
        "global_batch_size": 2,
        "learning_rate": 0.0002,
        "optimizer": "AdamW",
        "lora_r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.0,
        "seed": 20260915,
        "attention": "sdpa",
        "dtype": "bfloat16",
        "probe_samples": [
            {"id": row["id"], "tokens": length}
            for length, row in lengths[:2]
        ],
        "token_lengths": {
            "min": lengths[-1][0],
            "max": lengths[0][0],
            "over_16384": sum(length > 16384 for length, _ in lengths),
            "over_20480": sum(length > 20480 for length, _ in lengths),
            "over_24576": sum(length > 24576 for length, _ in lengths),
            "over_32768": sum(length > 32768 for length, _ in lengths),
        },
    }
    (output_dir / "training_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(config, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
