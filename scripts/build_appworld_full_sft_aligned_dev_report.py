#!/usr/bin/env python3
"""Build a Chinese report for a complete, interface-aligned AppWorld Dev run.

The builder is read-only with respect to AppWorld outputs.  It writes only the
five report artifacts in the selected evaluation experiment directory.
"""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


DEFAULT_APPWORLD_EXPERIMENT = (
    "simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev"
)
GENERATED_NAMES = (
    "REPORT.md",
    "summary.json",
    "manifest.json",
    "command.txt",
    "artifacts.sha256",
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"Expected a JSON object: {path}")
    return value


def read_jsonl(path: Path) -> tuple[list[dict[str, Any]], list[int]]:
    rows: list[dict[str, Any]] = []
    malformed: list[int] = []
    if not path.is_file():
        return rows, malformed
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                malformed.append(line_number)
                continue
            if isinstance(value, dict):
                rows.append(value)
            else:
                malformed.append(line_number)
    return rows, malformed


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def atomic_write_json(path: Path, value: Any) -> None:
    atomic_write_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def load_task_ids(path: Path, expected_count: int) -> list[str]:
    task_ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    duplicates = sorted(task_id for task_id, count in collections.Counter(task_ids).items() if count > 1)
    if len(task_ids) != expected_count or duplicates:
        raise RuntimeError(
            f"Dataset must contain exactly {expected_count} unique tasks; "
            f"found rows={len(task_ids)}, unique={len(set(task_ids))}, duplicates={duplicates}"
        )
    return task_ids


def resolve_output_root(
    experiment: Path, appworld_experiment_name: str, dataset: str
) -> tuple[Path, Path]:
    preferred = experiment / "experiments" / "outputs" / appworld_experiment_name
    preferred_eval = preferred / "evaluations" / f"{dataset}.json"
    if preferred_eval.is_file():
        return preferred, preferred_eval
    matches = sorted(
        experiment.glob(f"experiments/outputs/**/evaluations/{dataset}.json")
    )
    if len(matches) != 1:
        raise RuntimeError(
            f"Expected one {dataset} evaluation under {experiment}; found {len(matches)}: {matches}"
        )
    return matches[0].parent.parent, matches[0]


def scenario_map(task_ids: list[str]) -> dict[str, list[str]]:
    scenarios: dict[str, list[str]] = collections.defaultdict(list)
    for task_id in task_ids:
        scenarios[task_id.rsplit("_", 1)[0]].append(task_id)
    return dict(scenarios)


def difficulty_stats(individual: dict[str, Any]) -> dict[str, dict[str, int | float]]:
    totals: collections.Counter[str] = collections.Counter()
    successes: collections.Counter[str] = collections.Counter()
    for item in individual.values():
        key = str(item.get("difficulty"))
        totals[key] += 1
        successes[key] += int(bool(item.get("success")))

    def sort_key(value: str) -> tuple[int, str]:
        try:
            return int(value), value
        except ValueError:
            return sys.maxsize, value

    return {
        key: {
            "total": totals[key],
            "successes": successes[key],
            "tgc": round(100 * successes[key] / totals[key], 1),
        }
        for key in sorted(totals, key=sort_key)
    }


def load_score_snapshot(
    label: str,
    experiment: Path,
    task_ids: list[str],
    appworld_experiment_name: str,
    dataset: str,
) -> dict[str, Any]:
    output_root, evaluation_path = resolve_output_root(
        experiment, appworld_experiment_name, dataset
    )
    scores = read_json(evaluation_path)
    aggregate = scores.get("aggregate")
    individual = scores.get("individual")
    if not isinstance(aggregate, dict) or not isinstance(individual, dict):
        raise RuntimeError(f"Malformed official evaluation: {evaluation_path}")
    expected = set(task_ids)
    actual = set(individual)
    if actual != expected:
        raise RuntimeError(
            f"{label} evaluation task mismatch; missing={sorted(expected-actual)}, "
            f"extra={sorted(actual-expected)}"
        )
    success_ids = sorted(
        task_id for task_id in task_ids if bool(individual[task_id].get("success"))
    )
    scenarios = scenario_map(task_ids)
    successful_scenarios = sorted(
        scenario
        for scenario, ids in scenarios.items()
        if all(task_id in set(success_ids) for task_id in ids)
    )
    passed = 0
    failed = 0
    inconsistent_test_counts: list[str] = []
    for task_id in task_ids:
        item = individual[task_id]
        passes = item.get("passes", [])
        failures = item.get("failures", [])
        if not isinstance(passes, list) or not isinstance(failures, list):
            raise RuntimeError(f"Malformed pass/failure lists for {label}:{task_id}")
        passed += len(passes)
        failed += len(failures)
        if len(passes) + len(failures) != int(item.get("num_tests", -1)):
            inconsistent_test_counts.append(task_id)
    if inconsistent_test_counts:
        raise RuntimeError(
            f"Official per-task test counts are inconsistent for {label}: {inconsistent_test_counts}"
        )
    total = passed + failed
    return {
        "label": label,
        "experiment": str(experiment),
        "output_root": str(output_root),
        "evaluation_path": str(evaluation_path),
        "evaluation_sha256": sha256(evaluation_path),
        "aggregate": {
            "task_goal_completion": float(aggregate["task_goal_completion"]),
            "scenario_goal_completion": float(aggregate["scenario_goal_completion"]),
        },
        "success_count": len(success_ids),
        "success_ids": success_ids,
        "successful_scenario_count": len(successful_scenarios),
        "successful_scenarios": successful_scenarios,
        "difficulty": difficulty_stats(individual),
        "evaluator_tests": {
            "passed": passed,
            "failed": failed,
            "total": total,
            "pass_percentage": round(100 * passed / total, 1) if total else 0.0,
        },
        "individual": individual,
    }


