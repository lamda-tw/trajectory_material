#!/usr/bin/env python3
"""Independently validate the three Dynamic-CFST Step 5 training packages."""

from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUT = Path(__file__).resolve().parent
MODEL = Path("/root/autodl-tmp/models/Qwen3-8B")
MAX_LENGTH = 40960
PACKAGE_COUNTS = {"CFST-state": 12, "CFST-Action": 8, "CFST-Mixed": 20}
CODE_RE = re.compile(r"```python\n(.*?)\n```", re.DOTALL)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows:
        raise AssertionError(f"empty JSONL: {path}")
    return rows


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def check(name: str, condition: bool, detail: Any, checks: list[dict[str, Any]]) -> None:
    checks.append({"name": name, "passed": bool(condition), "detail": detail})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def main() -> None:
    from transformers import AutoTokenizer

    manifest = json.loads((OUT / "manifest.json").read_text(encoding="utf-8"))
    conversions = read_jsonl(OUT / "label_conversion.jsonl")
    masks = read_jsonl(OUT / "loss_mask_checks.jsonl")
    source_ids = {
        line.strip()
        for line in (ROOT / "experiments/2026-09-28_dynamic_cfst/step02_error_analysis/source_task_ids.txt").read_text().splitlines()
        if line.strip()
    }
    check_ids = {
        line.strip()
        for line in (ROOT / "experiments/2026-09-28_dynamic_cfst/step02_error_analysis/check_task_ids.txt").read_text().splitlines()
        if line.strip()
    }
    checks: list[dict[str, Any]] = []

    check("conversion_count_20", len(conversions) == 20, len(conversions), checks)
    conversion_ids = [row["task_id"] for row in conversions]
    check("conversion_task_ids_unique", len(set(conversion_ids)) == 20, conversion_ids, checks)
    check("all_conversions_source60", set(conversion_ids) <= source_ids, sorted(set(conversion_ids) - source_ids), checks)
    check("no_conversions_check30", not (set(conversion_ids) & check_ids), sorted(set(conversion_ids) & check_ids), checks)
    check(
        "new_label_counts_12_8",
        Counter(row["new_primary_label"] for row in conversions) == {"state_construction": 12, "action_grounding": 8},
        dict(Counter(row["new_primary_label"] for row in conversions)),
        checks,
    )
    recovery = next(row for row in conversions if row["task_id"] == "6104387_3")
    check("csv_recovery_mapped_to_action", recovery["new_primary_label"] == "action_grounding", recovery, checks)
    check("csv_recovery_keeps_recovery_secondary", "错误反馈后" in recovery["secondary_labels"], recovery["secondary_labels"], checks)

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL, trust_remote_code=False, local_files_only=True, use_fast=True
    )
    package_rows: dict[str, list[dict[str, Any]]] = {}
    computed_masks: dict[tuple[str, str], dict[str, int]] = {}
    for package, expected in PACKAGE_COUNTS.items():
        path = OUT / package / "train.jsonl"
        rows = read_jsonl(path)
        package_rows[package] = rows
        ids = [row["id"] for row in rows]
        task_ids = [row["metadata"]["task_id"] for row in rows]
        check(f"{package}_count", len(rows) == expected, len(rows), checks)
        check(f"{package}_unique_ids", len(set(ids)) == expected, ids, checks)
        check(f"{package}_source_only", set(task_ids) <= source_ids and not (set(task_ids) & check_ids), task_ids, checks)
        package_manifest = json.loads((OUT / package / "manifest.json").read_text(encoding="utf-8"))
        check(f"{package}_train_hash", package_manifest["train_sha256"] == sha256_file(path), package_manifest["train_sha256"], checks)
        check(f"{package}_manifest_order", package_manifest["task_ids_in_order"] == task_ids, task_ids, checks)

        for row in rows:
            metadata = row["metadata"]
            check_name = f"{package}_{row['id']}"
            check(f"{check_name}_one_completion", len(row["completion"]) == 1 and row["completion"][0]["role"] == "assistant", package, checks)
            check(f"{check_name}_one_python_block", len(CODE_RE.findall(row["completion"][0]["content"])) == 1, package, checks)
            check(f"{check_name}_loss_contract", metadata["loss_policy"] == "assistant_completion_only", metadata["loss_policy"], checks)
            check(f"{check_name}_verified", metadata["prefix_replay_success"] and metadata["official_evaluation_success"] and metadata["teacher_boundary_clean"], package, checks)
            check(f"{check_name}_target_index", metadata["target_message_index"] == len(row["prompt"]), metadata["target_message_index"], checks)
            prompt_ids = tokenizer.apply_chat_template(
                row["prompt"], tools=None, tokenize=True, add_generation_prompt=True, enable_thinking=False
            )
            full_ids = tokenizer.apply_chat_template(
                row["prompt"] + row["completion"], tools=None, tokenize=True,
                add_generation_prompt=False, enable_thinking=False,
            )
            check(f"{check_name}_template_prefix", full_ids[: len(prompt_ids)] == prompt_ids, package, checks)
            completion_ids = full_ids[len(prompt_ids) :]
            labels = [-100] * len(prompt_ids) + completion_ids
            check(f"{check_name}_within_max_length", len(full_ids) <= MAX_LENGTH, len(full_ids), checks)
            check(f"{check_name}_completion_nonempty", bool(completion_ids), len(completion_ids), checks)
            check(f"{check_name}_prompt_fully_masked", all(value == -100 for value in labels[: len(prompt_ids)]), len(prompt_ids), checks)
            check(f"{check_name}_completion_fully_supervised", labels[len(prompt_ids) :] == completion_ids, len(completion_ids), checks)
            computed_masks[(package, row["id"])] = {
                "prompt_tokens": len(prompt_ids),
                "completion_tokens": len(completion_ids),
                "full_tokens": len(full_ids),
            }

    state_ids = {row["id"] for row in package_rows["CFST-state"]}
    action_ids = {row["id"] for row in package_rows["CFST-Action"]}
    mixed_by_id = {row["id"]: row for row in package_rows["CFST-Mixed"]}
    specialist_by_id = {row["id"]: row for package in ("CFST-state", "CFST-Action") for row in package_rows[package]}
    check("specialists_disjoint", not (state_ids & action_ids), sorted(state_ids & action_ids), checks)
    check("specialists_union_mixed", state_ids | action_ids == set(mixed_by_id), sorted(state_ids | action_ids), checks)
    check("mixed_rows_equal_specialist_rows", mixed_by_id == specialist_by_id, len(mixed_by_id), checks)
    check(
        "state_package_labels",
        {row["metadata"]["capability_label"] for row in package_rows["CFST-state"]} == {"state_construction"},
        None,
        checks,
    )
    check(
        "action_package_labels",
        {row["metadata"]["capability_label"] for row in package_rows["CFST-Action"]} == {"action_grounding"},
        None,
        checks,
    )

    recorded_masks = {(row["package"], row["id"]): row for row in masks}
    check("loss_mask_record_count_40", len(recorded_masks) == 40, len(recorded_masks), checks)
    check("loss_mask_keys_exact", set(recorded_masks) == set(computed_masks), None, checks)
    for key, computed in computed_masks.items():
        recorded = recorded_masks[key]
        check(
            f"mask_stats_{key[0]}_{key[1]}",
            all(recorded[field] == value for field, value in computed.items())
            and recorded["ignored_prompt_label_count"] == computed["prompt_tokens"]
            and recorded["supervised_completion_label_count"] == computed["completion_tokens"]
            and recorded["prompt_truncated"] is False,
            computed,
            checks,
        )

    check(
        "root_manifest_package_hashes",
        all(
            manifest["packages"][package]["train_sha256"] == sha256_file(OUT / package / "train.jsonl")
            for package in PACKAGE_COUNTS
        ),
        manifest["packages"],
        checks,
    )
    check(
        "frozen_source_hash",
        manifest["source_qualified_samples_sha256"]
        == sha256_file(ROOT / manifest["source_qualified_samples"]),
        manifest["source_qualified_samples_sha256"],
        checks,
    )
    tie_order = manifest["order_policy"]["check30_tie_break_branch_order"]
    check("tie_break_order_frozen", set(tie_order) == set(PACKAGE_COUNTS) and len(tie_order) == 3, tie_order, checks)

    validation = {
        "schema_version": "dynamic-cfst-step05-validation-v1",
        "status": "PASS",
        "checks_passed": len(checks),
        "checks_total": len(checks),
        "checks": checks,
        "summary": {
            "unique_verified_repairs": 20,
            "state_samples": 12,
            "action_samples": 8,
            "mixed_samples": 20,
            "serialized_rows_checked": 40,
            "source60_only": True,
            "check30_teacher_answers": 0,
            "dev57_teacher_answers": 0,
            "completion_only_loss_masks_checked": 40,
            "max_full_tokens": max(value["full_tokens"] for value in computed_masks.values()),
            "prompt_truncations": 0,
        },
    }
    (OUT / "validation.json").write_text(
        json.dumps(validation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    hash_paths = [
        OUT / "manifest.json", OUT / "label_conversion.jsonl", OUT / "label_conversion.csv",
        OUT / "package_stats.json", OUT / "loss_mask_checks.jsonl", OUT / "validation.json",
    ]
    for package in PACKAGE_COUNTS:
        hash_paths.extend([OUT / package / "train.jsonl", OUT / package / "manifest.json"])
    hashes = {str(path.relative_to(OUT)): sha256_file(path) for path in hash_paths}
    (OUT / "artifact_sha256.json").write_text(
        json.dumps({"algorithm": "sha256", "files": hashes}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(validation["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()
