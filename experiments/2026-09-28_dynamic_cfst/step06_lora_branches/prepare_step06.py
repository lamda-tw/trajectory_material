#!/usr/bin/env python3
"""Freeze matched-token schedules and configs for Dynamic-CFST Step 6."""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
STEP05 = ROOT / "experiments/2026-09-28_dynamic_cfst/step05_training_packages"
BASE_MODEL = Path("/root/autodl-tmp/models/Qwen3-8B")
SOURCE_ADAPTER = ROOT / "experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter"
SEED = 20260928
TARGET_SUPERVISED_TOKENS = 8000
MAX_LENGTH = 40960
LEARNING_RATE = 2e-4
WEIGHT_DECAY = 0.0
EXPECTED_TRAINABLE_PARAMETERS = 21_823_488
BRANCHES = ["CFST-state", "CFST-Action", "CFST-Mixed"]


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


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")


def main() -> None:
    step05_validation = json.loads((STEP05 / "validation.json").read_text(encoding="utf-8"))
    if step05_validation.get("status") != "PASS":
        raise ValueError("Step 5 validation is not PASS")
    if not (BASE_MODEL / "config.json").is_file():
        raise FileNotFoundError(BASE_MODEL / "config.json")
    source_weights = SOURCE_ADAPTER / "adapter_model.safetensors"
    if not source_weights.is_file():
        raise FileNotFoundError(source_weights)
    source_weight_hash = sha256_file(source_weights)
    if source_weight_hash != "c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938":
        raise ValueError(f"unexpected source adapter hash: {source_weight_hash}")

    source_config = json.loads((SOURCE_ADAPTER / "adapter_config.json").read_text(encoding="utf-8"))
    expected_lora = {
        "r": 8,
        "lora_alpha": 16,
        "lora_dropout": 0.0,
        "target_modules": {"q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"},
    }
    if int(source_config["r"]) != expected_lora["r"] or int(source_config["lora_alpha"]) != expected_lora["lora_alpha"]:
        raise ValueError("source adapter LoRA rank/alpha mismatch")
    if float(source_config["lora_dropout"]) != expected_lora["lora_dropout"]:
        raise ValueError("source adapter LoRA dropout mismatch")
    if set(source_config["target_modules"]) != expected_lora["target_modules"]:
        raise ValueError("source adapter target modules mismatch")

    tokenizer = AutoTokenizer.from_pretrained(
        SOURCE_ADAPTER, local_files_only=True, use_fast=True, padding_side="right"
    )
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    source_hashes = {
        path.name: sha256_file(path)
        for path in sorted(SOURCE_ADAPTER.iterdir())
        if path.is_file()
    }
    write_json(
        OUT / "source_adapter_manifest.json",
        {
            "source_adapter": str(SOURCE_ADAPTER),
            "base_model": str(BASE_MODEL),
            "files_sha256": source_hashes,
            "adapter_model_sha256": source_weight_hash,
            "lora": {
                "r": expected_lora["r"],
                "alpha": expected_lora["lora_alpha"],
                "dropout": expected_lora["lora_dropout"],
                "target_modules": sorted(expected_lora["target_modules"]),
            },
        },
    )

    common = {
        "base_model": str(BASE_MODEL),
        "source_adapter": str(SOURCE_ADAPTER),
        "source_adapter_model_sha256": source_weight_hash,
        "seed": SEED,
        "max_length": MAX_LENGTH,
        "enable_thinking": False,
        "loss_policy": "assistant_completion_only",
        "optimizer": "AdamW",
        "optimizer_state": "new_identical_state_per_branch",
        "learning_rate": LEARNING_RATE,
        "weight_decay": WEIGHT_DECAY,
        "scheduler": "constant_none",
        "warmup_steps": 0,
        "dtype": "bfloat16",
        "attention": "sdpa",
        "world_size": 2,
        "per_gpu_batch_size": 1,
        "global_batch_size": 2,
        "gradient_accumulation_steps": 1,
        "gradient_checkpointing": True,
        "target_supervised_tokens_minimum": TARGET_SUPERVISED_TOKENS,
        "stop_policy": "cycle fixed Step 5 order until target tokens reached and example count is even",
        "expected_trainable_parameters": EXPECTED_TRAINABLE_PARAMETERS,
    }
    plans: dict[str, Any] = {}

    for branch in BRANCHES:
        branch_dir = OUT / branch
        final_adapter = branch_dir / "adapter"
        if final_adapter.exists():
            raise FileExistsError(f"refusing to overwrite trained adapter: {final_adapter}")
        unique_path = STEP05 / branch / "train.jsonl"
        unique_rows = read_jsonl(unique_path)
        lengths: list[int] = []
        full_lengths: list[int] = []
        for row in unique_rows:
            prompt_ids = tokenizer.apply_chat_template(
                row["prompt"], tools=None, tokenize=True,
                add_generation_prompt=True, enable_thinking=False,
            )
            full_ids = tokenizer.apply_chat_template(
                row["prompt"] + row["completion"], tools=None, tokenize=True,
                add_generation_prompt=False, enable_thinking=False,
            )
            if full_ids[: len(prompt_ids)] != prompt_ids:
                raise ValueError(f"{row['id']}: chat-template prefix mismatch")
            if len(full_ids) > MAX_LENGTH:
                raise ValueError(f"{row['id']}: exceeds max length")
            lengths.append(len(full_ids) - len(prompt_ids))
            full_lengths.append(len(full_ids))

        schedule: list[dict[str, Any]] = []
        cumulative = 0
        cursor = 0
        while cumulative < TARGET_SUPERVISED_TOKENS or len(schedule) % 2:
            unique_index = cursor % len(unique_rows)
            cycle_index = cursor // len(unique_rows) + 1
            source_row = unique_rows[unique_index]
            row = copy.deepcopy(source_row)
            original_id = str(row["id"])
            row["id"] = f"{original_id}::schedule-{cursor + 1:04d}"
            row["metadata"] = copy.deepcopy(row["metadata"])
            row["metadata"]["step06_schedule"] = {
                "branch": branch,
                "schedule_index_1based": cursor + 1,
                "cycle_index_1based": cycle_index,
                "unique_index_1based": unique_index + 1,
                "source_training_id": original_id,
                "completion_tokens": lengths[unique_index],
            }
            schedule.append(row)
            cumulative += lengths[unique_index]
            cursor += 1

        schedule_path = branch_dir / "train_schedule.jsonl"
        write_jsonl(schedule_path, schedule)
        branch_plan = {
            "unique_sample_count": len(unique_rows),
            "unique_family_count": len({row["metadata"]["task_family"] for row in unique_rows}),
            "unique_supervised_tokens": sum(lengths),
            "scheduled_examples": len(schedule),
            "optimizer_steps": len(schedule) // 2,
            "scheduled_supervised_tokens": cumulative,
            "target_supervised_tokens_minimum": TARGET_SUPERVISED_TOKENS,
            "token_overshoot": cumulative - TARGET_SUPERVISED_TOKENS,
            "full_cycles": len(schedule) // len(unique_rows),
            "partial_cycle_examples": len(schedule) % len(unique_rows),
            "max_sequence_tokens": max(full_lengths),
            "unique_train_json": str(unique_path),
            "unique_train_sha256": sha256_file(unique_path),
            "schedule_json": str(schedule_path),
            "schedule_sha256": sha256_file(schedule_path),
            "output_adapter": str(final_adapter),
        }
        plans[branch] = branch_plan
        config = {
            "schema_version": "dynamic-cfst-step06-branch-config-v1",
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "branch": branch,
            **common,
            **branch_plan,
            "branch_dir": str(branch_dir),
            "metrics_path": str(branch_dir / "metrics.json"),
            "loss_history_path": str(branch_dir / "loss_history.jsonl"),
            "diagnostic_scope": "the unique branch package; overlaps training and is only a numerical fit check",
        }
        write_json(branch_dir / "training_config.json", config)

    token_budgets = [plans[name]["scheduled_supervised_tokens"] for name in BRANCHES]
    if max(token_budgets) - min(token_budgets) > 25:
        raise ValueError(f"matched token budgets differ too much: {token_budgets}")
    plan = {
        "schema_version": "dynamic-cfst-step06-training-plan-v1",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FROZEN_NOT_YET_TRAINED",
        "purpose": "continue the same epoch5 LoRA weights for one short CFST phase in three independent branches",
        "common_training": common,
        "branches": plans,
        "budget_comparison": {
            "minimum": min(token_budgets),
            "maximum": max(token_budgets),
            "range": max(token_budgets) - min(token_budgets),
            "relative_range_percent_of_8000": 100.0 * (max(token_budgets) - min(token_budgets)) / TARGET_SUPERVISED_TOKENS,
        },
        "step05_manifest_sha256": sha256_file(STEP05 / "manifest.json"),
        "step05_validation_sha256": sha256_file(STEP05 / "validation.json"),
        "source_adapter_manifest_sha256": sha256_file(OUT / "source_adapter_manifest.json"),
    }
    write_json(OUT / "training_plan.json", plan)
    print(json.dumps({name: plans[name] for name in BRANCHES}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