def line_count(path: Path) -> int:
    if not path.is_file():
        return 0
    with path.open("r", encoding="utf-8", errors="replace") as handle:
        return sum(1 for line in handle if line.strip())


def collect_runtime(output_root: Path, task_ids: list[str]) -> dict[str, Any]:
    totals: collections.Counter[str] = collections.Counter()
    error_tasks: set[str] = set()
    syntax_error_tasks: set[str] = set()
    no_code_tasks: set[str] = set()
    max_step_tasks: set[str] = set()
    missing_task_dirs: list[str] = []
    missing_lm_logs: list[str] = []
    missing_api_logs: list[str] = []
    for task_id in task_ids:
        task_dir = output_root / "tasks" / task_id
        if not task_dir.is_dir():
            missing_task_dirs.append(task_id)
            continue
        lm_path = task_dir / "logs" / "lm_calls.jsonl"
        api_path = task_dir / "logs" / "api_calls.jsonl"
        env_path = task_dir / "logs" / "environment_io.md"
        usage_path = task_dir / "misc" / "usage.json"
        finished_path = task_dir / "misc" / "finished"
        if finished_path.exists():
            totals["finished_markers"] += 1
        if not lm_path.is_file():
            missing_lm_logs.append(task_id)
        if not api_path.is_file():
            missing_api_logs.append(task_id)
        lm_calls = line_count(lm_path)
        totals["lm_calls"] += lm_calls
        totals["api_calls"] += line_count(api_path)
        if lm_calls >= 50:
            max_step_tasks.add(task_id)
        if usage_path.is_file():
            try:
                tokens = read_json(usage_path).get("tokens", {})
                totals["input_tokens"] += int(tokens.get("input_cache_miss", 0) or 0)
                totals["input_tokens"] += int(tokens.get("input_cache_hit", 0) or 0)
                totals["output_tokens"] += int(tokens.get("output", 0) or 0)
            except Exception:
                totals["malformed_usage_files"] += 1
        if lm_path.is_file():
            with lm_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        record = json.loads(line)
                        message = record["output"]["choices"][0]["message"]
                        content = message.get("content")
                        if content is None:
                            totals["content_null"] += 1
                            no_code_tasks.add(task_id)
                        else:
                            totals["content_non_null"] += 1
                            if not re.search(r"```python\s+.+?(?:```|$)", str(content), re.DOTALL):
                                totals["lm_messages_without_python_code"] += 1
                                no_code_tasks.add(task_id)
                        if message.get("reasoning_content") is None:
                            totals["reasoning_content_null"] += 1
                    except Exception:
                        totals["malformed_lm_log_rows"] += 1
        if api_path.is_file():
            with api_path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        url = str(json.loads(line).get("url", ""))
                        if url.endswith("/complete_task") or url.endswith("/message"):
                            totals["complete_task_api_calls"] += 1
                    except Exception:
                        totals["malformed_api_log_rows"] += 1
        if env_path.is_file():
            text = env_path.read_text(encoding="utf-8", errors="replace")
            no_code_count = text.count("No code available to execute")
            totals["no_code_observations"] += no_code_count
            if no_code_count:
                no_code_tasks.add(task_id)
            complete_count = text.count("apis.supervisor.complete_task(")
            totals["complete_task_action_count"] += complete_count
            if complete_count:
                totals["complete_task_task_count"] += 1
            if "Execution failed. Traceback" in text:
                error_tasks.add(task_id)
            if "Syntax error in line:" in text:
                syntax_error_tasks.add(task_id)
    totals["total_tokens"] = totals["input_tokens"] + totals["output_tokens"]
    # Keep zero-valued interface counters explicit in summary.json. Their
    # absence would make a completed audit indistinguishable from an audit
    # whose parser never inspected the field.
    for key in (
        "finished_markers",
        "lm_calls",
        "api_calls",
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "content_null",
        "content_non_null",
        "reasoning_content_null",
        "lm_messages_without_python_code",
        "no_code_observations",
        "complete_task_api_calls",
        "complete_task_action_count",
        "complete_task_task_count",
        "malformed_lm_log_rows",
        "malformed_api_log_rows",
        "malformed_usage_files",
    ):
        totals.setdefault(key, 0)
    return {
        **dict(totals),
        "python_error_task_count": len(error_tasks),
        "python_error_task_ids": sorted(error_tasks),
        "syntax_error_task_count": len(syntax_error_tasks),
        "syntax_error_task_ids": sorted(syntax_error_tasks),
        "no_code_task_count": len(no_code_tasks),
        "no_code_task_ids": sorted(no_code_tasks),
        "max_step_task_count": len(max_step_tasks),
        "max_step_task_ids": sorted(max_step_tasks),
        "missing_task_dir_ids": missing_task_dirs,
        "missing_lm_log_ids": missing_lm_logs,
        "missing_api_log_ids": missing_api_logs,
    }


