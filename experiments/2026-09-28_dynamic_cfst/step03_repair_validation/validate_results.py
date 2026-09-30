#!/usr/bin/env python3
"""Validate Step 3 evidence without reading AppWorld private ground truth."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


STAGE = Path(__file__).resolve().parent
STEP01 = STAGE.parent / "step01_train90_student_rollouts"
STEP02 = STAGE.parent / "step02_error_analysis"
ADAPTER = STAGE.parents[2] / "experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter/adapter_model.safetensors"
FORBIDDEN_TEACHER_EVENTS = {"command_execution", "file_change", "mcp_tool_call", "web_search"}


def sha256_path(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


checks: list[dict[str, Any]] = []


def check(name: str, condition: bool, evidence: Any = None) -> None:
    checks.append({"name": name, "passed": bool(condition), "evidence": evidence})


prefix = json.loads((STAGE / "prefix_validation.json").read_text())
summary = json.loads((STAGE / "summary.json").read_text())
manifest = json.loads((STAGE / "manifest.json").read_text())
candidates = {
    row["task_id"]: row for row in load_jsonl(STEP02 / "repair_candidates.jsonl")
}
annotations = {
    row["task_id"]: row for row in load_jsonl(STEP02 / "review_annotations.jsonl")
}

check("all five frozen prefixes validated", prefix["passed"] and prefix["validated_candidates"] == 5)
check(
    "57 prefix actions reproduced",
    sum(row["executed_prefix_actions"] for row in prefix["results"]) == 57
    and all(row["all_observations_match"] for row in prefix["results"]),
)
check(
    "frozen candidate index unchanged",
    prefix["candidate_index_sha256"] == sha256_path(STEP02 / "repair_candidates.jsonl")
    == manifest["candidate_index_sha256"],
)
check(
    "original adapter weights unchanged",
    sha256_path(ADAPTER) == manifest["student_adapter_sha256"],
    sha256_path(ADAPTER),
)
check("gate status complete", summary["status"] == "completed_gate_passed")
check("exactly three attempts and successes", summary["attempts_completed"] == summary["verified_successful_repairs"] == 3)
check(
    "first three frozen candidates used",
    [row["task_id"] for row in summary["candidate_results"]]
    == ["ccb4494_2", "302c169_2", "60d0b5b_1"],
)
check("no failed candidate", summary["failed_task_ids"] == [])
check("three teacher calls", summary["teacher_calls"] == 3)
check("student continued after every repair", summary["student_continuation_actions"] == 9)
check("no training", summary["training_runs"] == manifest["training_runs"] == 0)

for item in summary["candidate_results"]:
    task_id = item["task_id"]
    rank = item["rank"]
    candidate = candidates[task_id]
    annotation = annotations[task_id]
    attempt_dir = STAGE / "attempts" / f"rank{rank}_{task_id}"
    result = json.loads((attempt_dir / "result.json").read_text())
    teacher_request = json.loads((attempt_dir / "teacher/request.json").read_text())
    teacher_response = json.loads((attempt_dir / "teacher/response.json").read_text())
    interactions = load_jsonl(attempt_dir / "interactions.jsonl")
    original_calls = load_jsonl(Path(candidate["paths"]["lm_calls"]))
    replacement = candidate["replace_action_index_1based"]
    original_messages = original_calls[replacement - 1]["input"]["messages"]
    original_rejected_content = original_calls[replacement - 1]["output"]["choices"][0]["message"]["content"]
    first_student = next(row for row in interactions if row["actor"] == "student")
    first_request = json.loads(
        (attempt_dir / f"student/action_{first_student['action_index_1based']:02d}_request.json").read_text()
    )
    request_prefix = first_request["messages"][: len(original_messages)]
    for message in request_prefix:
        message.pop("cache_control", None)
    original_prefix = json.loads(canonical(original_messages))
    for message in original_prefix:
        message.pop("cache_control", None)
    report_path = Path(result["official_report"])
    report = report_path.read_text()

    check(f"{task_id}: rank and replacement frozen", result["candidate_rank"] == rank and result["replace_action_index_1based"] == replacement)
    check(f"{task_id}: clean prefix replay", result["prefix_replay_success"] and result["replay_error"] is None)
    check(f"{task_id}: teacher input digest", teacher_request["student_messages_sha256"] == candidate["input_messages_sha256"])
    check(f"{task_id}: student received exact original prefix", request_prefix == original_prefix)
    check(
        f"{task_id}: rejected action hidden from teacher",
        original_rejected_content not in teacher_request["prompt"],
    )
    check(
        f"{task_id}: official failure summary hidden from teacher",
        annotation["official_failure_summary_zh"] not in teacher_request["prompt"],
    )
    check(
        f"{task_id}: step02 repair direction hidden from teacher",
        candidate["repair_direction"] not in teacher_request["prompt"],
    )
    check(
        f"{task_id}: teacher used no tools",
        not (set(teacher_response["codex_event_item_types"]) & FORBIDDEN_TEACHER_EVENTS)
        and teacher_response["codex_event_item_types"] == ["agent_message"],
        teacher_response["codex_event_item_types"],
    )
    check(
        f"{task_id}: teacher code executed at frozen action",
        interactions[0]["actor"] == "teacher"
        and interactions[0]["action_index_1based"] == replacement
        and interactions[0]["code"] == teacher_response["code"],
    )
    check(
        f"{task_id}: student continued",
        result["student"]["continuation_actions"] > 0
        and all(row["actor"] == "student" for row in interactions[1:]),
        result["student"]["continuation_actions"],
    )
    check(
        f"{task_id}: action budget respected",
        replacement + result["student"]["continuation_actions"] <= 50,
    )
    check(f"{task_id}: no generation error", result["generation_error"] is None)
    check(
        f"{task_id}: official full success",
        result["official_successful_repair"]
        and result["official_evaluation"]["success"]
        and result["official_evaluation"]["num_failures"] == 0
        and result["official_evaluation"]["num_passes"]
        == result["official_evaluation"]["num_tests"],
        result["official_evaluation"],
    )
    check(
        f"{task_id}: official report saved",
        report_path.is_file() and "Num Failed Tests : 0" in report and "Fails" in report,
        str(report_path),
    )

validation = {
    "schema_version": "dynamic-cfst-step03-validation-v1",
    "passed": all(row["passed"] for row in checks),
    "check_count": len(checks),
    "failed_checks": [row["name"] for row in checks if not row["passed"]],
    "checks": checks,
    "scope": "Evidence consistency, teacher boundary, action budget and official-score artifact checks. This does not establish generalization or CFST training effectiveness.",
}
(STAGE / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")

included: list[Path] = []
for path in STAGE.rglob("*"):
    if not path.is_file():
        continue
    relative = path.relative_to(STAGE)
    if relative.parts[0] in {"cache", "__pycache__", "logs"}:
        continue
    if relative.name == "artifact_sha256.json":
        continue
    included.append(path)
hashes = {str(path.relative_to(STAGE)): sha256_path(path) for path in sorted(included)}
(STAGE / "artifact_sha256.json").write_text(json.dumps(hashes, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({key: validation[key] for key in ["passed", "check_count", "failed_checks", "scope"]}, ensure_ascii=False, indent=2))
raise SystemExit(0 if validation["passed"] else 1)
