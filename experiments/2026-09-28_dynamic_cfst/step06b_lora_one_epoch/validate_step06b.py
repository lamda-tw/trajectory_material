#!/usr/bin/env python3
"""Validate, reload, and summarize the three trained Dynamic-CFST adapters."""

from __future__ import annotations

import gc
from collections import Counter
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch
from peft import PeftModel
from safetensors.torch import load_file
from transformers import AutoModelForCausalLM, AutoTokenizer

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
BRANCHES = ["CFST-state", "CFST-Action", "CFST-Mixed"]
EXPECTED = {
    "CFST-state": {"unique": 12, "examples": 12, "steps": 6, "tokens": 1826},
    "CFST-Action": {"unique": 8, "examples": 8, "steps": 4, "tokens": 1493},
    "CFST-Mixed": {"unique": 20, "examples": 20, "steps": 10, "tokens": 3319},
}
SOURCE = ROOT / "experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter"
BASE = Path("/root/autodl-tmp/models/Qwen3-8B")
SOURCE_HASH = "c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def add_check(checks: list[dict[str, Any]], name: str, condition: bool, detail: Any = None) -> None:
    checks.append({"name": name, "passed": bool(condition), "detail": detail})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def tensor_delta(source_path: Path, final_path: Path) -> dict[str, Any]:
    source = load_file(source_path, device="cpu")
    final = load_file(final_path, device="cpu")
    if set(source) != set(final):
        raise AssertionError("adapter tensor keys differ")
    changed = 0
    squared = 0.0
    max_abs = 0.0
    for key in sorted(source):
        delta = final[key].float() - source[key].float()
        if torch.count_nonzero(delta).item():
            changed += 1
        squared += torch.sum(delta.double() * delta.double()).item()
        max_abs = max(max_abs, torch.max(torch.abs(delta)).item())
    count = sum(value.numel() for value in source.values())
    del source, final
    gc.collect()
    return {
        "tensor_count": len(load_file(final_path, device="cpu")),
        "changed_tensor_count": changed,
        "parameter_count": count,
        "l2_delta": math.sqrt(squared),
        "max_abs_delta": max_abs,
    }


def reload_forward(adapter_paths: dict[str, Path]) -> dict[str, Any]:
    tokenizer = AutoTokenizer.from_pretrained(SOURCE, local_files_only=True, use_fast=True)
    messages = [{"role": "user", "content": "Reply with the single word OK."}]
    input_ids = tokenizer.apply_chat_template(
        messages, tokenize=True, add_generation_prompt=True, enable_thinking=False,
        return_tensors="pt",
    ).to("cuda:0")
    attention_mask = torch.ones_like(input_ids)
    base = AutoModelForCausalLM.from_pretrained(
        BASE, local_files_only=True, dtype=torch.bfloat16,
        low_cpu_mem_usage=True, attn_implementation="sdpa",
    ).to("cuda:0")
    model = PeftModel.from_pretrained(
        base, adapter_paths["CFST-state"], adapter_name="state", is_trainable=False
    )
    model.load_adapter(adapter_paths["CFST-Action"], adapter_name="action", is_trainable=False)
    model.load_adapter(adapter_paths["CFST-Mixed"], adapter_name="mixed", is_trainable=False)
    model.eval()
    result: dict[str, Any] = {}
    for branch, adapter_name in [
        ("CFST-state", "state"), ("CFST-Action", "action"), ("CFST-Mixed", "mixed")
    ]:
        model.set_adapter(adapter_name)
        with torch.no_grad(), torch.autocast(device_type="cuda", dtype=torch.bfloat16):
            logits = model(input_ids=input_ids, attention_mask=attention_mask, use_cache=False).logits[:, -1, :]
        finite = bool(torch.isfinite(logits).all().item())
        raw = logits.detach().float().cpu().numpy().tobytes()
        result[branch] = {
            "adapter_name": adapter_name,
            "input_tokens": int(input_ids.numel()),
            "output_logits_shape": list(logits.shape),
            "all_logits_finite": finite,
            "last_token_logits_sha256_float32": hashlib.sha256(raw).hexdigest(),
        }
    del model, base, input_ids, attention_mask
    gc.collect()
    torch.cuda.empty_cache()
    return result


