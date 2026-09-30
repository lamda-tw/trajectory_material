#!/usr/bin/env python3
"""Validate Step 4B evidence, boundaries, labels, and the stopped training gate."""

from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

STAGE = Path(__file__).resolve().parent
PARENT = STAGE.parent
STEP02 = PARENT / "step02_error_analysis"
EXPECTED_ORDER = ["76f2c72_2", "b0a8eae_1", "2a163ab_1", "2a163ab_2", "22cc237_2", "22cc237_1", "c901732_2", "2a163ab_3"]
EXPECTED_SUCCESSES = {"b0a8eae_1", "2a163ab_1", "2a163ab_2", "2a163ab_3"}


def read_json(path: Path):
    return json.loads(path.read_text())


def read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def check(name: str, passed: bool, detail=None) -> dict:
    return {"name": name, "passed": bool(passed), "detail": detail}


def main() -> None:
    candidates = read_jsonl(STAGE / "repair_candidates.jsonl")
    reviews = read_jsonl(STAGE / "review_annotations.jsonl")
    prefix = read_json(STAGE / "prefix_validation.json")
    summary = read_json(STAGE / "summary.json")
    qualified = read_jsonl(STAGE / "qualified_samples.jsonl")
    excluded = read_jsonl(STAGE / "excluded_attempts.jsonl")
    freeze = read_json(STAGE / "freeze_summary.json")
    costs = read_json(STAGE / "costs.json")
    manifest = read_json(STAGE / "manifest.json")
    source = set((STEP02 / "source_task_ids.txt").read_text().split())
    check_ids = set((STEP02 / "check_task_ids.txt").read_text().split())
    queue = {row["task_id"]: row for row in csv.DictReader((STEP02 / "review_queue.csv").open())}
    candidate_ids = [row["task_id"] for row in candidates]
    result_paths = sorted((STAGE / "attempts").glob("rank*/result.json"))
    results = [read_json(path) for path in result_paths]
    results_by_id = {row["task_id"]: row for row in results}
    success_ids = {row["task_id"] for row in results if row["official_successful_repair"]}
    excluded_ids = {row["task_id"] for row in excluded}
    new_qualified = [row for row in qualified if row["origin"] == "step04b"]
    label_counts = Counter(row["final_primary_label"] for row in qualified)

    checks = [
        check("candidate_count_8", len(candidates) == 8, len(candidates)),
        check("fixed_step02_order", candidate_ids == EXPECTED_ORDER, candidate_ids),
        check("candidate_ranks_1_to_8", [row["candidate_rank"] for row in candidates] == list(range(1, 9))),
        check("attempt_order_file_matches", (STAGE / "attempt_order.txt").read_text().split() == EXPECTED_ORDER),
        check("all_candidates_source60", set(candidate_ids) <= source),
        check("no_candidates_check30", not (set(candidate_ids) & check_ids)),
        check("all_candidates_context_failures", all(queue[task_id]["context_error"] == "True" for task_id in candidate_ids)),
        check("all_candidates_pre_rejection", all(row["replace_action_index_1based"] <= row["original_trajectory_actions"] < row["first_rejected_call_index_1based"] for row in candidates)),
        check("all_candidate_inputs_fit_32000", all(row["input_within_fixed_32000_protocol"] and row["prompt_plus_reserved_tokens"] <= 32000 for row in candidates)),
        check("review_count_8", len(reviews) == 8),
        check("review_metadata_excluded_from_teacher", all(row["review_metadata_is_not_teacher_input"] for row in reviews)),
        check("prefix_validation_passed", prefix["passed"] is True),
        check("prefix_candidate_count_8", len(prefix["results"]) == 8),
        check("prefix_actions_70", sum(len(row["steps"]) for row in prefix["results"]) == 70),
        check("all_prefix_observations_match", all(row["all_observations_match"] for row in prefix["results"])),
        check("attempt_results_8", len(results) == 8),
        check("summary_attempts_8", summary["attempts_completed"] == 8),
        check("official_successes_4", summary["verified_successful_repairs"] == 4 and success_ids == EXPECTED_SUCCESSES, sorted(success_ids)),
        check("official_failures_4", excluded_ids == set(EXPECTED_ORDER) - EXPECTED_SUCCESSES, sorted(excluded_ids)),
        check("new_qualified_matches_success", {row["task_id"] for row in new_qualified} == EXPECTED_SUCCESSES),
        check("new_labels_all_state", Counter(row["final_primary_label"] for row in new_qualified) == {"状态错误": 4}),
        check("combined_qualified_20", len(qualified) == 20),
        check("combined_label_counts_12_7_1", label_counts == {"状态错误": 12, "参数错误": 7, "恢复错误": 1}, dict(label_counts)),
        check("all_qualified_official_success", all(row["official_success"] for row in qualified)),
        check("all_qualified_prefix_valid", all(row["prefix_replay_success"] for row in qualified)),
        check("new_teacher_boundary_clean", all(not any(row["teacher_boundary"].values()) for row in new_qualified)),
        check("all_attempt_teacher_boundary_clean", all(not any([row["teacher"]["ground_truth_visible"], row["teacher"]["rejected_action_visible"], row["teacher"]["later_trajectory_visible"], row["teacher"]["official_failure_condition_visible"]]) for row in results)),
        check("all_teacher_calls_completed", summary["teacher_calls"] == 8 and all(results_by_id[task]["teacher"]["called"] for task in EXPECTED_ORDER)),
        check("freeze_matches_counts", freeze["qualified_samples"] == 20 and freeze["label_counts"] == dict(label_counts)),
        check("parameter_shortfall_1", freeze["remaining_to_lower_bound"]["参数错误"] == 1 and freeze["new_parameter_successes"] == 0),
        check("recovery_shortfall_7", freeze["remaining_to_lower_bound"]["恢复错误"] == 7 and freeze["new_recovery_successes"] == 0),
        check("all_source_failures_exhausted", freeze["all_source_failures_exhausted"] is True),
        check("training_gate_stopped", freeze["training_gate_passed"] is False and freeze["training_runs"] == 0),
        check("check30_teacher_answers_zero", costs["check_split_teacher_answers"] == 0),
        check("dev57_teacher_answers_zero", costs["dev57_teacher_answers"] == 0),
        check("training_runs_zero", costs["training_runs"] == 0 and manifest["training_runs"] == 0),
        check("cost_environment_runs_16", costs["total_environment_runs"] == 16),
        check("cost_student_actions_45", costs["student_continuation_actions"] == 45),
        check("server_stopped_recorded", "stopped_at_utc" in read_json(STAGE / "server.json")),
    ]
    validation = {
        "schema_version": "dynamic-cfst-step04b-validation-v1",
        "passed": all(row["passed"] for row in checks),
        "checks_passed": sum(row["passed"] for row in checks),
        "checks_total": len(checks),
        "checks": checks,
    }
    (STAGE / "validation.json").write_text(json.dumps(validation, ensure_ascii=False, indent=2) + "\n")
    if not validation["passed"]:
        raise SystemExit(json.dumps(validation, ensure_ascii=False, indent=2))

    evidence = {}
    for path in sorted(STAGE.iterdir()):
        if path.is_file() and path.name not in {"artifact_sha256.json", "server.json"}:
            evidence[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (STAGE / "artifact_sha256.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(validation, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
