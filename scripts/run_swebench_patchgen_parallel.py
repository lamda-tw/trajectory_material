#!/usr/bin/env python3
"""Orchestrate a frozen 50-task baseline with configurable limits and workers."""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from math import ceil
from pathlib import Path

import yaml


MODEL_PATH = Path("/root/autodl-tmp/models/Qwen3-8B")
MINI_ROOT = Path("/root/autodl-tmp/envs/mini-swe-agent")
MINI_SOURCE = MINI_ROOT / "source"
AGENT_PYTHON = MINI_ROOT / "agent-venv/bin/python"
VLLM_ROOT = Path("/root/autodl-tmp/envs/qwen3-vllm-py312")
VLLM_EXECUTABLE = VLLM_ROOT / "bin/vllm"
SHARED_DATA = Path("/root/autodl-tmp/data/swebench")
REPO_CACHE = Path("/root/autodl-tmp/data/swebench-repos")
WORKSPACE = Path("/root/autodl-tmp/workspace-tw")
MODEL_NAME = "openai/qwen3-8b"
SERVED_MODEL_NAME = "qwen3-8b"
SYSTEM_TEMPLATE = (
    "You are a software engineering agent. The current directory is the task worktree and replaces /testbed. "
    "Never create or modify files outside it and do not clone, fetch, download, or access network resources. "
    "The repository source is already available on PYTHONPATH; do not install this repository from PyPI. "
    "An isolated Python environment is on PATH. Every response must have a brief THOUGHT followed by exactly "
    "one command in a ```mswea_bash_command code block."
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_json(path: Path, value: object) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_fingerprint(root: Path) -> dict:
    digest = hashlib.sha256()
    count = 0
    total_bytes = 0
    for path in sorted(item for item in root.rglob("*") if item.is_file() and not item.is_symlink()):
        relative = path.relative_to(root).as_posix()
        file_hash = sha256_file(path)
        size = path.stat().st_size
        digest.update(relative.encode() + b"\0" + str(size).encode() + b"\0" + file_hash.encode() + b"\n")
        count += 1
        total_bytes += size
    return {"root": str(root), "file_count": count, "total_bytes": total_bytes, "sha256": digest.hexdigest()}


def capture(command: list[str], *, cwd: Path | None = None, check: bool = True) -> str:
    result = subprocess.run(command, cwd=cwd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if check and result.returncode != 0:
        raise RuntimeError(f"Command failed ({result.returncode}): {' '.join(command)}\n{result.stdout}")
    return result.stdout


def port_is_free(port: int) -> bool:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def vllm_command(
    port: int,
    *,
    max_model_len: int,
    gpu_memory_utilization: float,
    max_num_seqs: int,
) -> list[str]:
    return [
        str(VLLM_EXECUTABLE),
        "serve",
        str(MODEL_PATH),
        "--tokenizer",
        str(MODEL_PATH),
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--disable-uvicorn-access-log",
        "--enable-auto-tool-choice",
        "--tool-call-parser",
        "hermes",
        "--reasoning-parser",
        "qwen3",
        "--dtype",
        "bfloat16",
        "--seed",
        "20260914",
        "--max-model-len",
        str(max_model_len),
        "--served-model-name",
        SERVED_MODEL_NAME,
        "--gpu-memory-utilization",
        str(gpu_memory_utilization),
        "--max-num-seqs",
        str(max_num_seqs),
    ]


def request_json(url: str, payload: dict | None = None, timeout: float = 30) -> dict:
    data = json.dumps(payload).encode() if payload is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read())


def wait_healthy(process: subprocess.Popen, port: int, timeout: float = 300) -> dict:
    deadline = time.monotonic() + timeout
    last_error = "not attempted"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"vLLM on port {port} exited with code {process.returncode}: {last_error}")
        try:
            response = request_json(f"http://127.0.0.1:{port}/v1/models", timeout=3)
            if response.get("data"):
                return response
        except BaseException as error:
            last_error = f"{type(error).__name__}: {error}"
        time.sleep(2)
    raise TimeoutError(f"vLLM on port {port} did not become healthy: {last_error}")