def main() -> None:
    plan = json.loads((OUT / "training_plan.json").read_text(encoding="utf-8"))
    checks: list[dict[str, Any]] = []
    add_check(checks, "training_plan_frozen", plan["status"] == "FROZEN_NOT_YET_TRAINED", plan["status"])
    add_check(checks, "source_adapter_hash", sha256_file(SOURCE / "adapter_model.safetensors") == SOURCE_HASH, SOURCE_HASH)
    add_check(checks, "training_code_identical_to_previous", plan["old_trainer_identical"] and sha256_file(OUT / "train_cfst_branch.py") == plan["trainer_sha256"] == sha256_file(OUT.parent / "step06_lora_branches/train_cfst_branch.py"))
    add_check(checks, "one_epoch_policy", plan["training_amount_policy"] == {"epochs": 1, "each_unique_sample_count": 1, "equal_tokens_required": False, "no_check30_or_dev57": True})
    guard = json.loads((OUT / "old_results_guard.json").read_text())
    for path, expected_hash in guard["files_sha256"].items():
        add_check(checks, "old_result_unchanged:" + path, Path(path).is_file() and sha256_file(Path(path)) == expected_hash)
    source_manifest = json.loads((OUT / "source_adapter_manifest.json").read_text())
    for filename, expected_hash in source_manifest["files_sha256"].items():
        add_check(checks, "source_file_unchanged:" + filename, sha256_file(SOURCE / filename) == expected_hash)
    exposures = {}
    metrics_by_branch: dict[str, Any] = {}
    adapter_paths: dict[str, Path] = {}
    deltas: dict[str, Any] = {}
    final_hashes: list[str] = []

    for branch in BRANCHES:
        expected = EXPECTED[branch]
        branch_dir = OUT / branch
        config = json.loads((branch_dir / "training_config.json").read_text(encoding="utf-8"))
        metrics = json.loads((branch_dir / "metrics.json").read_text(encoding="utf-8"))
        history = read_jsonl(branch_dir / "loss_history.jsonl")
        schedule = read_jsonl(branch_dir / "train_schedule.jsonl")
        unique = read_jsonl(Path(config["unique_train_json"]))
        unique_by_id = {row["id"]: row for row in unique}
        add_check(checks, f"{branch}_frozen_unique_data_hash", sha256_file(Path(config["unique_train_json"])) == config["unique_train_sha256"])
        add_check(checks, f"{branch}_exactly_one_epoch_config", config["epochs"] == 1 and config["full_cycles"] == 1 and config["partial_cycle_examples"] == 0)
        for scheduled in schedule:
            source_id = scheduled["metadata"]["step06_schedule"]["source_training_id"]
            original = unique_by_id[source_id]
            copy = json.loads(json.dumps(scheduled))
            copy["id"] = source_id
            del copy["metadata"]["step06_schedule"]
            add_check(checks, f"{branch}_unchanged_sample:{source_id}", copy == original)
        actual_samples = [sample for row in history for sample in row["samples"]]
        exposure_counts = Counter(sample["source_training_id"] for sample in actual_samples)
        add_check(checks, f"{branch}_actual_sample_exposure_exactly_once", exposure_counts == Counter({key: 1 for key in unique_by_id}), dict(exposure_counts))
        add_check(checks, f"{branch}_history_matches_metrics", history == metrics["training"]["history"])
        partition = json.loads((branch_dir / "expected_rank_partition.json").read_text())
        for rank in (0, 1):
            expected_ids = [schedule[index]["id"] for index in partition[str(rank)]]
            actual_ids = [row["samples"][rank]["id"] for row in history]
            add_check(checks, f"{branch}_rank{rank}_actual_order", actual_ids == expected_ids, actual_ids)
        cumulative = 0
        for step, event in enumerate(history, 1):
            count = sum(sample["completion_tokens"] for sample in event["samples"])
            cumulative += count
            add_check(checks, f"{branch}_update_{step}_count_and_tokens", len(event["samples"]) == 2 and event["step"] == step and count == event["supervised_tokens"] and cumulative == event["cumulative_supervised_tokens"])
        add_check(checks, f"{branch}_actual_input_tokens", sum(row["tokens"] for row in actual_samples) == config["one_epoch_input_tokens"])
        add_check(checks, f"{branch}_actual_prompt_tokens", sum(row["prompt_tokens"] for row in actual_samples) == config["one_epoch_prompt_tokens"])
        add_check(checks, f"{branch}_diagnostic_target_tokens", metrics["diagnostic"]["completion_target_tokens"] == expected["tokens"])
        exposures[branch] = {
            "sample_counts": dict(exposure_counts), "all_samples_exactly_once": True,
            "actual_examples": len(actual_samples), "optimizer_updates": len(history),
            "supervised_tokens": cumulative,
            "input_tokens_unpadded": sum(row["tokens"] for row in actual_samples),
            "input_tokens_padded": sum(8 * math.ceil(row["tokens"] / 8) for row in actual_samples),
            "prompt_tokens": sum(row["prompt_tokens"] for row in actual_samples),
            "rank_partition_verified": True,
        }
        adapter = branch_dir / "adapter"
        adapter_weights = adapter / "adapter_model.safetensors"
        adapter_config = json.loads((adapter / "adapter_config.json").read_text(encoding="utf-8"))
        adapter_hash = sha256_file(adapter_weights)
        metrics_by_branch[branch] = metrics
        adapter_paths[branch] = adapter
        final_hashes.append(adapter_hash)

        add_check(checks, f"{branch}_status_success", metrics["status"] == "SUCCESS", metrics["status"])
        add_check(checks, f"{branch}_source_hash_same", metrics["source"]["adapter_model_sha256"] == SOURCE_HASH, metrics["source"])
        add_check(checks, f"{branch}_model_weights_reused", metrics["source"]["model_weights_reused"] is True, metrics["source"])
        add_check(checks, f"{branch}_optimizer_state_new", metrics["source"]["optimizer_state_reused"] is False, metrics["source"])
        add_check(checks, f"{branch}_unique_count", config["unique_sample_count"] == expected["unique"], config["unique_sample_count"])
        add_check(checks, f"{branch}_schedule_count", len(schedule) == expected["examples"], len(schedule))
        add_check(checks, f"{branch}_schedule_ids_unique", len({row["id"] for row in schedule}) == len(schedule), None)
        add_check(checks, f"{branch}_schedule_hash", sha256_file(branch_dir / "train_schedule.jsonl") == config["schedule_sha256"], config["schedule_sha256"])
        add_check(checks, f"{branch}_optimizer_steps", metrics["training"]["optimizer_steps"] == expected["steps"] == len(history), metrics["training"]["optimizer_steps"])
        add_check(checks, f"{branch}_supervised_tokens", metrics["data"]["scheduled_supervised_tokens"] == expected["tokens"], metrics["data"]["scheduled_supervised_tokens"])
        add_check(checks, f"{branch}_history_tokens", history[-1]["cumulative_supervised_tokens"] == expected["tokens"], history[-1]["cumulative_supervised_tokens"])
        add_check(checks, f"{branch}_finite_losses", all(math.isfinite(row["loss"]) for row in history), None)
        add_check(checks, f"{branch}_diagnostic_finite", math.isfinite(metrics["diagnostic"]["loss"]), metrics["diagnostic"]["loss"])
        add_check(checks, f"{branch}_adapter_hash_matches", adapter_hash == metrics["artifacts"]["adapter_model_sha256"], adapter_hash)
        add_check(checks, f"{branch}_adapter_changed", adapter_hash != SOURCE_HASH and metrics["artifacts"]["adapter_differs_from_source"] is True, adapter_hash)
        add_check(checks, f"{branch}_base_model_preserved", adapter_config["base_model_name_or_path"] == str(BASE), adapter_config["base_model_name_or_path"])
        add_check(checks, f"{branch}_lora_rank", int(adapter_config["r"]) == 8 and int(adapter_config["lora_alpha"]) == 16, {"r": adapter_config["r"], "alpha": adapter_config["lora_alpha"]})
        add_check(checks, f"{branch}_only_lora_trainable", metrics["model"]["trainable_parameters"] == 21_823_488, metrics["model"]["trainable_parameters"])
        deltas[branch] = tensor_delta(SOURCE / "adapter_model.safetensors", adapter_weights)
        add_check(checks, f"{branch}_nonzero_weight_delta", deltas[branch]["l2_delta"] > 0 and deltas[branch]["changed_tensor_count"] > 0, deltas[branch])

    add_check(checks, "final_adapter_hashes_distinct", len(set(final_hashes)) == 3, final_hashes)
    budgets = [EXPECTED[name]["tokens"] for name in BRANCHES]
    add_check(checks, "natural_unequal_training_amounts", budgets == [1826, 1493, 3319], budgets)
    common_keys = ["base_model", "source_adapter", "seed", "max_length", "learning_rate", "weight_decay", "world_size", "global_batch_size"]
    configs = {name: json.loads((OUT / name / "training_config.json").read_text()) for name in BRANCHES}
    for key in common_keys:
        add_check(checks, f"common_config_{key}", len({json.dumps(configs[name][key], sort_keys=True) for name in BRANCHES}) == 1, {name: configs[name][key] for name in BRANCHES})

    old_common = json.loads((OUT.parent / "step06_lora_branches/training_plan.json").read_text())["common_training"]
    unchanged_keys = ["base_model", "source_adapter", "seed", "max_length", "enable_thinking", "loss_policy", "optimizer", "learning_rate", "weight_decay", "scheduler", "warmup_steps", "dtype", "attention", "world_size", "per_gpu_batch_size", "global_batch_size", "gradient_accumulation_steps", "gradient_checkpointing"]
    for key in unchanged_keys:
        add_check(checks, f"same_as_previous_setting:{key}", all(configs[name][key] == old_common[key] for name in BRANCHES), configs[BRANCHES[0]][key])
    (OUT / "sample_exposure_audit.json").write_text(json.dumps({"status": "PASS", "branches": exposures}, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"event": "static_audit_passed", "checks": len(checks), "next": "reload_three_adapters"}), flush=True)
    reload_results = reload_forward(adapter_paths)
    for branch in BRANCHES:
        add_check(checks, f"{branch}_reload_forward_finite", reload_results[branch]["all_logits_finite"] is True, reload_results[branch])
    reload_hashes = [reload_results[name]["last_token_logits_sha256_float32"] for name in BRANCHES]
    add_check(checks, "reloaded_branch_logits_distinct", len(set(reload_hashes)) == 3, reload_hashes)
    reload_validation = {
        "schema_version": "dynamic-cfst-step06b-one-epoch-reload-validation-v1",
        "status": "PASS",
        "base_model": str(BASE),
        "prompt": "Reply with the single word OK.",
        "branches": reload_results,
    }
    (OUT / "reload_validation.json").write_text(json.dumps(reload_validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary_branches: dict[str, Any] = {}
    for branch in BRANCHES:
        metrics = metrics_by_branch[branch]
        summary_branches[branch] = {
            "exposure": exposures[branch],
            "adapter_dir": metrics["artifacts"]["adapter_dir"],
            "adapter_model_sha256": metrics["artifacts"]["adapter_model_sha256"],
            "unique_samples": metrics["data"]["unique_samples"],
            "scheduled_examples": metrics["data"]["scheduled_examples"],
            "supervised_tokens": metrics["data"]["scheduled_supervised_tokens"],
            "optimizer_steps": metrics["training"]["optimizer_steps"],
            "loss_first": metrics["training"]["loss_first"],
            "loss_last": metrics["training"]["loss_last"],
            "loss_mean": metrics["training"]["loss_mean"],
            "diagnostic_loss": metrics["diagnostic"]["loss"],
            "duration_seconds": metrics["training"]["duration_seconds"],
            "peak_reserved_gib_max": max(row["peak_reserved_gib"] for row in metrics["distributed"]["gpus"]),
            "weight_delta": deltas[branch],
            "reload_forward": reload_results[branch],
        }
    summary = {
        "schema_version": "dynamic-cfst-step06b-one-epoch-summary-v1",
        "status": "SUCCESS",
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": {
            "base_model": str(BASE),
            "adapter": str(SOURCE),
            "adapter_model_sha256": SOURCE_HASH,
            "model_weights_reused_for_every_branch": True,
            "optimizer_state_reused": False,
        },
        "common_training": {
            "learning_rate": 2e-4,
            "weight_decay": 0.0,
            "optimizer": "AdamW",
            "scheduler": "none_constant",
            "warmup_steps": 0,
            "seed": 20260928,
            "max_length": 40960,
            "dtype": "bfloat16",
            "attention": "sdpa",
            "world_size": 2,
            "global_batch_size": 2,
            "loss_policy": "assistant_completion_only, globally weighted by supervised tokens per DDP step",
        },
        "training_amount_policy": plan["training_amount_policy"],
        "old_result_files_unchanged": len(guard["files_sha256"]),
        "branches": summary_branches,
        "validation": {
            "checks_passed": len(checks),
            "checks_total": len(checks),
            "reload_forward_passed": True,
        },
        "scope_note": "training and overlapping-package diagnostic only; no check30 or Dev57 evaluation was run",
    }
    (OUT / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    validation = {
        "schema_version": "dynamic-cfst-step06b-one-epoch-validation-v1",
        "status": "PASS",
        "checks_passed": len(checks),
        "checks_total": len(checks),
        "checks": checks,
    }
    (OUT / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    core_paths = [
        OUT / "training_plan.json", OUT / "source_adapter_manifest.json",
        OUT / "summary.json", OUT / "validation.json", OUT / "reload_validation.json",
    ]
    for branch in BRANCHES:
        core_paths.extend([
            OUT / branch / "training_config.json", OUT / branch / "train_schedule.jsonl",
            OUT / branch / "metrics.json", OUT / branch / "loss_history.jsonl",
            OUT / branch / "adapter/adapter_config.json",
            OUT / branch / "adapter/adapter_model.safetensors",
        ])
    hashes = {str(path.relative_to(OUT)): sha256_file(path) for path in core_paths}
    (OUT / "artifact_sha256.json").write_text(
        json.dumps({"algorithm": "sha256", "files": hashes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({
        "status": "PASS", "checks": len(checks),
        "adapter_hashes": {name: summary_branches[name]["adapter_model_sha256"] for name in BRANCHES},
        "budgets": {name: summary_branches[name]["supervised_tokens"] for name in BRANCHES},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
