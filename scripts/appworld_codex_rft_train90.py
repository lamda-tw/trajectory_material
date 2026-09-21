#!/usr/bin/env python3
"""Unattended, resumable 90-task AppWorld Codex RFT collection."""

from __future__ import annotations

import argparse
import collections
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import appworld_codex_rft_sampler as sampler


DEFAULT_SOURCE_ROOT = Path("/root/autodl-tmp/data/benchmarks/appworld/runtime")
DEFAULT_PROMPT = sampler.DEFAULT_PROMPT
DEFAULT_CODEX = sampler.DEFAULT_CODEX
SCHEMA_VERSION = "appworld-codex-rft-train90-v1"
SEMANTIC_GENERATION_ERRORS = (
    "codex_used_forbidden_tools",
    "unexpected_response_keys",
    "empty_policy_response",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, default=DEFAULT_SOURCE_ROOT)
    parser.add_argument("--prompt-template", type=Path, default=DEFAULT_PROMPT)
    parser.add_argument("--codex-bin", type=Path, default=DEFAULT_CODEX)
    parser.add_argument("--codex-model", default="gpt-5.6-sol")
    parser.add_argument("--reasoning-effort", default="high")
    parser.add_argument("--max-semantic-failures", type=int, default=10)
    parser.add_argument("--max-interactions", type=int, default=40)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--codex-timeout", type=int, default=900)
    parser.add_argument("--max-observation-chars", type=int, default=24000)
    parser.add_argument("--max-infrastructure-backoff", type=int, default=60)
    parser.add_argument("--worker-task", help=argparse.SUPPRESS)
    return parser.parse_args()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    temporary.write_text(text, encoding="utf-8")
    os.replace(temporary, path)


def atomic_json(path: Path, value: Any) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def atomic_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    text = "".join(
        json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        for value in values
    )
    atomic_text(path, text)


