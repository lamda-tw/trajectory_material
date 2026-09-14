#!/usr/bin/env python3
"""Validate frozen selection, per-task provenance, and scorer-style predictions."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def atomic_json(path: Path, value: object) -> None:
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--workspace", type=Path, required=True)
    args = parser.parse_args()
    experiment = args.experiment.resolve(strict=True)
    workspace = args.workspace.resolve(strict=True)
    errors: list[str] = []

    selected = [json.loads(line) for line in (experiment / "data/selected_tasks.jsonl").read_text().splitlines() if line]
    selected_ids = [row["instance_id"] for row in selected]
    id_lines = (experiment / "data/selected_instance_ids.txt").read_text().splitlines()
    manifest = json.loads((experiment / "data/selection_manifest.json").read_text())
    predictions = [json.loads(line) for line in (experiment / "predictions.jsonl").read_text().splitlines() if line]
    native = json.loads((experiment / "preds.json").read_text())

    if len(selected) != 50 or len(set(selected_ids)) != 50:
        errors.append("selected_tasks does not contain exactly 50 unique instances")
    if selected_ids != id_lines:
        errors.append("selected_instance_ids order differs from selected_tasks")
    if selected_ids != manifest.get("instance_ids_in_output_order"):
        errors.append("selection manifest order differs from selected_tasks")
    if len(predictions) != 50 or [row.get("instance_id") for row in predictions] != selected_ids:
        errors.append("predictions does not contain the 50 frozen instances in order")
    if any(set(row) != {"instance_id", "model_name_or_path", "model_patch"} for row in predictions):
        errors.append("prediction schema contains missing or extra fields")
    if set(native) != set(selected_ids):
        errors.append("native preds keys differ from frozen instances")

    states = []
    for task, prediction in zip(selected, predictions, strict=True):
        instance_id = task["instance_id"]
        state_path = experiment / "metadata/per-task" / f"{instance_id}.json"
        trajectory_path = experiment / "trajectories" / f"{instance_id}.traj.json"
        submitted_path = experiment / "outputs" / f"{instance_id}.submitted.patch"
        worktree_path = experiment / "outputs" / f"{instance_id}.worktree.patch"
        dependency_path = experiment / "metadata/dependency_manifests" / f"{instance_id}.txt"
        for required in (state_path, trajectory_path, submitted_path, worktree_path, dependency_path):
            if not required.exists():
                errors.append(f"missing {required.relative_to(experiment)}")
        if not state_path.exists() or not submitted_path.exists():
            continue
        state = json.loads(state_path.read_text())
        states.append(state)
        submission = submitted_path.read_text()
        if prediction["model_patch"] != submission:
            errors.append(f"prediction patch differs from submitted artifact for {instance_id}")
        if native.get(instance_id) != prediction:
            errors.append(f"native prediction differs for {instance_id}")
        if state.get("infrastructure_error"):
            errors.append(f"unresolved infrastructure error for {instance_id}")
        if bool(submission) == bool(state.get("empty_submission")):
            errors.append(f"empty-submission flag mismatch for {instance_id}")
        patch_check = state.get("patch_apply_check", {})
        if submission and patch_check.get("applies") is not True:
            errors.append(f"nonempty patch lacks successful apply-check for {instance_id}")
        if not submission and patch_check.get("attempted") is not False:
            errors.append(f"empty patch was unexpectedly apply-checked for {instance_id}")
        if state.get("retry_count") != 0 or state.get("attempt") != 0:
            errors.append(f"formal model task was retried for {instance_id}")
        if trajectory_path.exists():
            try:
                trajectory = json.loads(trajectory_path.read_text())
                if trajectory.get("experiment", {}).get("instance_id") != instance_id:
                    errors.append(f"trajectory provenance mismatch for {instance_id}")
            except json.JSONDecodeError:
                errors.append(f"invalid trajectory JSON for {instance_id}")

    environment = json.loads((experiment / "metadata/environment.json").read_text())
    if not environment.get("dataset_tree_unchanged"):
        errors.append("shared SWE-bench data tree changed during execution")
    if not environment.get("env_entries_unchanged"):
        errors.append("/root/autodl-tmp/envs entries changed during execution")
    for runtime_name in ("worktrees", "task-envs"):
        runtime = experiment / runtime_name
        if runtime.exists() and any(runtime.iterdir()):
            errors.append(f"runtime directory is not empty: {runtime_name}")

    relative = experiment.relative_to(workspace)
    tracked_runtime = subprocess.run(
        ["git", "ls-files", "--", str(relative / "worktrees"), str(relative / "task-envs"), str(relative / "pip-cache")],
        cwd=workspace,
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    ).stdout.splitlines()
    if tracked_runtime:
        errors.append("runtime files are tracked by workspace Git")

    report = {
        "schema_version": 1,
        "validated_at_utc": datetime.now(timezone.utc).isoformat(),
        "passed": not errors,
        "errors": errors,
        "selected_count": len(selected),
        "prediction_count": len(predictions),
        "unique_prediction_count": len({row.get("instance_id") for row in predictions}),
        "trajectory_count": len(list((experiment / "trajectories").glob("*.traj.json"))),
        "per_task_state_count": len(states),
        "exit_status_counts": dict(sorted(Counter(row.get("exit_status") for row in states).items())),
        "empty_submission_count": sum(row.get("empty_submission", False) for row in states),
        "nonempty_submission_count": sum(not row.get("empty_submission", True) for row in states),
        "applicable_nonempty_count": sum(row.get("patch_apply_check", {}).get("applies") is True for row in states),
        "formal_retry_count": sum(row.get("retry_count", 0) for row in states),
        "tracked_runtime_files": tracked_runtime,
    }
    atomic_json(experiment / "metadata/final_validation.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