def audit_task_status(
    status_path: Path, task_ids: list[str], individual: dict[str, Any]
) -> dict[str, Any]:
    rows, malformed_lines = read_jsonl(status_path)
    by_task: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    missing_id_rows = 0
    for row in rows:
        task_id = row.get("task_id")
        if isinstance(task_id, str):
            by_task[task_id].append(row)
        else:
            missing_id_rows += 1
    expected = set(task_ids)
    actual = set(by_task)
    duplicates = {task_id: len(items) for task_id, items in by_task.items() if len(items) > 1}
    latest = {task_id: items[-1] for task_id, items in by_task.items()}
    evaluation_error_ids = sorted(
        task_id for task_id, row in latest.items() if row.get("status") == "evaluation_error"
    )
    status_success_mismatch: list[str] = []
    test_count_mismatch: list[str] = []
    for task_id in sorted(expected & actual):
        row = latest[task_id]
        expected_success = bool(individual[task_id].get("success"))
        observed_success = row.get("status") == "success"
        if expected_success != observed_success:
            status_success_mismatch.append(task_id)
        if "passed_tests" in row and "failed_tests" in row:
            official = individual[task_id]
            if int(row["passed_tests"]) != len(official.get("passes", [])) or int(
                row["failed_tests"]
            ) != len(official.get("failures", [])):
                test_count_mismatch.append(task_id)
    completed_indices = [row.get("completed_index") for row in rows]
    integer_indices = [index for index in completed_indices if isinstance(index, int)]
    return {
        "path": str(status_path),
        "exists": status_path.is_file(),
        "raw_row_count": len(rows),
        "malformed_line_numbers": malformed_lines,
        "rows_without_task_id": missing_id_rows,
        "unique_task_count": len(by_task),
        "duplicate_task_ids": sorted(duplicates),
        "duplicate_row_counts": duplicates,
        "missing_task_ids": sorted(expected - actual),
        "extra_task_ids": sorted(actual - expected),
        "evaluation_error_task_ids": evaluation_error_ids,
        "status_success_mismatch_ids": status_success_mismatch,
        "test_count_mismatch_ids": test_count_mismatch,
        "completed_index_duplicate_count": len(integer_indices) - len(set(integer_indices)),
        "strictly_one_row_per_task": len(rows) == len(task_ids) and not duplicates,
        "latest_rows_cover_dataset": actual == expected,
    }


def parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value)
    except ValueError:
        return None


def audit_run(experiment: Path, status_audit: dict[str, Any]) -> dict[str, Any]:
    run_path = experiment / "logs" / "run.log"
    launcher_path = experiment / "logs" / "launcher.log"
    exit_path = experiment / "logs" / "run_exit_code.txt"
    run_text = run_path.read_text(encoding="utf-8", errors="replace") if run_path.is_file() else ""
    launcher_text = (
        launcher_path.read_text(encoding="utf-8", errors="replace")
        if launcher_path.is_file()
        else ""
    )
    combined = run_text + "\n" + launcher_text
    context_overflow_pattern = re.compile(
        r"(?:maximum context length is \d+ tokens|"
        r"(?:max_tokens|max_completion_tokens).{0,120}too large)",
        flags=re.IGNORECASE,
    )
    context_overflow_task_ids: list[str] = []
    current_task_id: str | None = None
    for line in run_text.splitlines():
        task_match = re.search(r"Task ID:\s*([^\s│]+)", line)
        if task_match:
            current_task_id = task_match.group(1)
        if (
            "Encountered BREAKING_ERROR" in line
            and context_overflow_pattern.search(line)
            and current_task_id is not None
        ):
            context_overflow_task_ids.append(current_task_id)
    starts = re.findall(r"^run_started_at=(.+)$", run_text, flags=re.MULTILINE)
    finishes = re.findall(r"^run_finished_at=(.+)$", run_text, flags=re.MULTILINE)
    embedded_exit_codes = [
        int(value) for value in re.findall(r"^run_exit_code=(-?\d+)$", run_text, flags=re.MULTILINE)
    ]
    final_exit_code: int | None = None
    if exit_path.is_file():
        try:
            final_exit_code = int(exit_path.read_text(encoding="utf-8").strip())
        except ValueError:
            final_exit_code = None
    start = parse_iso(starts[0].strip()) if starts else None
    end = parse_iso(finishes[-1].strip()) if finishes else None
    duration = (end - start).total_seconds() if start and end else None
    fatal_patterns = {
        "cuda_oom": r"CUDA out of memory",
        "killed": r"(?:^|\n)Killed(?:\n|$)",
        "engine_failure": r"Engine core proc failed|EngineDeadError|engine process.*died",
        "connection_failure": r"Connection refused|APIConnectionError|ConnectionError",
        "uncaught_runtime_error": r"^RuntimeError:",
    }
    fatal_counts = {
        name: len(re.findall(pattern, combined, flags=re.IGNORECASE | re.MULTILINE))
        for name, pattern in fatal_patterns.items()
    }
    anomalies: list[str] = []
    if final_exit_code is None:
        anomalies.append("final_exit_code_missing_or_invalid")
    elif final_exit_code != 0:
        anomalies.append(f"final_exit_code_{final_exit_code}")
    if len(starts) != len(finishes):
        anomalies.append("unbalanced_run_start_finish_markers")
    if any(code != 0 for code in embedded_exit_codes):
        anomalies.append("prior_nonzero_run_exit_detected")
    if status_audit["duplicate_task_ids"]:
        anomalies.append("duplicate_task_status_rows_from_resume_or_retry")
    if status_audit["malformed_line_numbers"]:
        anomalies.append("malformed_task_status_rows")
    if status_audit["evaluation_error_task_ids"]:
        anomalies.append("per_task_evaluation_error")
    if not status_audit["latest_rows_cover_dataset"]:
        anomalies.append("latest_task_status_does_not_cover_dataset")
    for name, count in fatal_counts.items():
        if count:
            anomalies.append(name)
    return {
        "run_log": str(run_path),
        "launcher_log": str(launcher_path),
        "run_attempt_count": len(starts),
        "run_finish_count": len(finishes),
        "recovery_detected": len(starts) > 1 or bool(status_audit["duplicate_task_ids"]),
        "run_started_at": starts[0].strip() if starts else None,
        "run_finished_at": finishes[-1].strip() if finishes else None,
        "duration_seconds": duration,
        "embedded_exit_codes": embedded_exit_codes,
        "final_exit_code": final_exit_code,
        "task_execution_failure_observations": run_text.count("Execution failed. Traceback"),
        "task_syntax_error_observations": run_text.count("Syntax error in line:"),
        "context_overflow_events": len(context_overflow_task_ids),
        "context_overflow_task_count": len(set(context_overflow_task_ids)),
        "context_overflow_task_ids": sorted(set(context_overflow_task_ids)),
        "fatal_pattern_counts": fatal_counts,
        "anomalies": sorted(set(anomalies)),
    }