def append_jsonl(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        written = os.write(descriptor, payload)
        if written != len(payload):
            raise OSError(f"Short JSONL write: {path}")
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def train_ids(source_root: Path) -> tuple[Path, list[str]]:
    path = source_root / "data" / "datasets" / "train.txt"
    ids = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(ids) != 90 or len(set(ids)) != 90:
        raise RuntimeError(f"Expected 90 unique train tasks, found {len(ids)}/{len(set(ids))}")
    return path, ids


def state_path(root: Path, task_id: str) -> Path:
    return root / "shards" / task_id / "state.json"


def initial_state(task_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "terminal": False,
        "accepted": False,
        "abandoned": False,
        "semantic_failures": 0,
        "semantic_attempts": 0,
        "infrastructure_restarts": 0,
        "consecutive_infrastructure_errors": 0,
        "next_run_index": 1,
        "active_run": None,
        "records": [],
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def load_state(root: Path, task_id: str) -> dict[str, Any]:
    path = state_path(root, task_id)
    if not path.is_file():
        return initial_state(task_id)
    state = load_json(path)
    if state.get("task_id") != task_id:
        raise RuntimeError(f"State task mismatch: {path}")
    return state


def save_state(root: Path, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    atomic_json(state_path(root, state["task_id"]), state)


def relative_to_root(path: Path, root: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def classify_infrastructure(result: dict[str, Any]) -> bool:
    error = result.get("generation_error")
    if not error:
        return False
    return not any(marker in error for marker in SEMANTIC_GENERATION_ERRORS)


def worker_args(args: argparse.Namespace, shard: Path) -> SimpleNamespace:
    return SimpleNamespace(
        experiment_dir=shard,
        codex_bin=args.codex_bin,
        codex_model=args.codex_model,
        reasoning_effort=args.reasoning_effort,
        max_interactions=args.max_interactions,
        codex_timeout=args.codex_timeout,
        max_observation_chars=args.max_observation_chars,
    )


def record_raised_infrastructure_error(
    root: Path,
    shard: Path,
    task_id: str,
    run_index: int,
    semantic_attempt_index: int,
    exception: BaseException,
) -> str:
    path = shard / "infrastructure" / f"run_{run_index:04d}.json"
    value = {
        "schema_version": "appworld-codex-rft-infrastructure-event-v1",
        "task_id": task_id,
        "run_index": run_index,
        "semantic_attempt_index": semantic_attempt_index,
        "created_at": utc_now(),
        "error": f"{type(exception).__name__}:{exception}",
    }
    atomic_json(path, value)
    return relative_to_root(path, root)


def worker_main(args: argparse.Namespace) -> int:
    root = args.experiment_dir.resolve()
    source_root = args.source_root.resolve()
    task_id = str(args.worker_task)
    _, all_ids = train_ids(source_root)
    if task_id not in all_ids:
        raise ValueError(f"Task not in train.txt: {task_id}")

    shard = root / "shards" / task_id
    shard.mkdir(parents=True, exist_ok=True)
    runtime_root = shard / "runtime" / "appworld_root"
    sampler.prepare_runtime(source_root, runtime_root)
    os.environ["APPWORLD_ROOT"] = str(runtime_root)

    from appworld import update_root

    update_root(str(runtime_root))
    schema_path = shard / "policy_output_schema.json"
    atomic_json(schema_path, sampler.output_schema())
    base_prompt, public_task = sampler.render_public_prompt(task_id, args.prompt_template)

    state = load_state(root, task_id)
    if state["terminal"]:
        print(json.dumps({"event": "already_terminal", "task_id": task_id}), flush=True)
        return 0

    if state.get("active_run"):
        state["infrastructure_restarts"] += 1
        state["consecutive_infrastructure_errors"] += 1
        state["records"].append(
            {
                "kind": "interrupted_infrastructure",
                "detected_at": utc_now(),
                "active_run": state["active_run"],
            }
        )
        state["active_run"] = None
        save_state(root, state)

    local_args = worker_args(args, shard)
    while not state["terminal"]:
        if state["semantic_failures"] >= args.max_semantic_failures:
            state["terminal"] = True
            state["abandoned"] = True
            save_state(root, state)
            break

        semantic_attempt_index = state["semantic_failures"] + 1
        run_index = int(state["next_run_index"])
        state["next_run_index"] = run_index + 1
        state["active_run"] = {
            "run_index": run_index,
            "semantic_attempt_index": semantic_attempt_index,
            "pid": os.getpid(),
            "started_at": utc_now(),
        }
        save_state(root, state)

        result: dict[str, Any] | None = None
        result_path: str
        try:
            result = sampler.run_attempt_persistent(
                task_id=task_id,
                attempt_index=run_index,
                args=local_args,
                schema_path=schema_path,
                base_prompt=base_prompt,
                public_task=public_task,
            )
            result["run_index"] = run_index
            result["semantic_attempt_index"] = semantic_attempt_index
            trajectory_path = (
                shard
                / "attempts"
                / f"{task_id}__attempt_{run_index:02d}"
                / "trajectory.json"
            )
            atomic_json(trajectory_path, result)
            result_path = relative_to_root(trajectory_path, root)
            infrastructure = classify_infrastructure(result)
        except BaseException as exception:
            result_path = record_raised_infrastructure_error(
                root,
                shard,
                task_id,
                run_index,
                semantic_attempt_index,
                exception,
            )
            infrastructure = True
            result = None

        state["active_run"] = None
        if infrastructure:
            state["infrastructure_restarts"] += 1
            state["consecutive_infrastructure_errors"] += 1
            state["records"].append(
                {
                    "kind": "infrastructure_error",
                    "run_index": run_index,
                    "semantic_attempt_index": semantic_attempt_index,
                    "result_path": result_path,
                    "recorded_at": utc_now(),
                }
            )
            save_state(root, state)
            print(
                json.dumps(
                    {
                        "event": "infrastructure_retry",
                        "task_id": task_id,
                        "run_index": run_index,
                        "semantic_attempt_index": semantic_attempt_index,
                        "consecutive": state["consecutive_infrastructure_errors"],
                    }
                ),
                flush=True,
            )
            delay = min(
                args.max_infrastructure_backoff,
                2 ** min(state["consecutive_infrastructure_errors"], 6),
            )
            time.sleep(delay)
            continue

        assert result is not None
        state["consecutive_infrastructure_errors"] = 0
        state["semantic_attempts"] += 1
        accepted = bool(result["accepted"])
        state["records"].append(
            {
                "kind": "accepted" if accepted else "semantic_failure",
                "run_index": run_index,
                "semantic_attempt_index": semantic_attempt_index,
                "result_path": result_path,
                "recorded_at": utc_now(),
            }
        )
        if accepted:
            state["accepted"] = True
            state["terminal"] = True
            state["accepted_result_path"] = result_path
        else:
            state["semantic_failures"] += 1
            if state["semantic_failures"] >= args.max_semantic_failures:
                state["terminal"] = True
                state["abandoned"] = True
        save_state(root, state)
        print(
            json.dumps(
                {
                    "event": "semantic_attempt_complete",
                    "task_id": task_id,
                    "semantic_attempt_index": semantic_attempt_index,
                    "accepted": accepted,
                    "semantic_failures": state["semantic_failures"],
                    "terminal": state["terminal"],
                }
            ),
            flush=True,
        )

    atomic_json(
        shard / "summary.json",
        {
            "task_id": task_id,
            "accepted": state["accepted"],
            "abandoned": state["abandoned"],
            "semantic_attempts": state["semantic_attempts"],
            "semantic_failures": state["semantic_failures"],
            "infrastructure_restarts": state["infrastructure_restarts"],
            "finished_at": utc_now(),
        },
    )
    return 0


def terminal_state(root: Path, task_id: str) -> bool:
    path = state_path(root, task_id)
    return path.is_file() and bool(load_json(path).get("terminal"))


def live_summary(root: Path, ids: list[str], running: list[str]) -> dict[str, Any]:
    states = [load_state(root, task_id) for task_id in ids]
    return {
        "updated_at": utc_now(),
        "tasks_total": len(ids),
        "tasks_terminal": sum(state["terminal"] for state in states),
        "tasks_accepted": sum(state["accepted"] for state in states),
        "tasks_abandoned": sum(state["abandoned"] for state in states),
        "semantic_attempts": sum(state["semantic_attempts"] for state in states),
        "semantic_failures": sum(state["semantic_failures"] for state in states),
        "infrastructure_restarts": sum(state["infrastructure_restarts"] for state in states),
        "running_task_ids": sorted(running),
    }


def worker_command(args: argparse.Namespace, task_id: str) -> list[str]:
    return [
        sys.executable,
        str(Path(__file__).resolve()),
        "--experiment-dir",
        str(args.experiment_dir),
        "--source-root",
        str(args.source_root),
        "--prompt-template",
        str(args.prompt_template),
        "--codex-bin",
        str(args.codex_bin),
        "--codex-model",
        args.codex_model,
        "--reasoning-effort",
        args.reasoning_effort,
        "--max-semantic-failures",
        str(args.max_semantic_failures),
        "--max-interactions",
        str(args.max_interactions),
        "--codex-timeout",
        str(args.codex_timeout),
        "--max-observation-chars",
        str(args.max_observation_chars),
        "--max-infrastructure-backoff",
        str(args.max_infrastructure_backoff),
        "--worker-task",
        task_id,
    ]


def initialize_manifest(
    args: argparse.Namespace,
    root: Path,
    train_path: Path,
    ids: list[str],
) -> None:
    path = root / "manifest.json"
    expected = {
        "schema_version": SCHEMA_VERSION,
        "source_train_file": str(train_path),
        "train_txt_sha256": sha256_path(train_path),
        "train_task_count": len(ids),
        "selected_task_ids": ids,
        "policy_model": args.codex_model,
        "reasoning_effort": args.reasoning_effort,
        "temperature": None,
        "thread_mode": "one_persistent_thread_per_full_attempt",
        "max_semantic_failures_per_task": args.max_semantic_failures,
        "max_interactions_per_attempt": args.max_interactions,
        "workers": args.workers,
        "stop_on_first_success": True,
        "infrastructure_errors_count_as_semantic_failures": False,
        "data_boundary": {
            "policy_task_loader": "Task.load(load_ground_truth=False)",
            "policy_visible": [
                "official_react_prompt",
                "task_spec",
                "own_prior_actions",
                "credential_redacted_environment_observations",
            ],
            "policy_hidden": [
                "ground_truth",
                "solution",
                "ground_truth_api_calls",
                "evaluator_assertions",
                "prior_teacher_trajectories",
                "credential_values",
            ],
            "ground_truth_use": "terminal official evaluator only",
        },
    }
    if path.is_file():
        current = load_json(path)
        for key, value in expected.items():
            if current.get(key) != value:
                raise RuntimeError(f"Resume manifest mismatch for {key}")
        return
    expected["created_at"] = utc_now()
    expected["controller_sha256"] = sha256_path(Path(__file__).resolve())
    expected["sampler_sha256"] = sha256_path(Path(sampler.__file__).resolve())
    atomic_json(path, expected)


def controller_main(args: argparse.Namespace) -> int:
    root = args.experiment_dir.resolve()
    args.experiment_dir = root
    args.source_root = args.source_root.resolve()
    args.prompt_template = args.prompt_template.resolve()
    args.codex_bin = args.codex_bin.resolve()
    if args.workers < 1:
        raise ValueError("workers must be positive")
    root.mkdir(parents=True, exist_ok=True)
    train_path, ids = train_ids(args.source_root)
    initialize_manifest(args, root, train_path, ids)

    pending = collections.deque(task_id for task_id in ids if not terminal_state(root, task_id))
    running: dict[str, tuple[subprocess.Popen[Any], Any]] = {}
    crash_counts: collections.Counter[str] = collections.Counter()
    last_live_write = 0.0

    while pending or running:
        while pending and len(running) < args.workers:
            task_id = pending.popleft()
            if terminal_state(root, task_id):
                continue
            log_path = root / "logs" / f"{task_id}.log"
            log_path.parent.mkdir(parents=True, exist_ok=True)
            handle = log_path.open("a", encoding="utf-8")
            handle.write(f"\n[{utc_now()}] controller launch\n")
            handle.flush()
            process = subprocess.Popen(
                worker_command(args, task_id),
                cwd=str(Path(__file__).resolve().parents[1]),
                stdout=handle,
                stderr=subprocess.STDOUT,
                text=True,
            )
            running[task_id] = (process, handle)
            print(
                json.dumps(
                    {
                        "event": "worker_launched",
                        "task_id": task_id,
                        "pid": process.pid,
                        "running": len(running),
                        "pending": len(pending),
                    }
                ),
                flush=True,
            )

        for task_id, (process, handle) in list(running.items()):
            returncode = process.poll()
            if returncode is None:
                continue
            handle.write(f"[{utc_now()}] controller observed exit={returncode}\n")
            handle.close()
            del running[task_id]
            if terminal_state(root, task_id):
                state = load_state(root, task_id)
                print(
                    json.dumps(
                        {
                            "event": "task_terminal",
                            "task_id": task_id,
                            "accepted": state["accepted"],
                            "semantic_attempts": state["semantic_attempts"],
                            "semantic_failures": state["semantic_failures"],
                            "infrastructure_restarts": state["infrastructure_restarts"],
                        }
                    ),
                    flush=True,
                )
            else:
                crash_counts[task_id] += 1
                append_jsonl(
                    root / "controller_worker_crashes.jsonl",
                    {
                        "task_id": task_id,
                        "returncode": returncode,
                        "crash_index": crash_counts[task_id],
                        "recorded_at": utc_now(),
                    },
                )
                pending.append(task_id)
                print(
                    json.dumps(
                        {
                            "event": "worker_requeued",
                            "task_id": task_id,
                            "returncode": returncode,
                            "crash_index": crash_counts[task_id],
                        }
                    ),
                    flush=True,
                )

        now = time.monotonic()
        if now - last_live_write >= 10:
            current = live_summary(root, ids, list(running))
            atomic_json(root / "live_summary.json", current)
            last_live_write = now
        time.sleep(1)

    summary, audit = consolidate_and_audit(root, ids)
    atomic_json(root / "summary.json", summary)
    atomic_json(root / "AUDIT.json", audit)
    atomic_text(root / "REPORT_CN.md", build_report_cn(summary, audit))
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    return 0


def load_record_result(root: Path, record: dict[str, Any]) -> dict[str, Any] | None:
    path_text = record.get("result_path")
    if not isinstance(path_text, str):
        return None
    path = root / path_text
    if not path.is_file():
        return None
    value = load_json(path)
    if value.get("schema_version", "").startswith("appworld-codex-rft-attempt"):
        return value
    return None


def sensitive_values(value: Any) -> list[str]:
    fragments = sampler.SENSITIVE_OBSERVATION_KEY_FRAGMENTS
    placeholders = {
        "string",
        "bearer",
        "integer",
        "number",
        "null",
        "none",
        "<redacted>",
        "<redacted_jwt>",
    }
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            if (
                any(fragment in str(key).lower() for fragment in fragments)
                and isinstance(item, str)
                and len(item) >= 6
                and item.lower() not in placeholders
            ):
                found.append(item)
            else:
                found.extend(sensitive_values(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(sensitive_values(item))
    return found


def consolidate_and_audit(
    root: Path,
    ids: list[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    task_results: list[dict[str, Any]] = []
    semantic_results: list[dict[str, Any]] = []
    accepted_results: list[dict[str, Any]] = []
    failed_results: list[dict[str, Any]] = []
    infrastructure_records: list[dict[str, Any]] = []

    for task_id in ids:
        state = load_state(root, task_id)
        if not state["terminal"]:
            raise RuntimeError(f"Cannot consolidate nonterminal task: {task_id}")
        for record in state["records"]:
            kind = record.get("kind")
            result = load_record_result(root, record)
            if kind in {"accepted", "semantic_failure"}:
                if result is None:
                    raise RuntimeError(f"Missing semantic result: {task_id} {record}")
                semantic_results.append(result)
                if kind == "accepted":
                    accepted_results.append(result)
                else:
                    failed_results.append(result)
            elif "infrastructure" in str(kind):
                infrastructure_records.append({"task_id": task_id, **record})
        task_results.append(
            {
                "task_id": task_id,
                "status": "accepted" if state["accepted"] else "abandoned",
                "accepted": state["accepted"],
                "abandoned": state["abandoned"],
                "semantic_attempts": state["semantic_attempts"],
                "semantic_failures": state["semantic_failures"],
                "infrastructure_restarts": state["infrastructure_restarts"],
                "accepted_result_path": state.get("accepted_result_path"),
            }
        )

    atomic_jsonl(root / "attempts.jsonl", semantic_results)
    atomic_jsonl(root / "accepted_trajectories.jsonl", accepted_results)
    atomic_jsonl(root / "failed_attempts.jsonl", failed_results)
    atomic_jsonl(root / "infrastructure_events.jsonl", infrastructure_records)
    atomic_jsonl(root / "task_results.jsonl", task_results)

    all_record_results: list[dict[str, Any]] = []
    for task_id in ids:
        state = load_state(root, task_id)
        for record in state["records"]:
            result = load_record_result(root, record)
            if result is not None:
                all_record_results.append(result)

    usage: dict[str, int] = {}
    item_types: set[str] = set()
    thread_ids: list[str] = []
    sensitive_checked = 0
    sensitive_leaks = 0
    redaction_markers = 0
    for result in all_record_results:
        thread_id = result.get("policy", {}).get("codex_thread_id")
        if isinstance(thread_id, str):
            thread_ids.append(thread_id)
        for key, value in result.get("codex_usage", {}).items():
            if isinstance(value, int):
                usage[key] = usage.get(key, 0) + value
        for step in result.get("steps", []):
            item_types.update(step.get("codex_event_item_types", []))
            policy_observation = str(step.get("policy_observation", ""))
            redaction_markers += policy_observation.count("<REDACTED")
            try:
                raw = json.loads(step.get("observation", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            for secret in sensitive_values(raw):
                sensitive_checked += 1
                if secret in policy_observation:
                    sensitive_leaks += 1

    forbidden_types = sorted(item_types - {"agent_message"})
    accepted_recoveries = sum(
        result.get("execution_failure_count", 0) > 0 for result in accepted_results
    )
    total_steps = sum(len(result.get("steps", [])) for result in semantic_results)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "finished_at": utc_now(),
        "tasks_total": len(ids),
        "tasks_accepted": sum(row["accepted"] for row in task_results),
        "tasks_abandoned": sum(row["abandoned"] for row in task_results),
        "semantic_attempts": len(semantic_results),
        "failed_semantic_attempts": len(failed_results),
        "infrastructure_events": len(infrastructure_records),
        "accepted_recovery_trajectories": accepted_recoveries,
        "total_steps_in_semantic_attempts": total_steps,
        "task_results": task_results,
    }
    audit = {
        "schema_version": "appworld-codex-rft-train90-audit-v1",
        "status": "passed"
        if not forbidden_types and sensitive_leaks == 0 and len(task_results) == 90
        else "failed",
        "terminal_task_count": len(task_results),
        "accepted_trajectory_count": len(accepted_results),
        "failed_semantic_attempt_count": len(failed_results),
        "infrastructure_event_count": len(infrastructure_records),
        "unique_thread_count": len(set(thread_ids)),
        "thread_count": len(thread_ids),
        "codex_event_item_types": sorted(item_types),
        "forbidden_codex_event_item_types": forbidden_types,
        "actual_sensitive_values_checked": sensitive_checked,
        "sensitive_values_in_policy_observations": sensitive_leaks,
        "policy_redaction_markers": redaction_markers,
        "accepted_recovery_trajectories": accepted_recoveries,
        "codex_usage": usage,
    }
    return summary, audit


def build_report_cn(summary: dict[str, Any], audit: dict[str, Any]) -> str:
    rows = summary["task_results"]
    distribution = collections.Counter(row["semantic_attempts"] for row in rows)
    dist_text = "、".join(f"{key}次:{value}题" for key, value in sorted(distribution.items()))
    usage = audit["codex_usage"]
    return f"""# AppWorld Codex RFT 全量 90 题无人值守实验

## 结论

- 终态任务：{summary['tasks_total']} / 90
- 成功任务：{summary['tasks_accepted']}
- 连续 10 次失败后放弃：{summary['tasks_abandoned']}
- 成功轨迹：{audit['accepted_trajectory_count']}
- 语义失败轨迹：{audit['failed_semantic_attempt_count']}
- 基础设施事件：{audit['infrastructure_event_count']}（不计入十次失败）
- 尝试次数分布：{dist_text}
- 成功轨迹中包含执行错误后恢复：{audit['accepted_recovery_trajectories']}
- 语义轨迹总交互步：{summary['total_steps_in_semantic_attempts']}

## 数据边界与审计

模型只看到公开 ReAct 提示、公开任务信息、本条 attempt 的历史动作，以及
凭据脱敏后的 observation。ground truth 只由官方 evaluator 用于最终 reward，
不会进入策略上下文。

- 审计状态：{audit['status']}
- Codex 事件类型：{audit['codex_event_item_types']}
- 禁止的工具事件：{audit['forbidden_codex_event_item_types']}
- 检查的实际敏感值：{audit['actual_sensitive_values_checked']}
- 模型可见 observation 中的敏感值泄漏：{audit['sensitive_values_in_policy_observations']}
- 独立 Codex threads：{audit['unique_thread_count']} / {audit['thread_count']}

## Codex 用量

- input tokens: {usage.get('input_tokens', 0)}
- cached input tokens: {usage.get('cached_input_tokens', 0)}
- output tokens: {usage.get('output_tokens', 0)}
- reasoning output tokens: {usage.get('reasoning_output_tokens', 0)}

## 主要文件

- accepted_trajectories.jsonl：成功轨迹
- failed_attempts.jsonl：完整语义失败轨迹
- infrastructure_events.jsonl：不计入失败上限的基础设施事件
- task_results.jsonl：90 题终态
- summary.json：汇总
- AUDIT.json：机器可读审计
- shards/<task_id>/：逐题状态、原始轨迹和逐回合 Codex 事件
"""


def main() -> int:
    args = parse_args()
    if args.max_semantic_failures != 10:
        raise ValueError("This run requires exactly 10 semantic failures per task")
    if args.worker_task:
        return worker_main(args)
    return controller_main(args)


if __name__ == "__main__":
    raise SystemExit(main())
