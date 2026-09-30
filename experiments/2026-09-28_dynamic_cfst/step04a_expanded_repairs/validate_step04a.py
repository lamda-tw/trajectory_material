#!/usr/bin/env python3
"""Validate the frozen Step 4A evidence and source/check boundary."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path


STAGE = Path(__file__).resolve().parent
PARENT = STAGE.parent
STEP02 = PARENT / "step02_error_analysis"


def read_json(path: Path):
    return json.loads(path.read_text())


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check(name: str, passed: bool, detail=None) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def main() -> None:
    candidates = read_jsonl(STAGE / "repair_candidates.jsonl")
    qualified = read_jsonl(STAGE / "qualified_samples.jsonl")
    excluded = read_jsonl(STAGE / "excluded_attempts.jsonl")
    prefix = read_json(STAGE / "prefix_validation.json")
    summary = read_json(STAGE / "summary.json")
    freeze = read_json(STAGE / "freeze_summary.json")
    costs = read_json(STAGE / "costs.json")
    source = set((STEP02 / "source_task_ids.txt").read_text().split())
    check_ids = set((STEP02 / "check_task_ids.txt").read_text().split())
    queue = list(csv.DictReader((STEP02 / "review_queue.csv").open()))
    eligible = {
        row["task_id"] for row in queue
        if row["context_error"] == "False" and row["task_id"] in source
    }
    candidate_ids = [row["task_id"] for row in candidates]
    step04_success = set(summary["successful_task_ids"])
    excluded_ids = {row["task_id"] for row in excluded}
    qualified_step04 = {row["task_id"] for row in qualified if row["origin"] == "step04a"}
    label_counts = Counter(row["final_primary_label"] for row in qualified)

    checks = [
        check("candidate_count_20", len(candidates) == 20, len(candidates)),
        check("candidate_ranks_frozen", [row["candidate_rank"] for row in candidates] == list(range(1, 21))),
        check("all_candidates_source_only", set(candidate_ids) <= source),
        check("no_candidate_from_check30", not (set(candidate_ids) & check_ids)),
        check("all_candidates_non_context", set(candidate_ids) <= eligible),
        check("all_eligible_source_failures_accounted", set(candidate_ids) | {"ccb4494_2", "302c169_2", "60d0b5b_1"} == eligible, sorted(eligible)),
        check("prefix_validation_passed", prefix["passed"] is True),
        check("prefix_candidate_count_20", len(prefix["results"]) == 20),
        check("prefix_actions_229", sum(len(row["steps"]) for row in prefix["results"]) == 229),
        check("all_prefix_observations_match", all(row["all_observations_match"] for row in prefix["results"])),
        check("logical_attempts_20", summary["attempts_completed"] == 20),
        check("step04_successes_13", summary["verified_successful_repairs"] == 13),
        check("step04_failures_7", len(summary["failed_task_ids"]) == 7),
        check("qualified_step04_matches_summary", qualified_step04 == step04_success),
        check("excluded_matches_failures", excluded_ids == set(summary["failed_task_ids"])),
        check("qualified_total_16", len(qualified) == 16),
        check("label_counts_8_7_1", label_counts == {"状态错误": 8, "参数错误": 7, "恢复错误": 1}, dict(label_counts)),
        check("all_qualified_official_success", all(row["official_success"] for row in qualified)),
        check("all_qualified_prefix_valid", all(row["prefix_replay_success"] for row in qualified)),
        check(
            "teacher_boundary_clean",
            all(not any(row["teacher_boundary"].values()) for row in qualified),
        ),
        check("freeze_matches", freeze["qualified_samples"] == 16 and freeze["label_counts"] == dict(label_counts)),
        check("teacher_answers_check30_zero", costs["check_split_teacher_answers"] == 0),
        check("training_runs_zero", costs["training_runs"] == 0),
        check("teacher_actions_20", costs["teacher_actions_completed"] == 20),
        check("infrastructure_retry_preserved", (STAGE / "infrastructure_failures/rank18_6104387_2_attempt1/result.json").exists()),
    ]
    result = {
        "schema_version": "dynamic-cfst-step04a-validation-v1",
        "passed": all(row["passed"] for row in checks),
        "checks_passed": sum(row["passed"] for row in checks),
        "checks_total": len(checks),
        "checks": checks,
    }
    (STAGE / "validation.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if not result["passed"]:
        raise SystemExit(json.dumps(result, ensure_ascii=False, indent=2))

    evidence = {}
    for path in sorted(STAGE.iterdir()):
        if path.is_file() and path.name not in {"artifact_sha256.json", "server.json"}:
            evidence[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (STAGE / "artifact_sha256.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