def transition(target: dict[str, Any], other: dict[str, Any]) -> dict[str, Any]:
    target_success = set(target["success_ids"])
    other_success = set(other["success_ids"])
    universe = set(target["individual"])
    return {
        "comparison_label": other["label"],
        "both_success": len(target_success & other_success),
        "comparison_only_success": len(other_success - target_success),
        "target_only_success": len(target_success - other_success),
        "both_failed": len(universe - target_success - other_success),
        "gained_task_ids": sorted(target_success - other_success),
        "regressed_task_ids": sorted(other_success - target_success),
        "common_success_task_ids": sorted(target_success & other_success),
    }


def git_commit(workspace: Path) -> str | None:
    try:
        return subprocess.check_output(
            ["git", "-C", str(workspace), "rev-parse", "HEAD"],
            text=True,
            stderr=subprocess.DEVNULL,
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def parse_metadata_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def compact_checkpoint_value(
    value: Any, path: str = "", omitted: dict[str, int] | None = None
) -> Any:
    """Keep checkpoint provenance useful without copying long per-step histories.

    Training metadata can contain thousands of per-sample or per-step records.
    The report needs their source hash and high-level fields, not a second copy
    of those histories. Short collections remain intact; long collections are
    represented by a deterministic count marker.
    """
    if omitted is None:
        omitted = {}
    if isinstance(value, dict):
        return {
            str(key): compact_checkpoint_value(
                item, f"{path}.{key}" if path else str(key), omitted
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        if len(value) > 16:
            omitted[path or "$"] = len(value)
            return {"collection_omitted": True, "item_count": len(value)}
        return [
            compact_checkpoint_value(item, f"{path}[{index}]", omitted)
            for index, item in enumerate(value)
        ]
    return value


def load_checkpoint_metadata(args: argparse.Namespace) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    metadata_path = args.checkpoint_metadata.resolve() if args.checkpoint_metadata else None
    if metadata_path:
        omitted: dict[str, int] = {}
        metadata.update(compact_checkpoint_value(read_json(metadata_path), omitted=omitted))
        if omitted:
            metadata["omitted_large_collections"] = omitted
        metadata["metadata_file"] = str(metadata_path)
        metadata["metadata_file_sha256"] = sha256(metadata_path)
    if args.checkpoint_path:
        checkpoint_path = args.checkpoint_path.resolve()
        metadata["path"] = str(checkpoint_path)
        metadata["exists"] = checkpoint_path.exists()
        if checkpoint_path.is_dir():
            for name in ("config.json", "model.safetensors.index.json", "tokenizer_config.json"):
                path = checkpoint_path / name
                if path.is_file():
                    metadata[f"{name}_sha256"] = sha256(path)
            shards = sorted(checkpoint_path.glob("*.safetensors"))
            metadata["safetensor_shard_count"] = len(shards)
            metadata["safetensor_total_bytes"] = sum(path.stat().st_size for path in shards)
    if args.checkpoint_label is not None:
        metadata["label"] = args.checkpoint_label
    if args.checkpoint_epoch is not None:
        metadata["epoch"] = args.checkpoint_epoch
    if args.checkpoint_sha256 is not None:
        metadata["weights_sha256"] = args.checkpoint_sha256
    for item in args.checkpoint_meta:
        if "=" not in item:
            raise ValueError(f"--checkpoint-meta must be KEY=VALUE: {item}")
        key, value = item.split("=", 1)
        if not key:
            raise ValueError("--checkpoint-meta key cannot be empty")
        metadata[key] = parse_metadata_value(value)
    return metadata


def appworld_version(experiment: Path) -> str | None:
    path = experiment / "data" / "version.txt"
    return path.read_text(encoding="utf-8").strip() if path.is_file() else None


def markdown_list(values: list[str], empty: str = "无") -> str:
    return "、".join(f"`{value}`" for value in values) if values else empty


def human_duration(seconds: float | None) -> str:
    if seconds is None:
        return "未知"
    total = int(seconds)
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours} 小时 {minutes} 分 {secs} 秒"


def render_report(summary: dict[str, Any], checkpoint: dict[str, Any]) -> str:
    target = summary["target"]
    comparisons = summary["comparisons"]
    runtime = summary["runtime"]
    status = summary["task_status_audit"]
    run = summary["run_audit"]
    metric_rows = [
        "| 实验 | 成功任务 | TGC | 成功场景 | SGC | 测试项通过率 |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for item in [*comparisons, target]:
        aggregate = item["aggregate"]
        tests = item["evaluator_tests"]
        metric_rows.append(
            f"| {str(item['label']).replace('|', '/')} | {item['success_count']}/{summary['task_count']} "
            f"| {aggregate['task_goal_completion']:.1f} | "
            f"{item['successful_scenario_count']}/{summary['scenario_count']} "
            f"| {aggregate['scenario_goal_completion']:.1f} "
            f"| {tests['passed']}/{tests['total']} ({tests['pass_percentage']:.1f}%) |"
        )
    transition_lines: list[str] = []
    for item in summary["transitions"]:
        transition_lines.extend(
            [
                f"### 相对 {item['comparison_label']}",
                "",
                "| 两者成功 | 对照独有成功 | 当前独有成功 | 两者失败 |",
                "|---:|---:|---:|---:|",
                f"| {item['both_success']} | {item['comparison_only_success']} | "
                f"{item['target_only_success']} | {item['both_failed']} |",
                "",
                f"当前新增成功：{markdown_list(item['gained_task_ids'])}",
                "",
                f"当前退化：{markdown_list(item['regressed_task_ids'])}",
                "",
            ]
        )
    checkpoint_text = json.dumps(checkpoint, ensure_ascii=False, indent=2)
    anomaly_text = markdown_list(run["anomalies"])
    recovery = run.get("recovery_details", {})
    if recovery:
        recovery_text = (
            f"首次运行因 {recovery.get('cause')} 退出（退出码 "
            f"{recovery.get('first_run_exit_code')}）；清除单个不完整任务 "
            f"{recovery.get('incomplete_task')} 后恢复运行，最终退出码 "
            f"{recovery.get('resumed_run_exit_code')}。"
        )
    else:
        recovery_text = "未记录额外恢复操作。"
    report = [
        f"# {target['label']} AppWorld 完整 Dev 评测报告",
        "",
        "## 1. 结论",
        "",
        f"本实验已覆盖 Dev 的 {summary['task_count']} 个唯一任务和 "
        f"{summary['scenario_count']} 个场景。官方结果为 "
        f"{target['success_count']}/{summary['task_count']} 个任务成功，"
        f"TGC={target['aggregate']['task_goal_completion']:.1f}，"
        f"SGC={target['aggregate']['scenario_goal_completion']:.1f}。",
        "",
        f"逐题 evaluator 共通过 {target['evaluator_tests']['passed']}/"
        f"{target['evaluator_tests']['total']} 个测试项"
        f"（{target['evaluator_tests']['pass_percentage']:.1f}%）。",
        "",
        "## 2. 官方指标与对照",
        "",
        *metric_rows,
        "",
        "## 3. 逐题转移",
        "",
        *transition_lines,
        "当前成功任务：" + markdown_list(target["success_ids"]),
        "",
        "当前完整成功场景：" + markdown_list(target["successful_scenarios"]),
        "",
        "## 4. 57 题完整性与唯一性",
        "",
        "| 检查 | 结果 |",
        "|---|---:|",
        f"| dataset 任务数/唯一数 | {summary['task_count']}/{summary['dataset_unique_count']} |",
        f"| 官方 individual 任务数 | {summary['task_count']} |",
        f"| task_status 原始行数 | {status['raw_row_count']} |",
        f"| task_status 唯一任务数 | {status['unique_task_count']} |",
        f"| 每题严格一行 | {status['strictly_one_row_per_task']} |",
        f"| 重复 task ID | {markdown_list(status['duplicate_task_ids'])} |",
        f"| 缺失 task ID | {markdown_list(status['missing_task_ids'])} |",
        f"| 多余 task ID | {markdown_list(status['extra_task_ids'])} |",
        f"| evaluator_error 任务 | {markdown_list(status['evaluation_error_task_ids'])} |",
        f"| 状态与官方结果不一致 | {markdown_list(status['status_success_mismatch_ids'])} |",
        "",
        "若恢复运行导致同一任务出现多行，汇总使用文件中最后一行，同时保留重复行审计。"
        "官方 individual 与 Dev split 的集合必须严格一致，否则脚本拒绝生成报告。",
        "",
        "## 5. 输出接口审计",
        "",
        "| 指标 | 数量 |",
        "|---|---:|",
        f"| LM 调用 | {runtime.get('lm_calls', 0):,} |",
        f"| message.content 非空 | {runtime.get('content_non_null', 0):,} |",
        f"| message.content=null | {runtime.get('content_null', 0):,} |",
        f"| 无 Python code 的 LM 消息 | {runtime.get('lm_messages_without_python_code', 0):,} |",
        f"| No code available observation | {runtime.get('no_code_observations', 0):,} |",
        f"| 受影响任务 | {runtime.get('no_code_task_count', 0)} |",
        f"| AppWorld API 调用 | {runtime.get('api_calls', 0):,} |",
        f"| 含 complete_task action 的任务 | {runtime.get('complete_task_task_count', 0)}/{summary['task_count']} |",
        f"| Python 执行错误任务 | {runtime.get('python_error_task_count', 0)} |",
        f"| Python 语法错误任务 | {runtime.get('syntax_error_task_count', 0)} |",
        f"| 达到 50 次 LM 调用的任务 | {runtime.get('max_step_task_count', 0)} |",
        "",
        "## 6. 运行与恢复审计",
        "",
        "| 指标 | 值 |",
        "|---|---:|",
        f"| run_started_at 记录数 | {run['run_attempt_count']} |",
        f"| run_finished_at 记录数 | {run['run_finish_count']} |",
        f"| 检测到恢复/重试 | {run['recovery_detected']} |",
        f"| 最终退出码 | {run['final_exit_code']} |",
        f"| 历次退出码 | {run['embedded_exit_codes']} |",
        f"| 首次开始至最终结束 | {human_duration(run['duration_seconds'])} |",
        f"| 任务内执行失败 observation | {run['task_execution_failure_observations']} |",
        f"| 任务内语法错误 observation | {run['task_syntax_error_observations']} |",
        f"| 上下文溢出终止事件 | {run.get('context_overflow_events', 0)} |",
        f"| 上下文溢出任务 | {run.get('context_overflow_task_count', 0)} |",
        f"| 运行/恢复异常 | {anomaly_text} |",
        "",
        "上下文溢出任务：" + markdown_list(run.get("context_overflow_task_ids", [])),
        "",
        recovery_text,
        "",
        "任务内 Python 错误属于 agent 轨迹质量统计；CUDA OOM、engine failure、连接失败、"
        "非零进程退出和恢复状态冲突才列为运行异常。",
        "",
        "## 7. Checkpoint 元数据",
        "",
        "```json",
        checkpoint_text,
        "```",
        "",
        "## 8. 产物",
        "",
        "- `REPORT.md`：本报告。",
        "- `summary.json`：机器可读指标、逐题转移与审计。",
        "- `manifest.json`：代码、数据、checkpoint 与比较实验来源。",
        "- `command.txt`：实际评测命令。",
        "- `artifacts.sha256`：核心报告输入和输出的 SHA256。",
        "- `task_status.jsonl`：逐题即时状态；恢复时可能追加重复任务。",
        "- `experiments/outputs/.../evaluations/dev.json`：官方聚合与逐题评测。",
        "",
    ]
    return "\n".join(report)


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    experiment = args.experiment.resolve()
    workspace = args.workspace.resolve()
    dataset_path = (
        args.dataset_file.resolve()
        if args.dataset_file
        else experiment / "data" / "datasets" / f"{args.dataset}.txt"
    )
    task_ids = load_task_ids(dataset_path, args.expected_tasks)
    scenarios = scenario_map(task_ids)
    target = load_score_snapshot(
        args.label,
        experiment,
        task_ids,
        args.appworld_experiment_name,
        args.dataset,
    )
    comparison_specs = [
        (args.base_label, args.base_experiment),
        (args.lora_label, args.lora_experiment),
    ]
    if args.epoch5_experiment:
        comparison_specs.append((args.epoch5_label, args.epoch5_experiment))
    comparisons = [
        load_score_snapshot(
            label,
            path.resolve(),
            task_ids,
            args.appworld_experiment_name,
            args.dataset,
        )
        for label, path in comparison_specs
    ]
    output_root = Path(target["output_root"])
    runtime = collect_runtime(output_root, task_ids)
    status_path = experiment / "task_status.jsonl"
    status_audit = audit_task_status(status_path, task_ids, target["individual"])
    run_audit = audit_run(experiment, status_audit)
    if not status_audit["latest_rows_cover_dataset"]:
        raise RuntimeError(
            "task_status latest rows do not cover the exact 57-task dataset; run is incomplete"
        )
    checkpoint = load_checkpoint_metadata(args)
    recovery_keys = (
        "recovery_cause",
        "recovery_incomplete_task",
        "recovery_action",
        "first_run_exit_code",
        "resumed_run_exit_code",
    )
    if any(key in checkpoint for key in recovery_keys):
        run_audit["recovery_details"] = {
            "cause": checkpoint.get("recovery_cause"),
            "incomplete_task": checkpoint.get("recovery_incomplete_task"),
            "action": checkpoint.get("recovery_action"),
            "first_run_exit_code": checkpoint.get("first_run_exit_code"),
            "resumed_run_exit_code": checkpoint.get("resumed_run_exit_code"),
        }
        if str(checkpoint.get("recovery_cause", "")).lower() == "recursionerror":
            run_audit["anomalies"] = sorted(
                set(run_audit["anomalies"]) | {"recovered_recursion_error"}
            )
    summary: dict[str, Any] = {
        "experiment": str(experiment),
        "task_count": len(task_ids),
        "dataset_unique_count": len(set(task_ids)),
        "scenario_count": len(scenarios),
        "target": target,
        "comparisons": comparisons,
        "transitions": [transition(target, item) for item in comparisons],
        "runtime": runtime,
        "task_status_audit": status_audit,
        "run_audit": run_audit,
        "checkpoint": checkpoint,
    }
    # Do not duplicate evaluator assertions/traces in the compact machine-readable summary.
    summary["target"] = {key: value for key, value in target.items() if key != "individual"}
    summary["comparisons"] = [
        {key: value for key, value in item.items() if key != "individual"}
        for item in comparisons
    ]
    run_command = args.run_command.strip()
    command_path = experiment / "command.txt"
    atomic_write_text(command_path, run_command + "\n")
    summary_path = experiment / "summary.json"
    atomic_write_json(summary_path, summary)
    script_path = Path(__file__).resolve()
    manifest = {
        "created_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "created_for": f"{args.label} AppWorld {args.dataset} evaluation report",
        "workspace": str(workspace),
        "workspace_git_commit": git_commit(workspace),
        "report_builder": str(script_path),
        "report_builder_sha256": sha256(script_path),
        "appworld_version": appworld_version(experiment),
        "dataset": args.dataset,
        "dataset_file": str(dataset_path),
        "dataset_sha256": sha256(dataset_path),
        "expected_task_count": args.expected_tasks,
        "appworld_experiment_name": args.appworld_experiment_name,
        "target_evaluation": target["evaluation_path"],
        "target_evaluation_sha256": target["evaluation_sha256"],
        "comparison_evaluations": [
            {
                "label": item["label"],
                "experiment": item["experiment"],
                "evaluation": item["evaluation_path"],
                "sha256": item["evaluation_sha256"],
            }
            for item in comparisons
        ],
        "checkpoint": checkpoint,
        "integrity_rules": {
            "dataset_exactly_57_unique": args.expected_tasks == 57,
            "official_individual_matches_dataset": True,
            "latest_task_status_covers_dataset": True,
            "duplicate_status_rows_reported_and_latest_row_used": True,
            "evaluator_assertions_omitted_from_report_artifacts": True,
        },
        "run_command_sha256": hashlib.sha256(
            (run_command + "\n").encode("utf-8")
        ).hexdigest(),
        "summary_sha256": sha256(summary_path),
    }
    manifest_path = experiment / "manifest.json"
    atomic_write_json(manifest_path, manifest)
    report_path = experiment / "REPORT.md"
    atomic_write_text(report_path, render_report(summary, checkpoint))
    artifact_paths = [
        report_path,
        summary_path,
        manifest_path,
        command_path,
        status_path,
        Path(target["evaluation_path"]),
        experiment / "logs" / "run.log",
        experiment / "logs" / "launcher.log",
    ]
    checksum_lines: list[str] = []
    seen: set[Path] = set()
    for path in artifact_paths:
        path = path.resolve()
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        try:
            display = str(path.relative_to(experiment))
        except ValueError:
            display = str(path)
        checksum_lines.append(f"{sha256(path)}  {display}")
    atomic_write_text(
        experiment / "artifacts.sha256", "\n".join(checksum_lines) + "\n"
    )
    return summary


def make_fixture_experiment(
    root: Path, name: str, task_ids: list[str], success_modulo: int
) -> Path:
    experiment = root / name
    dataset_path = experiment / "data" / "datasets" / "dev.txt"
    dataset_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_path.write_text("\n".join(task_ids) + "\n", encoding="utf-8")
    output_root = experiment / "experiments" / "outputs" / DEFAULT_APPWORLD_EXPERIMENT
    evaluation_path = output_root / "evaluations" / "dev.json"
    evaluation_path.parent.mkdir(parents=True, exist_ok=True)
    individual: dict[str, Any] = {}
    success_ids: set[str] = set()
    for index, task_id in enumerate(task_ids):
        success = index % success_modulo == 0
        if success:
            success_ids.add(task_id)
        individual[task_id] = {
            "success": success,
            "difficulty": index % 3 + 1,
            "num_tests": 2,
            "passes": [{"requirement": "fixture", "label": "no_op_pass"}],
            "failures": [] if success else [{"requirement": "fixture", "trace": "x", "label": "no_op_fail"}],
        }
        if success:
            individual[task_id]["passes"].append(
                {"requirement": "fixture", "label": "no_op_fail"}
            )
        task_dir = output_root / "tasks" / task_id
        (task_dir / "logs").mkdir(parents=True, exist_ok=True)
        (task_dir / "misc").mkdir(parents=True, exist_ok=True)
        (task_dir / "logs" / "lm_calls.jsonl").write_text(
            json.dumps(
                {
                    "output": {
                        "choices": [
                            {
                                "message": {
                                    "content": "```python\nprint(1)\n```",
                                    "reasoning_content": "fixture",
                                }
                            }
                        ]
                    }
                }
            )
            + "\n",
            encoding="utf-8",
        )
        (task_dir / "logs" / "api_calls.jsonl").write_text(
            '{"url":"/fixture"}\n', encoding="utf-8"
        )
        (task_dir / "logs" / "environment_io.md").write_text(
            "apis.supervisor.complete_task(status='success')\n", encoding="utf-8"
        )
        (task_dir / "misc" / "usage.json").write_text(
            '{"tokens":{"input_cache_miss":10,"input_cache_hit":0,"output":2}}\n',
            encoding="utf-8",
        )
        (task_dir / "misc" / "finished").write_text("", encoding="utf-8")
    scenarios = scenario_map(task_ids)
    successful_scenarios = sum(
        all(task_id in success_ids for task_id in ids) for ids in scenarios.values()
    )
    evaluation = {
        "aggregate": {
            "task_goal_completion": round(100 * len(success_ids) / len(task_ids), 1),
            "scenario_goal_completion": round(100 * successful_scenarios / len(scenarios), 1),
        },
        "individual": individual,
    }
    evaluation_path.write_text(
        json.dumps(evaluation, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rows = []
    for index, task_id in enumerate(task_ids, start=1):
        item = individual[task_id]
        rows.append(
            json.dumps(
                {
                    "completed_index": index,
                    "task_id": task_id,
                    "status": "success" if item["success"] else "failed",
                    "passed_tests": len(item["passes"]),
                    "failed_tests": len(item["failures"]),
                }
            )
        )
    (experiment / "task_status.jsonl").write_text("\n".join(rows) + "\n", encoding="utf-8")
    (experiment / "logs").mkdir(exist_ok=True)
    (experiment / "logs" / "run.log").write_text(
        "run_started_at=2026-09-15T10:00:00+08:00\n"
        "run_finished_at=2026-09-15T10:10:00+08:00\nrun_exit_code=0\n",
        encoding="utf-8",
    )
    (experiment / "logs" / "launcher.log").write_text("fixture\n", encoding="utf-8")
    (experiment / "logs" / "run_exit_code.txt").write_text("0\n", encoding="utf-8")
    (experiment / "data" / "version.txt").write_text("0.2.0.dev0\n", encoding="utf-8")
    return experiment


def self_test() -> None:
    with tempfile.TemporaryDirectory(prefix="appworld-report-fixture-") as temporary:
        root = Path(temporary)
        task_ids = [f"family_{index:02d}_{variant}" for index in range(19) for variant in range(1, 4)]
        target = make_fixture_experiment(root, "target", task_ids, 5)
        base = make_fixture_experiment(root, "base", task_ids, 7)
        lora = make_fixture_experiment(root, "lora", task_ids, 6)
        epoch5 = make_fixture_experiment(root, "epoch5", task_ids, 8)
        checkpoint_metadata = root / "checkpoint.json"
        checkpoint_metadata.write_text('{"epoch":4,"kind":"full_sft"}\n', encoding="utf-8")
        args = argparse.Namespace(
            experiment=target,
            workspace=root,
            base_experiment=base,
            lora_experiment=lora,
            epoch5_experiment=epoch5,
            dataset="dev",
            dataset_file=None,
            appworld_experiment_name=DEFAULT_APPWORLD_EXPERIMENT,
            expected_tasks=57,
            label="fixture target",
            base_label="fixture base",
            lora_label="fixture lora",
            epoch5_label="fixture epoch5",
            checkpoint_metadata=checkpoint_metadata,
            checkpoint_path=None,
            checkpoint_label="epoch-4",
            checkpoint_epoch=4,
            checkpoint_sha256=None,
            checkpoint_meta=["global_step=1280"],
            run_command="fixture-run --model epoch-4",
        )
        summary = build_report(args)
        if summary["task_count"] != 57 or summary["dataset_unique_count"] != 57:
            raise AssertionError("fixture task uniqueness failed")
        if summary["runtime"].get("content_null", 0) != 0:
            raise AssertionError("fixture content audit failed")
        if summary["runtime"].get("no_code_observations", 0) != 0:
            raise AssertionError("fixture no-code audit failed")
        for name in GENERATED_NAMES:
            if not (target / name).is_file():
                raise AssertionError(f"fixture did not produce {name}")
        json.loads((target / "summary.json").read_text(encoding="utf-8"))
        json.loads((target / "manifest.json").read_text(encoding="utf-8"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--experiment", type=Path)
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--base-experiment", "--baseline", dest="base_experiment", type=Path)
    parser.add_argument("--lora-experiment", "--lora", dest="lora_experiment", type=Path)
    parser.add_argument("--epoch5-experiment", "--epoch5", dest="epoch5_experiment", type=Path)
    parser.add_argument("--dataset", default="dev")
    parser.add_argument("--dataset-file", type=Path)
    parser.add_argument("--appworld-experiment-name", default=DEFAULT_APPWORLD_EXPERIMENT)
    parser.add_argument("--expected-tasks", type=int, default=57)
    parser.add_argument("--label", default="全参数 SFT checkpoint")
    parser.add_argument("--base-label", default="原始 Qwen3-8B")
    parser.add_argument("--lora-label", default="LoRA")
    parser.add_argument("--epoch5-label", default="full-SFT epoch-5")
    parser.add_argument("--checkpoint-metadata", type=Path)
    parser.add_argument("--checkpoint-path", type=Path)
    parser.add_argument("--checkpoint-label")
    parser.add_argument("--checkpoint-epoch", type=int)
    parser.add_argument("--checkpoint-sha256")
    parser.add_argument("--checkpoint-meta", action="append", default=[], metavar="KEY=VALUE")
    parser.add_argument("--run-command", "--command", dest="run_command")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_test:
        self_test()
        print(json.dumps({"self_test": "ok"}))
        return 0
    required = {
        "--experiment": args.experiment,
        "--workspace": args.workspace,
        "--base-experiment": args.base_experiment,
        "--lora-experiment": args.lora_experiment,
        "--run-command": args.run_command,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise SystemExit("Missing required arguments: " + ", ".join(missing))
    summary = build_report(args)
    print(
        json.dumps(
            {
                "status": "ok",
                "experiment": summary["experiment"],
                "task_count": summary["task_count"],
                "tgc": summary["target"]["aggregate"]["task_goal_completion"],
                "sgc": summary["target"]["aggregate"]["scenario_goal_completion"],
                "run_anomalies": summary["run_audit"]["anomalies"],
                "outputs": [str(Path(summary["experiment"]) / name) for name in GENERATED_NAMES],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