def worker_target(worker_id: int, worker_count: int) -> tuple[int, int]:
    workers_per_replica = ceil(worker_count / 2)
    gpu_id = min(worker_id // workers_per_replica, 1)
    return gpu_id, (18080, 18081)[gpu_id]


def concurrency_smoke(worker_count: int) -> dict:
    release = threading.Event()

    def one(request_id: int, port: int) -> dict:
        release.wait()
        started = time.time()
        payload = {
            "model": SERVED_MODEL_NAME,
            "messages": [{"role": "user", "content": "Return the word OK and nothing else."}],
            "temperature": 0,
            "max_tokens": 8,
            "seed": 20260914 + request_id,
            "chat_template_kwargs": {"enable_thinking": False},
        }
        try:
            response = request_json(f"http://127.0.0.1:{port}/v1/chat/completions", payload, timeout=120)
            content = response["choices"][0]["message"].get("content", "")
            error = None
        except BaseException as caught:
            content = ""
            error = f"{type(caught).__name__}: {caught}"
        finished = time.time()
        return {
            "request_id": request_id,
            "port": port,
            "started_at_unix": started,
            "finished_at_unix": finished,
            "elapsed_seconds": round(finished - started, 3),
            "content": content,
            "error": error,
        }

    requests = [(worker_id, worker_target(worker_id, worker_count)[1]) for worker_id in range(worker_count)]
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = [executor.submit(one, request_id, port) for request_id, port in requests]
        release.set()
        results = [future.result() for future in futures]
    overlap = {}
    for port in sorted({port for _, port in requests}):
        matches = [result for result in results if result["port"] == port]
        overlap[str(port)] = len(matches) == 1 or min(item["finished_at_unix"] for item in matches) > max(
            item["started_at_unix"] for item in matches
        )
    overlap["global"] = min(item["finished_at_unix"] for item in results) > max(
        item["started_at_unix"] for item in results
    )
    passed = all(result["error"] is None for result in results) and all(overlap.values())
    return {"schema_version": 1, "performed_at_utc": utc_now(), "passed": passed, "intervals_overlap": overlap, "requests": results}


def prepare_task(experiment: Path, task: dict, task_index: int) -> tuple[Path, Path, str]:
    instance_id = task["instance_id"]
    mirror = REPO_CACHE / f"{task['repo'].replace('/', '__')}.git"
    worktree = experiment / "worktrees" / instance_id
    task_env = experiment / "task-envs" / instance_id
    if worktree.exists() or task_env.exists():
        raise FileExistsError(f"Runtime directory already exists for incomplete task {instance_id}")
    worktree.mkdir(parents=True)
    archive_env = os.environ.copy()
    archive_env.update(
        {
            "GIT_NO_LAZY_FETCH": "1",
            "HTTP_PROXY": "http://127.0.0.1:9",
            "HTTPS_PROXY": "http://127.0.0.1:9",
            "ALL_PROXY": "http://127.0.0.1:9",
            "NO_PROXY": "127.0.0.1,localhost",
        }
    )
    archive = subprocess.Popen(
        ["git", f"--git-dir={mirror}", "archive", "--format=tar", task["base_commit"]],
        stdout=subprocess.PIPE,
        env=archive_env,
    )
    assert archive.stdout is not None
    extract = subprocess.run(["tar", "-xf", "-", "-C", str(worktree)], stdin=archive.stdout)
    archive.stdout.close()
    archive_status = archive.wait()
    if archive_status != 0 or extract.returncode != 0:
        raise RuntimeError(f"Unable to extract {instance_id} from the hydrated cache")
    capture(["git", "init", "-q"], cwd=worktree)
    capture(["git", "config", "user.name", "SWE-bench Baseline"], cwd=worktree)
    capture(["git", "config", "user.email", "swebench-baseline@localhost"], cwd=worktree)
    # Every archived path was tracked at the upstream base commit. Force-add so
    # repository-local ignore rules cannot silently omit tracked fixtures.
    capture(["git", "add", "-f", "."], cwd=worktree)
    capture(["git", "commit", "-q", "-m", f"Sanitized base {task['base_commit']}"], cwd=worktree)
    baseline_head = capture(["git", "rev-parse", "HEAD"], cwd=worktree).strip()
    if capture(["git", "status", "--porcelain"], cwd=worktree).strip():
        raise RuntimeError(f"Prepared source directory is not clean for {instance_id}")
    subprocess.run([sys.executable, "-m", "venv", str(task_env)], check=True)
    return worktree, task_env, baseline_head


def launch_task(
    experiment: Path,
    task: dict,
    task_index: int,
    *,
    worker_count: int,
    step_limit: int,
    max_tokens: int,
    command_timeout_seconds: int,
) -> dict:
    worker_id = task_index % worker_count
    gpu_id, port = worker_target(worker_id, worker_count)
    endpoint = f"http://127.0.0.1:{port}"
    worktree, task_env, baseline_head = prepare_task(experiment, task, task_index)
    log_path = experiment / "logs" / f"{task['instance_id']}.log"
    log_handle = log_path.open("w", encoding="utf-8")
    command = [
        str(AGENT_PYTHON),
        str(WORKSPACE / "scripts/run_swebench_task.py"),
        "--task-json",
        json.dumps(task, ensure_ascii=False),
        "--experiment",
        str(experiment),
        "--worktree",
        str(worktree),
        "--task-env",
        str(task_env),
        "--baseline-head",
        baseline_head,
        "--task-index",
        str(task_index),
        "--worker-id",
        str(worker_id),
        "--gpu-id",
        str(gpu_id),
        "--endpoint",
        endpoint,
        "--mini-source",
        str(MINI_SOURCE),
        "--step-limit",
        str(step_limit),
        "--max-tokens",
        str(max_tokens),
        "--command-timeout-seconds",
        str(command_timeout_seconds),
    ]
    process_env = os.environ.copy()
    process_env.update({"MSWEA_SILENT_STARTUP": "1", "PYTHONUNBUFFERED": "1"})
    process = subprocess.Popen(command, stdout=log_handle, stderr=subprocess.STDOUT, env=process_env)
    print(f"START index={task_index} worker={worker_id} gpu={gpu_id} instance={task['instance_id']} pid={process.pid}", flush=True)
    return {
        "task": task,
        "task_index": task_index,
        "worker_id": worker_id,
        "gpu_id": gpu_id,
        "endpoint": endpoint,
        "worktree": worktree,
        "task_env": task_env,
        "log_handle": log_handle,
        "process": process,
    }


def finish_task(experiment: Path, running: dict) -> tuple[bool, dict | None]:
    process = running["process"]
    returncode = process.wait()
    running["log_handle"].close()
    instance_id = running["task"]["instance_id"]
    state_path = experiment / "metadata/per-task" / f"{instance_id}.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else None
    infrastructure_error = returncode != 0 or state is None or bool(state.get("infrastructure_error"))
    if not infrastructure_error:
        trajectory = experiment / "trajectories" / f"{instance_id}.traj.json"
        required = [
            experiment / "outputs" / f"{instance_id}.submitted.patch",
            experiment / "outputs" / f"{instance_id}.worktree.patch",
            experiment / "metadata/dependency_manifests" / f"{instance_id}.txt",
        ]
        if not (trajectory.exists() or Path(f"{trajectory}.gz").exists()) or not all(
            path.exists() for path in required
        ):
            infrastructure_error = True
    if infrastructure_error:
        print(f"INFRASTRUCTURE_ERROR index={running['task_index']} instance={instance_id} returncode={returncode}", flush=True)
    else:
        shutil.rmtree(running["task_env"])
        shutil.rmtree(running["worktree"])
        print(
            f"DONE index={running['task_index']} worker={running['worker_id']} instance={instance_id} "
            f"status={state['exit_status']} calls={state['api_calls']} patch_bytes={state['submitted_patch_bytes']} "
            f"elapsed={state['elapsed_seconds']}",
            flush=True,
        )
    return infrastructure_error, state


def run_canary(
    experiment: Path,
    tasks: list[dict],
    *,
    worker_count: int,
    step_limit: int,
    max_tokens: int,
    command_timeout_seconds: int,
) -> bool:
    running = [
        launch_task(
            experiment,
            tasks[index],
            index,
            worker_count=worker_count,
            step_limit=step_limit,
            max_tokens=max_tokens,
            command_timeout_seconds=command_timeout_seconds,
        )
        for index in range(worker_count)
    ]
    failed = False
    for item in running:
        infrastructure_error, _ = finish_task(experiment, item)
        failed = failed or infrastructure_error
    return not failed


def run_remaining(
    experiment: Path,
    tasks: list[dict],
    *,
    worker_count: int,
    step_limit: int,
    max_tokens: int,
    command_timeout_seconds: int,
) -> bool:
    queues = {
        worker: [
            index
            for index in range(worker_count, len(tasks))
            if index % worker_count == worker
            and not (experiment / "metadata/per-task" / f"{tasks[index]['instance_id']}.json").exists()
        ]
        for worker in range(worker_count)
    }
    active: dict[int, dict] = {}
    stop_dispatch = False
    while any(queues.values()) or active:
        if not stop_dispatch:
            for worker in range(worker_count):
                if worker not in active and queues[worker]:
                    index = queues[worker].pop(0)
                    active[worker] = launch_task(
                        experiment,
                        tasks[index],
                        index,
                        worker_count=worker_count,
                        step_limit=step_limit,
                        max_tokens=max_tokens,
                        command_timeout_seconds=command_timeout_seconds,
                    )
        if not active:
            break
        time.sleep(1)
        for worker, item in list(active.items()):
            if item["process"].poll() is None:
                continue
            infrastructure_error, _ = finish_task(experiment, item)
            del active[worker]
            if infrastructure_error:
                stop_dispatch = True
        if stop_dispatch and not active:
            return False
    return not stop_dispatch


def aggregate(experiment: Path, tasks: list[dict]) -> dict:
    states = []
    predictions = []
    native = {}
    patch_validation = {}
    for task in tasks:
        instance_id = task["instance_id"]
        state = json.loads((experiment / "metadata/per-task" / f"{instance_id}.json").read_text(encoding="utf-8"))
        submission = (experiment / "outputs" / f"{instance_id}.submitted.patch").read_text(encoding="utf-8")
        prediction = {"instance_id": instance_id, "model_name_or_path": MODEL_NAME, "model_patch": submission}
        states.append(state)
        predictions.append(prediction)
        native[instance_id] = prediction
        patch_validation[instance_id] = state["patch_apply_check"]
    atomic_write(experiment / "predictions.jsonl", "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in predictions))
    atomic_json(experiment / "preds.json", native)
    atomic_json(experiment / "metadata/task_statuses.json", states)
    atomic_json(experiment / "metadata/patch_validation.json", patch_validation)
    return {
        "completed": len(states),
        "exit_status_counts": dict(sorted(Counter(state["exit_status"] for state in states).items())),
        "empty_submissions": sum(state["empty_submission"] for state in states),
        "nonempty_submissions": sum(not state["empty_submission"] for state in states),
        "applicable_nonempty_submissions": sum(state["patch_apply_check"]["applies"] is True for state in states),
    }


def terminate_vllm(processes: list[subprocess.Popen]) -> None:
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline and any(process.poll() is None for process in processes):
        time.sleep(0.5)
    for process in processes:
        if process.poll() is None:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--step-limit", type=int, default=40)
    parser.add_argument("--max-model-len", type=int, default=32768)
    parser.add_argument("--max-tokens", type=int, default=2048)
    parser.add_argument("--command-timeout-seconds", type=int, default=180)
    parser.add_argument("--gpu-memory-utilization", type=float, default=0.45)
    parser.add_argument("--max-num-seqs", type=int, default=2)
    args = parser.parse_args()
    if not 1 <= args.workers <= 4:
        raise ValueError("--workers must be between 1 and 4")
    if min(args.step_limit, args.max_model_len, args.max_tokens, args.command_timeout_seconds, args.max_num_seqs) <= 0:
        raise ValueError("limits and sequence counts must be positive")
    if not 0 < args.gpu_memory_utilization <= 1:
        raise ValueError("--gpu-memory-utilization must be in (0, 1]")
    experiment = args.experiment.resolve(strict=True)
    selected_path = experiment / "data/selected_tasks.jsonl"
    tasks = [json.loads(line) for line in selected_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(tasks) != 50 or len({task["instance_id"] for task in tasks}) != 50:
        raise ValueError("Frozen selection must contain exactly 50 unique tasks")
    existing_states = {
        task["instance_id"]: experiment / "metadata/per-task" / f"{task['instance_id']}.json"
        for task in tasks
        if (experiment / "metadata/per-task" / f"{task['instance_id']}.json").exists()
    }
    if existing_states and not args.resume:
        raise RuntimeError("Per-task results already exist; use --resume to continue without overwriting them")
    if args.resume:
        for instance_id, state_path in existing_states.items():
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if state.get("infrastructure_error"):
                raise RuntimeError(f"Cannot resume past unresolved infrastructure error for {instance_id}")
            trajectory = experiment / "trajectories" / f"{instance_id}.traj.json"
            required = [
                experiment / "outputs" / f"{instance_id}.submitted.patch",
                experiment / "outputs" / f"{instance_id}.worktree.patch",
                experiment / "metadata/dependency_manifests" / f"{instance_id}.txt",
            ]
            if not (trajectory.exists() or Path(f"{trajectory}.gz").exists()) or not all(
                path.exists() for path in required
            ):
                raise RuntimeError(f"Existing task result is incomplete for {instance_id}")
            shutil.rmtree(experiment / "task-envs" / instance_id, ignore_errors=True)
            shutil.rmtree(experiment / "worktrees" / instance_id, ignore_errors=True)
    if any(not port_is_free(port) for port in (18080, 18081)):
        raise RuntimeError("Required vLLM port 18080 or 18081 is already in use")

    started_at = utc_now()
    start_monotonic = time.monotonic()
    dataset_before = tree_fingerprint(SHARED_DATA)
    env_entries_before = sorted(path.name for path in Path("/root/autodl-tmp/envs").iterdir())
    gpu_before = capture(
        [
            "nvidia-smi",
            "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
            "--format=csv,noheader,nounits",
        ]
    ).splitlines()
    model_manifest = []
    for path in sorted(item for item in MODEL_PATH.iterdir() if item.is_file()):
        model_manifest.append({"name": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    environment = {
        "schema_version": 1,
        "captured_at_utc": utc_now(),
        "workspace_git_head": capture(["git", "rev-parse", "HEAD"], cwd=WORKSPACE).strip(),
        "workspace_git_status_before": capture(["git", "status", "--porcelain"], cwd=WORKSPACE),
        "dataset_tree_before": dataset_before,
        "env_entries_before": env_entries_before,
        "gpu_before": gpu_before,
        "disk_before": capture(["df", "-B1", str(experiment)]).splitlines(),
        "mini_swe_agent_version": capture([str(AGENT_PYTHON), "-c", "import importlib.metadata; print(importlib.metadata.version('mini-swe-agent'))"]).strip().splitlines()[-1],
        "mini_swe_agent_source_commit": capture(["git", "rev-parse", "HEAD"], cwd=MINI_SOURCE).strip(),
        "vllm_version": capture([str(VLLM_ROOT / "bin/python"), "-c", "import vllm; print(vllm.__version__)"]).strip(),
        "model_path": str(MODEL_PATH),
        "model_files": model_manifest,
    }
    atomic_json(experiment / "metadata/environment.json", environment)

    builtin = yaml.safe_load((MINI_SOURCE / "src/minisweagent/config/benchmarks/swebench_backticks.yaml").read_text())
    assignments = [
        {
            "task_index": index,
            "instance_id": task["instance_id"],
            "worker_id": index % args.workers,
            "gpu_id": worker_target(index % args.workers, args.workers)[0],
            "endpoint": f"http://127.0.0.1:{worker_target(index % args.workers, args.workers)[1]}",
        }
        for index, task in enumerate(tasks)
    ]
    atomic_json(experiment / "metadata/task_assignments.json", assignments)
    atomic_write(experiment / "metadata/retry_log.jsonl", "")
    config = {
        "schema_version": 1,
        "created_at_utc": utc_now(),
        "dataset": str(selected_path),
        "model": {
            "checkpoint": str(MODEL_PATH),
            "model_name_or_path": MODEL_NAME,
            "served_model_name": SERVED_MODEL_NAME,
            "max_model_len": args.max_model_len,
            "temperature": 0.6,
            "top_p": 0.95,
            "request_seed": 20260914,
            "max_tokens": args.max_tokens,
            "enable_thinking": False,
        },
        "agent": {
            "system_template": SYSTEM_TEMPLATE,
            "instance_template": builtin["agent"]["instance_template"],
            "step_limit": args.step_limit,
            "command_timeout_seconds": args.command_timeout_seconds,
            "mode": "yolo",
            "max_consecutive_format_errors": 3,
        },
        "parallelism": {
            "workers": args.workers,
            "assignment": f"worker_id = task_index % {args.workers}",
            "replicas": [
                {
                    "gpu_id": gpu_id,
                    "port": port,
                    "max_num_seqs": args.max_num_seqs,
                    "gpu_memory_utilization": args.gpu_memory_utilization,
                    "command": vllm_command(
                        port,
                        max_model_len=args.max_model_len,
                        gpu_memory_utilization=args.gpu_memory_utilization,
                        max_num_seqs=args.max_num_seqs,
                    ),
                }
                for gpu_id, port in ((0, 18080), (1, 18081))
            ],
        },
    }
    atomic_json(experiment / "config.json", config)

    vllm_processes = []
    vllm_logs = []
    run_complete = False
    stop_reason = None
    try:
        for gpu_id, port in ((0, 18080), (1, 18081)):
            log_handle = (experiment / "logs" / f"vllm-gpu{gpu_id}.log").open("a", encoding="utf-8")
            log_handle.write(f"\n===== vLLM segment started {utc_now()} =====\n")
            log_handle.flush()
            process_env = os.environ.copy()
            process_env.update({"CUDA_VISIBLE_DEVICES": str(gpu_id), "HF_HUB_OFFLINE": "1", "PYTHONUNBUFFERED": "1"})
            process = subprocess.Popen(
                vllm_command(
                    port,
                    max_model_len=args.max_model_len,
                    gpu_memory_utilization=args.gpu_memory_utilization,
                    max_num_seqs=args.max_num_seqs,
                ),
                stdout=log_handle,
                stderr=subprocess.STDOUT,
                env=process_env,
                start_new_session=True,
            )
            vllm_processes.append(process)
            vllm_logs.append(log_handle)
            print(f"VLLM_START gpu={gpu_id} port={port} pid={process.pid}", flush=True)
        health = [wait_healthy(process, port) for process, port in zip(vllm_processes, (18080, 18081), strict=True)]
        print("Both vLLM replicas are healthy", flush=True)
        smoke = concurrency_smoke(args.workers)
        smoke["model_health"] = health
        smoke["vllm_processes_alive_after"] = [process.poll() is None for process in vllm_processes]
        smoke["passed"] = smoke["passed"] and all(smoke["vllm_processes_alive_after"])
        atomic_json(experiment / "metadata/concurrency_smoke.json", smoke)
        with (experiment / "metadata/concurrency_smoke_history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(smoke, ensure_ascii=False) + "\n")
        if not smoke["passed"]:
            raise RuntimeError(f"{args.workers}-request concurrency smoke test failed")
        print(f"{args.workers}-request concurrency smoke test passed", flush=True)
        canary_complete = all(
            (experiment / "metadata/per-task" / f"{tasks[index]['instance_id']}.json").exists()
            for index in range(args.workers)
        )
        runner_kwargs = {
            "worker_count": args.workers,
            "step_limit": args.step_limit,
            "max_tokens": args.max_tokens,
            "command_timeout_seconds": args.command_timeout_seconds,
        }
        if not canary_complete and not run_canary(experiment, tasks, **runner_kwargs):
            stop_reason = f"Infrastructure failure in the {args.workers}-task formal canary"
        elif not run_remaining(experiment, tasks, **runner_kwargs):
            stop_reason = "Infrastructure failure during the remaining formal tasks"
        else:
            run_complete = True
    except BaseException as error:
        stop_reason = f"{type(error).__name__}: {error}"
        print(f"STOP: {stop_reason}", flush=True)
    finally:
        terminate_vllm(vllm_processes)
        for log_handle in vllm_logs:
            log_handle.close()

    completed_states = list((experiment / "metadata/per-task").glob("*.json"))
    summary = aggregate(experiment, tasks) if run_complete else {"completed": len(completed_states)}
    dataset_after = tree_fingerprint(SHARED_DATA)
    env_entries_after = sorted(path.name for path in Path("/root/autodl-tmp/envs").iterdir())
    environment.update(
        {
            "finished_at_utc": utc_now(),
            "dataset_tree_after": dataset_after,
            "dataset_tree_unchanged": dataset_after == dataset_before,
            "env_entries_after": env_entries_after,
            "env_entries_unchanged": env_entries_after == env_entries_before,
            "gpu_after": capture(
                [
                    "nvidia-smi",
                    "--query-gpu=index,name,memory.total,memory.used,memory.free,utilization.gpu",
                    "--format=csv,noheader,nounits",
                ]
            ).splitlines(),
            "disk_after": capture(["df", "-B1", str(experiment)]).splitlines(),
        }
    )
    atomic_json(experiment / "metadata/environment.json", environment)
    run_status = {
        "schema_version": 1,
        "started_at_utc": started_at,
        "finished_at_utc": utc_now(),
        "elapsed_seconds": round(time.monotonic() - start_monotonic, 3),
        "complete": run_complete,
        "stop_reason": stop_reason,
        "summary": summary,
    }
    with (experiment / "metadata/run_segments.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(run_status, ensure_ascii=False) + "\n")
    atomic_json(experiment / "metadata/run_status.json", run_status)
    print(json.dumps(run_status, ensure_ascii=False), flush=True)
    return 0 if run_complete else 2


if __name__ == "__main__":
    raise SystemExit(main())
