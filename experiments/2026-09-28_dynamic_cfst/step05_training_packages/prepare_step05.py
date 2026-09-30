#!/usr/bin/env python3
"""Build the three minimal Dynamic-CFST completion-only SFT packages."""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any

SEED = 20260928
MAX_LENGTH = 40960
TARGET_MODEL = "Qwen/Qwen3-8B"
SCHEMA_VERSION = "dynamic-cfst-step05-sft-v1"
ROOT = Path(__file__).resolve().parents[3]
EXPERIMENT = ROOT / "experiments/2026-09-28_dynamic_cfst"
OUT = Path(__file__).resolve().parent
SOURCE = EXPERIMENT / "step04b_context_repairs/qualified_samples.jsonl"
SOURCE_IDS = EXPERIMENT / "step02_error_analysis/source_task_ids.txt"
CHECK_IDS = EXPERIMENT / "step02_error_analysis/check_task_ids.txt"
MODEL = Path("/root/autodl-tmp/models/Qwen3-8B")

PACKAGES = {
    "CFST-state": "state_construction",
    "CFST-Action": "action_grounding",
    "CFST-Mixed": "mixed",
}

FORBIDDEN_PATTERNS = {
    "ground_truth": re.compile(r"\bground_truth\b", re.IGNORECASE),
    "private_data": re.compile(r"\bprivate_data\b", re.IGNORECASE),
    "test_data": re.compile(r"\btest_data\b", re.IGNORECASE),
    "solution_module": re.compile(r"\b(?:compiled_)?solution\.py\b", re.IGNORECASE),
    "evaluation_module": re.compile(r"\bevaluation\.py\b", re.IGNORECASE),
    "access_token_literal": re.compile(
        r"['\"]access_token['\"]\s*:\s*['\"](?!<REDACTED>)[^'\"]+['\"]",
        re.IGNORECASE,
    ),
    "password_literal": re.compile(
        r"['\"]password['\"]\s*:\s*['\"](?!<REDACTED>)[^'\"]+['\"]",
        re.IGNORECASE,
    ),
    "jwt": re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    "bearer": re.compile(
        r"\bBearer\s+(?!<REDACTED>)[A-Za-z0-9._~+/-]{12,}=*", re.IGNORECASE
    ),
}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8"
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def repo_relative(path: Path) -> str:
    return str(path.resolve().relative_to(ROOT))


def parse_teacher_messages(prompt: str) -> list[dict[str, str]]:
    start = "<student_messages_json>\n"
    end = "\n</student_messages_json>"
    if prompt.count(start) != 1 or prompt.count(end) != 1:
        raise ValueError("teacher prompt does not contain one bounded student transcript")
    payload = prompt.split(start, 1)[1].split(end, 1)[0]
    messages = json.loads(payload)
    if not isinstance(messages, list) or not messages:
        raise ValueError("empty teacher-visible transcript")
    for message in messages:
        if set(message) != {"role", "content"}:
            raise ValueError("unexpected key in teacher-visible message")
        if message["role"] not in {"system", "user", "assistant"}:
            raise ValueError(f"unexpected role: {message['role']}")
        if not isinstance(message["content"], str):
            raise ValueError("non-string teacher-visible message content")
    return messages


def assistant_message(reasoning: str, code: str) -> dict[str, str]:
    reasoning = reasoning.strip()
    code = code.strip()
    if not reasoning or not code or "```" in code:
        raise ValueError("invalid teacher repair response")
    return {
        "role": "assistant",
        "content": f"{reasoning}\n\n```python\n{code}\n```\n\n",
    }


def percentile(values: list[int], q: float) -> int:
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * q)]


