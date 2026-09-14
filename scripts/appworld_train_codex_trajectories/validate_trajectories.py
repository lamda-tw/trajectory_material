#!/usr/bin/env python3
"""Validate a candidate AppWorld trajectory in two fresh environments.

This module is intentionally model-agnostic.  It executes a pre-built plan,
captures AppWorld's real observations, runs the official evaluator, replays the
same actions from a clean task state, and rejects privileged or non-causal code.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from pathlib import Path
from typing import Any


FORBIDDEN_VISIBLE_TERMS = (
    "private_data",
    "test_data",
    "evaluation.py",
    "evaluation_code",
    "compiled_solution.py",
    "compiled_solution",
    "solution.py",
    "ground_truth",
    "world.task.ground_truth",
    "task.ground_truth",
    "access_token_from",
    "evaluator",
    "/data/tasks/",
)

DANGEROUS_MODULES = {
    "appworld",
    "glob",
    "importlib",
    "inspect",
    "os",
    "pathlib",
    "pickle",
    "requests",
    "shutil",
    "socket",
    "sqlite3",
    "sqlalchemy",
    "subprocess",
    "sys",
    "urllib",
}

DANGEROUS_CALLS = {
    "__import__",
    "breakpoint",
    "compile",
    "eval",
    "exec",
    "getattr",
    "globals",
    "help",
    "input",
    "locals",
    "open",
    "setattr",
    "vars",
}

FILE_METHODS = {
    "chdir",
    "glob",
    "iglob",
    "iterdir",
    "listdir",
    "open",
    "read_bytes",
    "read_text",
    "rglob",
    "scandir",
    "walk",
    "write_bytes",
    "write_text",
}

INTERNAL_ROOT_NAMES = {"ground_truth", "models", "requester", "task", "world"}

MUTATION_VERBS = {
    "accept",
    "add",
    "archive",
    "buy",
    "cancel",
    "create",
    "decline",
    "delete",
    "edit",
    "follow",
    "invite",
    "like",
    "move",
    "order",
    "post",
    "purchase",
    "reject",
    "remove",
    "rename",
    "reply",
    "send",
    "set",
    "share",
    "subscribe",
    "transfer",
    "unarchive",
    "unfollow",
    "unlike",
    "unsubscribe",
    "update",
    "upload",
}


class RejectedTrajectory(Exception):
    """A candidate violated a validation requirement."""


def sha256_file(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_dump_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    with temporary.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temporary, path)


def _extract_code_from_assistant(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("content")
    if not isinstance(value, str):
        return None
    matches = re.findall(r"```python\s*(.*?)```", value, flags=re.DOTALL | re.IGNORECASE)
    return matches[-1].strip() if matches else None


def normalize_plan(plan: Any, task_id: str) -> list[dict[str, Any]]:
    if isinstance(plan, dict):
        plan_task_id = plan.get("task_id")
        if plan_task_id is not None and str(plan_task_id) != task_id:
            raise RejectedTrajectory(
                f"plan_task_id_mismatch:{plan_task_id!s}!={task_id}"
            )
        raw_steps = plan.get("steps", plan.get("actions"))
    else:
        raw_steps = plan
    if not isinstance(raw_steps, list) or not raw_steps:
        raise RejectedTrajectory("plan_has_no_steps")

    steps: list[dict[str, Any]] = []
    for index, raw_step in enumerate(raw_steps, start=1):
        reasoning: Any = ""
        code: Any = None
        if isinstance(raw_step, dict):
            reasoning = raw_step.get(
                "reasoning", raw_step.get("rationale", raw_step.get("decision", ""))
            )
            code = raw_step.get("action_code", raw_step.get("code"))
            if code is None:
                code = _extract_code_from_assistant(raw_step.get("assistant"))
            if not reasoning and isinstance(raw_step.get("assistant"), dict):
                content = raw_step["assistant"].get("content", "")
                reasoning = re.sub(
                    r"```python\s*.*?```", "", str(content), flags=re.DOTALL | re.IGNORECASE
                ).strip()
        elif isinstance(raw_step, (list, tuple)) and len(raw_step) == 2:
            reasoning, code = raw_step
        if not isinstance(reasoning, str) or not isinstance(code, str) or not code.strip():
            raise RejectedTrajectory(f"invalid_step:{index}")
        steps.append(
            {
                "step_index": index,
                "reasoning": reasoning.strip(),
                "action_code": code.strip(),
            }
        )
    return steps


def _dotted_name(node: ast.AST) -> str | None:
    parts: list[str] = []
    current = node
    while isinstance(current, ast.Attribute):
        parts.append(current.attr)
        current = current.value
    if isinstance(current, ast.Name):
        parts.append(current.id)
        return ".".join(reversed(parts))
    return None


def _literal_payload(node: ast.AST) -> bool:
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, int)) and not isinstance(node.value, bool)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
        return _literal_payload(node.operand)
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return bool(node.elts) and all(_literal_payload(item) for item in node.elts)
    return False


def _target_names(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Name):
        return [node.id]
    if isinstance(node, (ast.List, ast.Tuple)):
        return [name for item in node.elts for name in _target_names(item)]
    return []


def _identifier_argument(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"id", "ids"} or lowered.endswith("_id") or lowered.endswith("_ids")


def _mutation_method(name: str) -> bool:
    pieces = set(name.lower().split("_"))
    return bool(pieces & MUTATION_VERBS) and name.lower() != "complete_task"


class SafetyVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.findings: list[str] = []
        self.literal_names: set[str] = set()
        self.api_call_count = 0

    def add(self, finding: str, node: ast.AST) -> None:
        self.findings.append(f"line_{getattr(node, 'lineno', 0)}:{finding}")

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            root = alias.name.split(".", 1)[0]
            if root in DANGEROUS_MODULES:
                self.add(f"forbidden_import:{root}", node)
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        root = (node.module or "").split(".", 1)[0]
        if root in DANGEROUS_MODULES:
            self.add(f"forbidden_import:{root}", node)
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if isinstance(node.ctx, ast.Load) and node.id in INTERNAL_ROOT_NAMES:
            self.add(f"forbidden_internal_name:{node.id}", node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        dotted = _dotted_name(node)
        if node.attr.startswith("__"):
            self.add("dunder_introspection", node)
        if node.attr in FILE_METHODS:
            self.add(f"forbidden_file_method:{node.attr}", node)
        if node.attr == "access_token_from":
            self.add("forbidden_access_token_shortcut", node)
        if dotted:
            parts = dotted.split(".")
            if any(part in {"ground_truth", "private_data", "test_data", "models"} for part in parts):
                self.add(f"forbidden_internal_attribute:{dotted}", node)
        self.generic_visit(node)

    def visit_Assign(self, node: ast.Assign) -> None:
        names = [name for target in node.targets for name in _target_names(target)]
        if _literal_payload(node.value):
            self.literal_names.update(names)
            for name in names:
                if _identifier_argument(name):
                    self.add(f"hardcoded_identifier_assignment:{name}", node)
        else:
            self.literal_names.difference_update(names)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        names = _target_names(node.target)
        if node.value is not None and _literal_payload(node.value):
            self.literal_names.update(names)
            for name in names:
                if _identifier_argument(name):
                    self.add(f"hardcoded_identifier_assignment:{name}", node)
        else:
            self.literal_names.difference_update(names)
        self.generic_visit(node)

    def visit_For(self, node: ast.For) -> None:
        names = _target_names(node.target)
        if _literal_payload(node.iter):
            self.literal_names.update(names)
        else:
            self.literal_names.difference_update(names)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        dotted = _dotted_name(node.func)
        short_name = dotted.rsplit(".", 1)[-1] if dotted else ""
        if dotted and dotted.startswith("apis."):
            self.api_call_count += 1
        if isinstance(node.func, ast.Name) and node.func.id in DANGEROUS_CALLS:
            self.add(f"forbidden_call:{node.func.id}", node)
        if short_name in FILE_METHODS:
            self.add(f"forbidden_file_call:{short_name}", node)
        if _mutation_method(short_name):
            for keyword in node.keywords:
                if keyword.arg and _identifier_argument(keyword.arg):
                    if _literal_payload(keyword.value) or (
                        isinstance(keyword.value, ast.Name)
                        and keyword.value.id in self.literal_names
                    ):
                        self.add(f"hardcoded_mutation_identifier:{keyword.arg}", keyword.value)
            for argument in node.args:
                if _literal_payload(argument) or (
                    isinstance(argument, ast.Name) and argument.id in self.literal_names
                ):
                    self.add("hardcoded_positional_mutation_argument", argument)
        self.generic_visit(node)


def static_validate_steps(steps: list[dict[str, Any]]) -> tuple[list[str], int]:
    visitor = SafetyVisitor()
    for step in steps:
        try:
            tree = ast.parse(step["action_code"])
        except SyntaxError as exception:
            raise RejectedTrajectory(
                f"step_{step['step_index']}:syntax_error:{exception.msg}"
            ) from exception
        before = len(visitor.findings)
        visitor.visit(tree)
        if len(visitor.findings) > before:
            new_findings = visitor.findings[before:]
            visitor.findings[before:] = [
                f"step_{step['step_index']}:{finding}" for finding in new_findings
            ]
    return sorted(set(visitor.findings)), visitor.api_call_count


def _walk_secret_values(value: Any, found: list[tuple[str, str]]) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered = str(key).lower()
            if lowered in {"password", "access_token"} and isinstance(item, str) and item:
                found.append((lowered, item))
            _walk_secret_values(item, found)
    elif isinstance(value, list):
        for item in value:
            _walk_secret_values(item, found)


def load_secret_markers(specs_path: Path, api_calls_path: Path) -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    specs = json.loads(specs_path.read_text(encoding="utf-8"))
    canary = specs.get("canary_string")
    if isinstance(canary, str) and canary:
        found.append(("canary_string", canary))
    if api_calls_path.is_file():
        _walk_secret_values(
            json.loads(api_calls_path.read_text(encoding="utf-8")), found
        )
    unique: dict[tuple[str, str], None] = {}
    for item in found:
        unique[item] = None
    return list(unique)


def scan_visible_content(
    instruction: str,
    steps: list[dict[str, Any]],
    secrets: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    visible = json.dumps(
        {"instruction": instruction, "steps": steps},
        ensure_ascii=False,
        separators=(",", ":"),
    )
    lowered = visible.lower()
    findings: list[dict[str, Any]] = []
    for term in FORBIDDEN_VISIBLE_TERMS:
        if term.lower() in lowered:
            findings.append({"kind": "privileged_term", "term": term})
    for kind, secret in secrets:
        if secret in visible:
            findings.append(
                {
                    "kind": "concrete_secret",
                    "secret_type": kind,
                    "value_sha256": hashlib.sha256(secret.encode("utf-8")).hexdigest(),
                }
            )
    return findings


def is_execution_error(output: str) -> bool:
    stripped = output.lstrip()
    return (
        stripped.startswith("Execution failed.")
        or stripped.startswith("No code available to execute.")
        or "Maximum number of executions" in stripped
    )


def safe_execution_error(output: str, secrets: list[tuple[str, str]]) -> str:
    summary = output
    for _kind, value in secrets:
        summary = summary.replace(value, "<redacted>")
    summary = re.sub(r"[\r\n]+", " ", summary).strip()
    return summary[:1500]


def count_api_log(log_path: Path, fallback: int) -> tuple[int, str]:
    if log_path.is_file():
        count = sum(1 for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip())
        return count, "appworld_api_calls_log"
    return fallback, "ast_static_lower_bound"


def evaluator_stats(tracker: Any) -> dict[str, Any]:
    return {
        "success": bool(tracker.success),
        "num_tests": int(tracker.num_tests),
        "num_passes": int(tracker.pass_count),
        "num_failures": int(tracker.fail_count),
    }


def prepare_runtime(source_root: Path, runtime_dir: Path) -> None:
    source_data = source_root / "data"
    if not source_data.is_dir():
        raise FileNotFoundError(f"source_data_missing:{source_data}")
    runtime_dir.mkdir(parents=True, exist_ok=True)
    runtime_data = runtime_dir / "data"
    if runtime_data.exists() or runtime_data.is_symlink():
        try:
            if not runtime_data.samefile(source_data):
                raise RuntimeError(f"runtime_data_points_elsewhere:{runtime_data}")
        except FileNotFoundError as exception:
            raise RuntimeError(f"broken_runtime_data_link:{runtime_data}") from exception
    else:
        runtime_data.symlink_to(source_data, target_is_directory=True)


def execute_once(
    task_id: str,
    experiment_name: str,
    steps: list[dict[str, Any]],
    ast_api_call_count: int,
    secrets: list[tuple[str, str]],
) -> dict[str, Any]:
    from appworld import AppWorld

    captured: list[dict[str, Any]] = []
    with AppWorld(
        task_id=task_id,
        experiment_name=experiment_name,
        load_ground_truth=True,
        raise_on_failure=True,
    ) as world:
        log_path = Path(world.output_logs_directory) / "api_calls.jsonl"
        for step in steps:
            output = world.execute(step["action_code"])
            captured.append(
                {
                    "step_index": step["step_index"],
                    "reasoning": step["reasoning"],
                    "action_code": step["action_code"],
                    "observation": output,
                }
            )
            if is_execution_error(output):
                detail = safe_execution_error(output, secrets)
                raise RejectedTrajectory(
                    f"step_{step['step_index']}:execution_failed:{detail}"
                )
            if world.task_completed() and step["step_index"] != len(steps):
                raise RejectedTrajectory(
                    f"step_{step['step_index']}:actions_follow_terminal_status"
                )
        completed = world.task_completed()
        if not completed:
            raise RejectedTrajectory("task_not_completed")
        tracker = world.evaluate(suppress_errors=True)
        evaluation = evaluator_stats(tracker)
        api_call_count, api_call_count_source = count_api_log(
            log_path, ast_api_call_count
        )
    return {
        "steps": captured,
        "task_completed": completed,
        "evaluation": evaluation,
        "api_call_count": api_call_count,
        "api_call_count_source": api_call_count_source,
    }


def validate_trajectory(
    *,
    source_root: Path,
    task_id: str,
    plan: Any,
    runtime_dir: Path,
    experiment_name: str,
    plan_path: Path | None = None,
) -> dict[str, Any]:
    task_dir = source_root / "data" / "tasks" / task_id
    specs_path = task_dir / "specs.json"
    api_calls_path = task_dir / "ground_truth" / "api_calls.json"
    result: dict[str, Any] = {
        "accepted": False,
        "trajectory": None,
        "task_result": {
            "task_id": task_id,
            "status": "failed",
            "attempts": 1,
            "generation_error": None,
            "execution_error": None,
            "evaluation_success": False,
            "replay_success": False,
            "step_count": 0,
            "api_call_count": 0,
            "rejection_reason": None,
        },
    }
    task_result = result["task_result"]
    try:
        if not specs_path.is_file():
            raise FileNotFoundError(f"task_specs_missing:{specs_path}")
        specs = json.loads(specs_path.read_text(encoding="utf-8"))
        steps = normalize_plan(plan, task_id)
        task_result["step_count"] = len(steps)
        secrets = load_secret_markers(specs_path, api_calls_path)
        pre_execution_leaks = scan_visible_content(
            str(specs["instruction"]), steps, secrets
        )
        if pre_execution_leaks:
            task_result["credential_leaks"] = sum(
                finding["kind"] == "concrete_secret" for finding in pre_execution_leaks
            )
            task_result["privileged_context_leaks"] = sum(
                finding["kind"] == "privileged_term" for finding in pre_execution_leaks
            )
            raise RejectedTrajectory("pre_execution_leak_scan_failed")

        static_findings, ast_api_call_count = static_validate_steps(steps)
        if static_findings:
            task_result["static_findings"] = static_findings
            raise RejectedTrajectory("static_safety_scan_failed")

        prepare_runtime(source_root, runtime_dir)
        os.environ["APPWORLD_ROOT"] = str(runtime_dir)
        from appworld import __version__ as appworld_version
        from appworld import update_root

        update_root(str(runtime_dir))
        first = execute_once(task_id, experiment_name, steps, ast_api_call_count, secrets)
        task_result["api_call_count"] = first["api_call_count"]
        task_result["evaluation_success"] = first["evaluation"]["success"]
        if not first["evaluation"]["success"]:
            raise RejectedTrajectory("official_evaluator_failed")

        first_leaks = scan_visible_content(
            str(specs["instruction"]), first["steps"], secrets
        )
        if first_leaks:
            task_result["credential_leaks"] = sum(
                finding["kind"] == "concrete_secret" for finding in first_leaks
            )
            task_result["privileged_context_leaks"] = sum(
                finding["kind"] == "privileged_term" for finding in first_leaks
            )
            raise RejectedTrajectory("executed_trajectory_leak_scan_failed")

        replay_experiment_name = f"{experiment_name}__replay"
        replay = execute_once(
            task_id, replay_experiment_name, steps, ast_api_call_count, secrets
        )
        task_result["replay_success"] = bool(replay["evaluation"]["success"])
        if not replay["evaluation"]["success"]:
            raise RejectedTrajectory("replay_evaluator_failed")
        replay_leaks = scan_visible_content(
            str(specs["instruction"]), replay["steps"], secrets
        )
        if replay_leaks:
            raise RejectedTrajectory("replay_leak_scan_failed")

        trajectory = {
            "task_id": task_id,
            "task_family": task_id.rsplit("_", 1)[0],
            "instruction": specs["instruction"],
            "supervisor": specs["supervisor"],
            "datetime": specs["datetime"],
            "appworld_version": appworld_version,
            "source": "ground_truth_api_calls_guided_codex_reconstruction",
            "steps": first["steps"],
            "final_status": "success",
            "evaluation": first["evaluation"],
            "replay_evaluation": replay["evaluation"],
            "replay_verified": True,
            "credential_leaks": 0,
            "privileged_context_leaks": 0,
            "api_call_count": first["api_call_count"],
            "api_call_count_source": first["api_call_count_source"],
            "replay_api_call_count": replay["api_call_count"],
            "step_count": len(first["steps"]),
            "provenance": {
                "specs_sha256": sha256_file(specs_path),
                "api_calls_sha256": sha256_file(api_calls_path),
                "plan_sha256": sha256_file(plan_path) if plan_path else None,
            },
        }
        task_result.update(
            {
                "status": "verified",
                "credential_leaks": 0,
                "privileged_context_leaks": 0,
                "rejection_reason": None,
            }
        )
        result["accepted"] = True
        result["trajectory"] = trajectory
    except RejectedTrajectory as exception:
        task_result["status"] = "rejected"
        task_result["rejection_reason"] = str(exception)
        if "execution" in str(exception):
            task_result["execution_error"] = str(exception)
    except Exception as exception:
        task_result["status"] = "failed"
        task_result["generation_error"] = f"{type(exception).__name__}:{exception}"
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--experiment-name", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
    except Exception as exception:
        output = {
            "accepted": False,
            "trajectory": None,
            "task_result": {
                "task_id": args.task_id,
                "status": "failed",
                "attempts": 1,
                "generation_error": f"plan_load_failed:{type(exception).__name__}:{exception}",
                "execution_error": None,
                "evaluation_success": False,
                "replay_success": False,
                "step_count": 0,
                "api_call_count": 0,
                "rejection_reason": None,
            },
        }
    else:
        output = validate_trajectory(
            source_root=args.source_root.resolve(),
            task_id=args.task_id,
            plan=plan,
            runtime_dir=args.runtime_dir.resolve(),
            experiment_name=args.experiment_name,
            plan_path=args.plan.resolve(),
        )
    atomic_dump_json(args.output.resolve(), output)
    print(
        json.dumps(
            {
                "task_id": args.task_id,
                "accepted": output["accepted"],
                "status": output["task_result"]["status"],
                "rejection_reason": output["task_result"].get("rejection_reason"),
                "output": str(args.output.resolve()),
            },
            ensure_ascii=False,
        )
    )
    return 0 if output["accepted"] else 2


if __name__ == "__main__":
    sys.exit(main())
