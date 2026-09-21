#!/usr/bin/env python3
"""Audit the Codex-RFT SFT data and build diagnostic/probe subsets."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
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
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            if not isinstance(row, dict):
                raise ValueError(f"line {line_number} is not an object")
            rows.append(row)
    if not rows:
        raise ValueError(f"empty JSONL: {path}")
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def percentile(sorted_values: list[int], q: float) -> int:
    return sorted_values[max(0, min(len(sorted_values) - 1, math.ceil(q * len(sorted_values)) - 1))]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset-dir", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--max-length", type=int, default=40960)
    args = parser.parse_args()

    dataset_dir = args.dataset_dir.resolve()
    model = args.model.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    train_path = dataset_dir / "train.jsonl"
    manifest_path = dataset_dir / "manifest.json"
    validation_path = dataset_dir / "validation.json"

    source_validation = json.loads(validation_path.read_text(encoding="utf-8"))
    if source_validation.get("status") != "PASS":
        raise ValueError("source dataset validation status is not PASS")
    if source_validation.get("task_count") != 90 or source_validation.get("decision_sample_count") != 1170:
        raise ValueError("unexpected source dataset counts")

    rows = read_jsonl(train_path)
    if len(rows) != 1170:
        raise ValueError(f"expected 1170 rows, found {len(rows)}")
    ids = [str(row["id"]) for row in rows]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate sample ids")

    task_rows: dict[str, list[dict[str, Any]]] = {}
    source_hashes: set[str] = set()
    for row in rows:
        metadata = row.get("metadata") or {}
        task_id = metadata.get("task_id")
        if not task_id:
            raise ValueError(f"missing metadata.task_id: {row['id']}")
        if metadata.get("loss_policy") != "assistant_completion_only":
            raise ValueError(f"unexpected loss policy: {row['id']}")
        if metadata.get("official_evaluation_success") is not True:
            raise ValueError(f"non-success source entered training: {row['id']}")
        if len(row.get("completion") or []) != 1 or row["completion"][0].get("role") != "assistant":
            raise ValueError(f"invalid completion: {row['id']}")
        task_rows.setdefault(str(task_id), []).append(row)
        source_hashes.add(str(metadata.get("source_trajectory_sha256")))
    if len(task_rows) != 90 or len(source_hashes) != 90:
        raise ValueError(f"expected 90 tasks/trajectories, found {len(task_rows)}/{len(source_hashes)}")

    tokenizer = AutoTokenizer.from_pretrained(
        model, local_files_only=True, use_fast=True, padding_side="right"
    )
    rendered: list[tuple[int, int, dict[str, Any]]] = []
    for row in rows:
        tools = row.get("tools") or None
        prompt_ids = tokenizer.apply_chat_template(
            row["prompt"], tools=tools, tokenize=True, add_generation_prompt=True,
            enable_thinking=False,
        )
        full_ids = tokenizer.apply_chat_template(
            row["prompt"] + row["completion"], tools=tools, tokenize=True,
            add_generation_prompt=False, enable_thinking=False,
        )
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError(f"chat-template prefix mismatch: {row['id']}")
        completion_tokens = len(full_ids) - len(prompt_ids)
        if completion_tokens <= 0:
            raise ValueError(f"empty rendered completion: {row['id']}")
        rendered.append((len(full_ids), completion_tokens, row))
    rendered.sort(key=lambda item: (-item[0], item[2]["id"]))
    if rendered[0][0] > args.max_length:
        raise ValueError(f"longest sample {rendered[0][0]} exceeds max length {args.max_length}")

    diagnostic_rows = [
        max(group, key=lambda row: (int(row["metadata"]["step_index"]), row["id"]))
        for _, group in sorted(task_rows.items())
    ]
    probe_rows = [item[2] for item in rendered[:2]]
    diagnostic_path = output_dir / "diagnostic_last_step_per_task.jsonl"
    probe_path = output_dir / "probe_two_longest.jsonl"
    write_jsonl(diagnostic_path, diagnostic_rows)
    write_jsonl(probe_path, probe_rows)

    token_lengths = sorted(item[0] for item in rendered)
    completion_lengths = sorted(item[1] for item in rendered)
    config = {
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "base_model": str(model),
        "dataset_dir": str(dataset_dir),
        "train_json": str(train_path),
        "dataset_manifest_sha256": sha256_file(manifest_path),
        "dataset_validation_sha256": sha256_file(validation_path),
        "train_sha256": sha256_file(train_path),
        "train_tasks": len(task_rows),
        "train_trajectories": len(source_hashes),
        "train_decision_samples": len(rows),
        "diagnostic_validation_samples": len(diagnostic_rows),
        "diagnostic_validation_sha256": sha256_file(diagnostic_path),
        "diagnostic_policy": "Each task's final decision; all 90 rows also occur in training, so loss is pipeline/fit diagnostic only, never a generalization metric.",
        "source_guards": source_validation.get("source_verification", {}),
        "difficulty": source_validation.get("difficulty", {}),
        "max_length": args.max_length,
        "native_max_position_embeddings": int(json.loads((model / "config.json").read_text(encoding="utf-8"))["max_position_embeddings"]),
        "enable_thinking": False,
        "loss_policy": "assistant_completion_only",
        "epochs": 5,
        "per_gpu_batch_size": 1,
        "world_size": 2,
        "global_batch_size": 2,
        "learning_rate": 0.0002,
        "weight_decay": 0.0,
        "optimizer": "AdamW",
        "lora_r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.0,
        "seed": 20260921,
        "attention": "sdpa",
        "dtype": "bfloat16",
        "probe_samples": [
            {"id": row["id"], "tokens": total, "completion_tokens": completion}
            for total, completion, row in rendered[:2]
        ],
        "token_lengths": {
            "min": token_lengths[0],
            "p50": percentile(token_lengths, 0.50),
            "p95": percentile(token_lengths, 0.95),
            "max": token_lengths[-1],
            "mean": sum(token_lengths) / len(token_lengths),
            "over_16384": sum(value > 16384 for value in token_lengths),
            "over_32768": sum(value > 32768 for value in token_lengths),
            "over_40960": sum(value > 40960 for value in token_lengths),
        },
        "completion_lengths": {
            "min": completion_lengths[0],
            "p50": percentile(completion_lengths, 0.50),
            "p95": percentile(completion_lengths, 0.95),
            "max": completion_lengths[-1],
            "mean": sum(completion_lengths) / len(completion_lengths),
        },
    }
    (output_dir / "training_config.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(config, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