def main() -> None:
    from transformers import AutoTokenizer

    source_rows = read_jsonl(SOURCE)
    if len(source_rows) != 20:
        raise ValueError(f"expected 20 frozen repairs, found {len(source_rows)}")
    if len({row["task_id"] for row in source_rows}) != 20:
        raise ValueError("frozen repairs contain duplicate task IDs")

    source_ids = {line.strip() for line in SOURCE_IDS.read_text().splitlines() if line.strip()}
    check_ids = {line.strip() for line in CHECK_IDS.read_text().splitlines() if line.strip()}
    if source_ids & check_ids or len(source_ids) != 60 or len(check_ids) != 30:
        raise ValueError("the frozen source/check split is invalid")

    tokenizer = AutoTokenizer.from_pretrained(
        MODEL, trust_remote_code=False, local_files_only=True, use_fast=True
    )

    prepared: list[dict[str, Any]] = []
    conversions: list[dict[str, Any]] = []
    token_by_id: dict[str, dict[str, int]] = {}
    redaction_by_id: dict[str, int] = {}

    for source_index, frozen in enumerate(source_rows, 1):
        task_id = str(frozen["task_id"])
        if task_id not in source_ids or task_id in check_ids:
            raise ValueError(f"{task_id}: repair is outside the source-60 partition")
        if not frozen.get("prefix_replay_success") or not frozen.get("official_success"):
            raise ValueError(f"{task_id}: frozen repair is not verified successful")
        if any(frozen.get("teacher_boundary", {}).values()):
            raise ValueError(f"{task_id}: teacher boundary is not clean")

        old_label = str(frozen["final_primary_label"])
        if old_label == "状态错误":
            capability = "state_construction"
            capability_zh = "状态构建"
            conversion_reason = "原状态错误：教师动作补充、筛选、压缩或重新理解下一步所需状态。"
        elif old_label in {"参数错误", "恢复错误"}:
            capability = "action_grounding"
            capability_zh = "动作落地"
            conversion_reason = (
                "原参数错误：必要状态已基本可见，教师动作修正API、对象、方向、路径或参数。"
                if old_label == "参数错误"
                else "原恢复错误实际修正CSV构造与写入，因此归入动作落地；保留错误反馈后次要标签。"
            )
        else:
            raise ValueError(f"{task_id}: unknown old label {old_label}")

        secondary = list(frozen.get("secondary_labels") or [])
        source_secondary = list(secondary)
        if task_id == "6104387_3" and "错误反馈后" not in secondary:
            secondary.insert(0, "错误反馈后")

        attempt = Path(frozen["result_path"]).resolve().parent
        request_path = attempt / "teacher/request.json"
        response_path = attempt / "teacher/response.json"
        result_path = attempt / "result.json"
        request = json.loads(request_path.read_text(encoding="utf-8"))
        response = json.loads(response_path.read_text(encoding="utf-8"))
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if (
            result.get("task_id") != task_id
            or int(result.get("replace_action_index_1based", -1)) != int(frozen["replace_action_index_1based"])
            or result.get("prefix_replay_success") is not True
            or result.get("official_successful_repair") is not True
            or result.get("official_evaluation", {}).get("success") is not True
            or result.get("official_evaluation", {}).get("num_passes")
            != result.get("official_evaluation", {}).get("num_tests")
        ):
            raise ValueError(f"{task_id}: source attempt is not a matching official successful repair")
        result_teacher = result.get("teacher", {})
        if any(
            result_teacher.get(flag) is not False
            for flag in (
                "ground_truth_visible",
                "rejected_action_visible",
                "later_trajectory_visible",
                "official_failure_condition_visible",
            )
        ):
            raise ValueError(f"{task_id}: source result teacher boundary is not clean")
        messages = parse_teacher_messages(str(request["prompt"]))
        if len(messages) != int(request["visible_message_count"]):
            raise ValueError(f"{task_id}: visible teacher message count mismatch")

        code = str(response["code"])
        reasoning = str(response["reasoning"])
        if result_teacher.get("response", {}).get("code") != code or result_teacher.get("response", {}).get("reasoning") != reasoning:
            raise ValueError(f"{task_id}: standalone teacher response differs from official repair result")
        if sha256_bytes(code.encode()) != frozen["teacher_code_sha256"]:
            raise ValueError(f"{task_id}: teacher code hash mismatch")
        if sha256_bytes(reasoning.encode()) != frozen["teacher_reasoning_sha256"]:
            raise ValueError(f"{task_id}: teacher reasoning hash mismatch")
        completion = [assistant_message(reasoning, code)]

        dynamic_blob = json.dumps(messages + completion, ensure_ascii=False)
        findings = [name for name, pattern in FORBIDDEN_PATTERNS.items() if pattern.search(dynamic_blob)]
        if findings:
            raise ValueError(f"{task_id}: forbidden dynamic content found: {findings}")
        redaction_by_id[task_id] = dynamic_blob.count("<REDACTED")

        prompt_ids = tokenizer.apply_chat_template(
            messages,
            tools=None,
            tokenize=True,
            add_generation_prompt=True,
            enable_thinking=False,
        )
        full_ids = tokenizer.apply_chat_template(
            messages + completion,
            tools=None,
            tokenize=True,
            add_generation_prompt=False,
            enable_thinking=False,
        )
        if full_ids[: len(prompt_ids)] != prompt_ids:
            raise ValueError(f"{task_id}: Qwen chat-template prefix invariant failed")
        completion_ids = full_ids[len(prompt_ids) :]
        if not completion_ids or len(full_ids) > MAX_LENGTH:
            raise ValueError(f"{task_id}: invalid token length {len(full_ids)}")
        token_by_id[task_id] = {
            "prompt_tokens": len(prompt_ids),
            "completion_tokens": len(completion_ids),
            "full_tokens": len(full_ids),
        }

        memberships = ["CFST-state", "CFST-Mixed"] if capability == "state_construction" else ["CFST-Action", "CFST-Mixed"]
        row = {
            "id": f"cfst-step05::{task_id}::repair-{int(frozen['replace_action_index_1based']):02d}",
            "prompt": messages,
            "completion": completion,
            "tools": None,
            "metadata": {
                "schema_version": SCHEMA_VERSION,
                "task_id": task_id,
                "task_family": frozen["family_id"],
                "split": "train",
                "source": "dynamic_cfst_verified_one_step_repair",
                "source_stage": frozen["origin"],
                "source_sample_id": frozen["sample_id"],
                "repair_action_index_1based": frozen["replace_action_index_1based"],
                "capability_label": capability,
                "capability_label_zh": capability_zh,
                "old_primary_label": old_label,
                "secondary_labels": secondary,
                "package_membership": memberships,
                "target_model": TARGET_MODEL,
                "chat_protocol": "appworld_simplified_react_code_agent",
                "loss_policy": "assistant_completion_only",
                "reasoning_policy": "verified_teacher_visible_rationale_preserved",
                "observation_policy": "teacher_visible_credential_redacted_original_history",
                "input_policy": "all teacher-visible original messages before the replaced action",
                "target_policy": "one verified teacher replacement action only",
                "excluded_from_target": [
                    "rejected_student_action",
                    "later_student_rollout",
                    "official_failure_conditions",
                    "evaluator_assertions",
                    "ground_truth",
                ],
                "prompt_message_count": len(messages),
                "target_message_index": len(messages),
                "prefix_replay_success": True,
                "official_evaluation_success": True,
                "teacher_boundary_clean": True,
                "teacher_code_sha256": frozen["teacher_code_sha256"],
                "teacher_reasoning_sha256": frozen["teacher_reasoning_sha256"],
                "source_result_sha256": sha256_file(result_path),
                "source_teacher_request_sha256": sha256_file(request_path),
                "source_teacher_response_sha256": sha256_file(response_path),
            },
        }
        prepared.append(row)
        conversions.append(
            {
                "source_index": source_index,
                "sample_id": frozen["sample_id"],
                "training_id": row["id"],
                "task_id": task_id,
                "family_id": frozen["family_id"],
                "origin": frozen["origin"],
                "replace_action_index_1based": frozen["replace_action_index_1based"],
                "old_primary_label": old_label,
                "new_primary_label": capability,
                "new_primary_label_zh": capability_zh,
                "source_secondary_labels": source_secondary,
                "secondary_labels": secondary,
                "conversion_reason_zh": conversion_reason,
                "label_rationale_zh": frozen["label_rationale_zh"],
                "package_membership": memberships,
                "prefix_replay_success": True,
                "official_success": True,
                "official_num_tests": frozen["official_evaluation"]["num_tests"],
                "official_num_passes": frozen["official_evaluation"]["num_passes"],
                "teacher_code_sha256": frozen["teacher_code_sha256"],
                "teacher_reasoning_sha256": frozen["teacher_reasoning_sha256"],
                "teacher_request_path": repo_relative(request_path),
                "teacher_response_path": repo_relative(response_path),
                "result_path": repo_relative(result_path),
            }
        )

    label_counts = Counter(row["metadata"]["capability_label"] for row in prepared)
    if label_counts != {"state_construction": 12, "action_grounding": 8}:
        raise ValueError(f"unexpected two-capability counts: {dict(label_counts)}")

    rng = random.Random(SEED)
    rng.shuffle(prepared)
    global_order = {row["metadata"]["task_id"]: index for index, row in enumerate(prepared, 1)}
    conversions.sort(key=lambda row: global_order[row["task_id"]])
    for conversion in conversions:
        conversion["global_order_seed_20260928"] = global_order[conversion["task_id"]]

    package_rows = {
        "CFST-state": [r for r in prepared if r["metadata"]["capability_label"] == "state_construction"],
        "CFST-Action": [r for r in prepared if r["metadata"]["capability_label"] == "action_grounding"],
        "CFST-Mixed": list(prepared),
    }
    expected_counts = {"CFST-state": 12, "CFST-Action": 8, "CFST-Mixed": 20}
    for package, rows in package_rows.items():
        if len(rows) != expected_counts[package]:
            raise ValueError(f"{package}: expected {expected_counts[package]}, found {len(rows)}")
        write_jsonl(OUT / package / "train.jsonl", rows)

    write_jsonl(OUT / "label_conversion.jsonl", conversions)
    csv_fields = [
        "global_order_seed_20260928", "task_id", "family_id", "origin",
        "replace_action_index_1based", "old_primary_label", "new_primary_label_zh",
        "secondary_labels", "package_membership", "official_num_passes", "official_num_tests",
        "conversion_reason_zh", "label_rationale_zh", "training_id",
    ]
    with (OUT / "label_conversion.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        for row in conversions:
            flat = {key: row[key] for key in csv_fields}
            flat["secondary_labels"] = "|".join(row["secondary_labels"])
            flat["package_membership"] = "|".join(row["package_membership"])
            writer.writerow(flat)

    stats: dict[str, Any] = {
        "schema_version": "dynamic-cfst-step05-stats-v1",
        "tokenizer_path": str(MODEL),
        "enable_thinking": False,
        "max_length": MAX_LENGTH,
        "packages": {},
    }
    mask_rows: list[dict[str, Any]] = []
    for package, rows in package_rows.items():
        ids = [row["metadata"]["task_id"] for row in rows]
        values = [token_by_id[task_id] for task_id in ids]
        completion_lengths = [value["completion_tokens"] for value in values]
        full_lengths = [value["full_tokens"] for value in values]
        family_ids = sorted({row["metadata"]["task_family"] for row in rows})
        pkg_stats = {
            "sample_count": len(rows),
            "unique_task_count": len(set(ids)),
            "unique_family_count": len(family_ids),
            "family_ids": family_ids,
            "capability_counts": dict(Counter(row["metadata"]["capability_label_zh"] for row in rows)),
            "prompt_tokens_sum": sum(value["prompt_tokens"] for value in values),
            "supervised_completion_tokens_sum": sum(completion_lengths),
            "full_tokens_sum_one_pass": sum(full_lengths),
            "completion_tokens": {
                "min": min(completion_lengths),
                "p50": percentile(completion_lengths, 0.50),
                "max": max(completion_lengths),
            },
            "full_tokens": {"min": min(full_lengths), "max": max(full_lengths)},
            "samples_over_40960": sum(length > MAX_LENGTH for length in full_lengths),
            "suggested_step06_supervised_token_budget": 8000,
            "repetition_schedule": "deferred_to_step06; train.jsonl contains unique samples only",
        }
        stats["packages"][package] = pkg_stats
        package_manifest = {
            "schema_version": "dynamic-cfst-step05-package-manifest-v1",
            "package": package,
            "seed": SEED,
            "order_policy": "filter one globally shuffled 20-sample order",
            "sample_count": len(rows),
            "task_ids_in_order": ids,
            "train_sha256": sha256_file(OUT / package / "train.jsonl"),
            "loss_policy": "assistant_completion_only",
            "unique_samples_only": True,
            "stats": pkg_stats,
        }
        write_json(OUT / package / "manifest.json", package_manifest)
        for row, value in zip(rows, values):
            mask_rows.append(
                {
                    "package": package,
                    "id": row["id"],
                    "task_id": row["metadata"]["task_id"],
                    **value,
                    "ignored_prompt_label_count": value["prompt_tokens"],
                    "supervised_completion_label_count": value["completion_tokens"],
                    "ignored_label_value": -100,
                    "chat_template_prefix_invariant": True,
                    "prompt_truncated": False,
                }
            )
    write_json(OUT / "package_stats.json", stats)
    write_jsonl(OUT / "loss_mask_checks.jsonl", mask_rows)

    branch_order = ["CFST-state", "CFST-Action", "CFST-Mixed"]
    random.Random(SEED).shuffle(branch_order)
    root_manifest = {
        "schema_version": "dynamic-cfst-step05-manifest-v1",
        "created_date": "2026-09-29",
        "seed": SEED,
        "source_qualified_samples": repo_relative(SOURCE),
        "source_qualified_samples_sha256": sha256_file(SOURCE),
        "source_partition": "source60 only",
        "excluded_partitions": ["check30", "Dev57"],
        "counts": {
            "frozen_verified_repairs": 20,
            "state_construction": 12,
            "action_grounding": 8,
            "mixed": 20,
            "serialized_rows_across_three_packages": 40,
        },
        "order_policy": {
            "sample_order": "Python random.Random(20260928).shuffle over the frozen 20-row source order; specialist packages filter that global order",
            "check30_tie_break_branch_order": branch_order,
        },
        "training_contract": {
            "format": "prompt + one assistant completion",
            "loss_policy": "assistant_completion_only",
            "input": "teacher-visible original history before the replaced action, with credentials redacted",
            "target": "verified teacher reasoning and one replacement Python action",
            "excluded": ["rejected action", "later student rollout", "official failure conditions", "evaluator assertions", "ground truth"],
            "max_length": MAX_LENGTH,
            "enable_thinking": False,
            "suggested_step06_supervised_token_budget_per_branch": 8000,
        },
        "packages": {
            package: {
                "path": f"{package}/train.jsonl",
                "sample_count": len(rows),
                "train_sha256": sha256_file(OUT / package / "train.jsonl"),
            }
            for package, rows in package_rows.items()
        },
        "redaction_markers": {
            "unique_samples_total": sum(redaction_by_id.values()),
            "by_task": redaction_by_id,
        },
        "generation_script": repo_relative(Path(__file__)),
    }
    write_json(OUT / "manifest.json", root_manifest)
    print(json.dumps(root_manifest["counts"], ensure_ascii=False))


if __name__ == "__main__":
    main()
