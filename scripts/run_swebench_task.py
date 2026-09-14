#!/usr/bin/env python3
"""Run one frozen SWE-bench task with mini-swe-agent and archive its result."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import yaml

from minisweagent.agents.interactive import InteractiveAgent
from minisweagent.environments.local import LocalEnvironment
from minisweagent.models.litellm_textbased_model import LitellmTextbasedModel


MODEL_NAME = "openai/qwen3-8b"
REPO_CACHE = Path("/root/autodl-tmp/data/swebench-repos")
SYSTEM_TEMPLATE = (
    "You are a software engineering agent. The current directory is the task worktree and replaces /testbed. "
    "Never create or modify files outside it and do not clone, fetch, download, or access network resources. "
    "The repository source is already available on PYTHONPATH; do not install this repository from PyPI. "
    "An isolated Python environment is on PATH. Every response must have a brief THOUGHT followed by exactly "
    "one command in a ```mswea_bash_command code block."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def run_capture(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def write_worktree_patch(worktree: Path, baseline_head: str, destination: Path) -> int:
    result = run_capture(["git", "diff", "--binary", baseline_head, "--", "."], cwd=worktree)
    if result.returncode != 0:
        raise RuntimeError(f"Unable to capture worktree patch: {result.stdout}")
    destination.write_text(result.stdout, encoding="utf-8")
    return len(result.stdout.encode())


def check_patch(worktree: Path, baseline_head: str, patch: Path, experiment: Path) -> dict:
    if patch.stat().st_size == 0:
        return {"attempted": False, "applies": None, "returncode": None, "output": "empty patch"}
    with tempfile.TemporaryDirectory(prefix="apply-check-", dir=experiment / "metadata") as temporary:
        clean = Path(temporary)
        archive = subprocess.Popen(
            ["git", "archive", "--format=tar", baseline_head], cwd=worktree, stdout=subprocess.PIPE
        )
        assert archive.stdout is not None
        extract = subprocess.run(["tar", "-xf", "-", "-C", str(clean)], stdin=archive.stdout)
        archive.stdout.close()
        archive_status = archive.wait()
        if archive_status != 0 or extract.returncode != 0:
            raise RuntimeError("Unable to reconstruct the clean baseline for patch validation")
        subprocess.run(["git", "init", "-q"], cwd=clean, check=True)
        result = run_capture(["git", "apply", "--check", str(patch)], cwd=clean)
        return {
            "attempted": True,
            "applies": result.returncode == 0,
            "returncode": result.returncode,
            "output": result.stdout[-10000:],
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--task-json", required=True)
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, required=True)
    parser.add_argument("--task-env", type=Path, required=True)
    parser.add_argument("--baseline-head", required=True)
    parser.add_argument("--task-index", type=int, required=True)
    parser.add_argument("--worker-id", type=int, required=True)
    parser.add_argument("--gpu-id", type=int, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--mini-source", type=Path, required=True)
    parser.add_argument("--step-limit", type=int, default=40)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--command-timeout-seconds", type=int, default=180)
    args = parser.parse_args()

    started_at = utc_now()
    start_monotonic = time.monotonic()
    task = json.loads(args.task_json)
    instance_id = task["instance_id"]
    experiment = args.experiment.resolve()
    worktree = args.worktree.resolve(strict=True)
    task_env = args.task_env.resolve(strict=True)
    trajectory_path = experiment / "trajectories" / f"{instance_id}.traj.json"
    submitted_path = experiment / "outputs" / f"{instance_id}.submitted.patch"
    worktree_patch_path = experiment / "outputs" / f"{instance_id}.worktree.patch"
    dependency_path = experiment / "metadata" / "dependency_manifests" / f"{instance_id}.txt"
    state_path = experiment / "metadata" / "per-task" / f"{instance_id}.json"
    for path in (trajectory_path, submitted_path, worktree_patch_path, dependency_path, state_path):
        path.parent.mkdir(parents=True, exist_ok=True)

    builtin = yaml.safe_load(
        (args.mini_source / "src/minisweagent/config/benchmarks/swebench_backticks.yaml").read_text(encoding="utf-8")
    )
    model_config = builtin["model"]
    model = LitellmTextbasedModel(
        model_name=MODEL_NAME,
        model_kwargs={
            "drop_params": True,
            "api_base": f"{args.endpoint}/v1",
            "api_key": "local-not-secret",
            "temperature": 0.6,
            "top_p": 0.95,
            "seed": 20260914,
            "max_tokens": args.max_tokens,
            "extra_body": {"chat_template_kwargs": {"enable_thinking": False}},
        },
        cost_tracking="ignore_errors",
        observation_template=model_config["observation_template"],
        format_error_template=model_config["format_error_template"],
    )
    command_env = {
        "PAGER": "cat",
        "MANPAGER": "cat",
        "LESS": "-R",
        "PIP_PROGRESS_BAR": "off",
        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
        "TQDM_DISABLE": "1",
        "PATH": f"{task_env / 'bin'}:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
        "VIRTUAL_ENV": str(task_env),
        "PYTHONPATH": f"{worktree}:{worktree / 'src'}",
        "PIP_CACHE_DIR": str(experiment / "pip-cache"),
        "HTTP_PROXY": "http://127.0.0.1:9",
        "HTTPS_PROXY": "http://127.0.0.1:9",
        "ALL_PROXY": "http://127.0.0.1:9",
        "NO_PROXY": "127.0.0.1,localhost",
    }
    env = LocalEnvironment(cwd=str(worktree), env=command_env, timeout=args.command_timeout_seconds)
    agent = InteractiveAgent(
        model,
        env,
        system_template=SYSTEM_TEMPLATE,
        instance_template=builtin["agent"]["instance_template"],
        step_limit=args.step_limit,
        cost_limit=0.0,
        wall_time_limit_seconds=0,
        max_consecutive_format_errors=3,
        output_path=trajectory_path,
        mode="yolo",
        whitelist_actions=[],
        confirm_exit=False,
    )

    infrastructure_error = False
    exception_info = None
    result = {"exit_status": "Unknown", "submission": ""}
    try:
        result = agent.run(task["problem_statement"])
    except BaseException as error:
        # Reaching the model fixed context window is a terminal model/agent
        # outcome, analogous to the fixed step limit. It is not an endpoint or
        # runner failure and must not be retried with changed parameters.
        model_terminal = type(error).__name__ in {"ContextWindowExceededError"}
        infrastructure_error = not model_terminal
        exception_info = {
            "type": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }
        result = {
            "exit_status": "ContextWindowExceeded" if model_terminal else type(error).__name__,
            "submission": "",
        }
        print(traceback.format_exc(), flush=True)

    submission = result.get("submission", "") or ""
    submitted_path.write_text(submission, encoding="utf-8")
    worktree_deleted_by_agent = not worktree.exists()
    try:
        if worktree_deleted_by_agent:
            worktree_patch_path.write_text("", encoding="utf-8")
            worktree_bytes = 0
            if submission:
                mirror = REPO_CACHE / f"{task['repo'].replace('/', '__')}.git"
                with tempfile.TemporaryDirectory(prefix="deleted-worktree-check-", dir=experiment / "metadata") as temporary:
                    clean = Path(temporary)
                    archive = subprocess.Popen(
                        ["git", f"--git-dir={mirror}", "archive", "--format=tar", task["base_commit"]],
                        stdout=subprocess.PIPE,
                    )
                    assert archive.stdout is not None
                    extract = subprocess.run(["tar", "-xf", "-", "-C", str(clean)], stdin=archive.stdout)
                    archive.stdout.close()
                    archive_status = archive.wait()
                    if archive_status != 0 or extract.returncode != 0:
                        raise RuntimeError("Unable to reconstruct deleted worktree for patch validation")
                    subprocess.run(["git", "init", "-q"], cwd=clean, check=True)
                    patch_result = run_capture(["git", "apply", "--check", str(submitted_path)], cwd=clean)
                    patch_check = {
                        "attempted": True,
                        "applies": patch_result.returncode == 0,
                        "returncode": patch_result.returncode,
                        "output": patch_result.stdout[-10000:],
                    }
            else:
                patch_check = {
                    "attempted": False,
                    "applies": None,
                    "returncode": None,
                    "output": "empty patch; worktree deleted by model action",
                }
        else:
            worktree_bytes = write_worktree_patch(worktree, args.baseline_head, worktree_patch_path)
            patch_check = check_patch(worktree, args.baseline_head, submitted_path, experiment)
    except BaseException as error:
        infrastructure_error = True
        if exception_info is None:
            exception_info = {
                "type": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }
        worktree_bytes = worktree_patch_path.stat().st_size if worktree_patch_path.exists() else 0
        patch_check = {"attempted": False, "applies": None, "returncode": None, "output": str(error)}

    dependency = run_capture([str(task_env / "bin/python"), "-m", "pip", "freeze", "--all"])
    dependency_path.write_text(dependency.stdout, encoding="utf-8")
    finished_at = utc_now()
    state = {
        "schema_version": 1,
        "instance_id": instance_id,
        "repo": task["repo"],
        "base_commit": task["base_commit"],
        "task_index": args.task_index,
        "worker_id": args.worker_id,
        "gpu_id": args.gpu_id,
        "endpoint": args.endpoint,
        "step_limit": args.step_limit,
        "max_tokens": args.max_tokens,
        "command_timeout_seconds": args.command_timeout_seconds,
        "started_at_utc": started_at,
        "finished_at_utc": finished_at,
        "elapsed_seconds": round(time.monotonic() - start_monotonic, 3),
        "exit_status": result.get("exit_status", "Unknown"),
        "api_calls": agent.n_calls,
        "submitted_patch": str(submitted_path),
        "submitted_patch_bytes": len(submission.encode()),
        "worktree_patch": str(worktree_patch_path),
        "worktree_patch_bytes": worktree_bytes,
        "empty_submission": not bool(submission),
        "worktree_deleted_by_agent": worktree_deleted_by_agent,
        "patch_apply_check": patch_check,
        "infrastructure_error": infrastructure_error,
        "exception": exception_info,
        "attempt": 0,
        "retry_count": 0,
    }
    atomic_json(state_path, state)

    if trajectory_path.exists():
        try:
            trajectory = json.loads(trajectory_path.read_text(encoding="utf-8"))
            trajectory["experiment"] = {
                "instance_id": instance_id,
                "task_index": args.task_index,
                "worker_id": args.worker_id,
                "gpu_id": args.gpu_id,
                "endpoint": args.endpoint,
                "base_commit": task["base_commit"],
            }
            atomic_json(trajectory_path, trajectory)
        except BaseException:
            infrastructure_error = True

    print(
        json.dumps(
            {
                "instance_id": instance_id,
                "exit_status": state["exit_status"],
                "api_calls": state["api_calls"],
                "submitted_patch_bytes": state["submitted_patch_bytes"],
                "infrastructure_error": infrastructure_error,
            }
        ),
        flush=True,
    )
    return 2 if infrastructure_error else 0


if __name__ == "__main__":
    raise SystemExit(main())
