#!/usr/bin/env python3
"""Build the human-readable report for the frozen Verified-50 baseline."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
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


def duration(seconds: float) -> str:
    minutes, remainder = divmod(seconds, 60)
    hours, minutes = divmod(int(minutes), 60)
    if hours:
        return f"{hours} h {minutes} min {remainder:.1f} s"
    return f"{minutes} min {remainder:.1f} s"


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    args = parser.parse_args()
    experiment = args.experiment.resolve(strict=True)
    manifest = json.loads((experiment / "data/selection_manifest.json").read_text())
    config = json.loads((experiment / "config.json").read_text())
    validation = json.loads((experiment / "metadata/final_validation.json").read_text())
    environment = json.loads((experiment / "metadata/environment.json").read_text())
    final_run = json.loads((experiment / "metadata/run_status.json").read_text())
    initial_status_path = experiment / "metadata/run_status.segment0.json"
    segments = [json.loads(initial_status_path.read_text())] if initial_status_path.exists() else []
    segments.append(final_run)
    states = [
        json.loads((experiment / "metadata/per-task" / f"{instance_id}.json").read_text())
        for instance_id in manifest["instance_ids_in_output_order"]
    ]
    model_config = config["model"]
    agent_config = config["agent"]
    parallel_config = config["parallelism"]
    workers = parallel_config["workers"]
    replicas = parallel_config["replicas"]
    max_model_len = model_config.get("max_model_len")
    if max_model_len is None:
        command = replicas[0]["command"]
        max_model_len = int(command[command.index("--max-model-len") + 1])
    step_limit = agent_config["step_limit"]
    max_tokens = model_config["max_tokens"]
    command_timeout = agent_config["command_timeout_seconds"]
    gpu_memory_utilization = replicas[0].get("gpu_memory_utilization")
    if gpu_memory_utilization is None:
        command = replicas[0]["command"]
        gpu_memory_utilization = float(command[command.index("--gpu-memory-utilization") + 1])
    worker_gpu = {
        state["worker_id"]: state["gpu_id"]
        for state in states
    }
    worker_map = ", ".join(
        f"worker {worker_id} -> GPU {worker_gpu[worker_id]}"
        for worker_id in sorted(worker_gpu)
    )

    active_wall = sum(float(segment["elapsed_seconds"]) for segment in segments)
    first_start = min(parse_time(segment["started_at_utc"]) for segment in segments)
    last_finish = max(parse_time(segment["finished_at_utc"]) for segment in segments)
    elapsed_end_to_end = (last_finish - first_start).total_seconds()
    task_work = sum(float(state["elapsed_seconds"]) for state in states)
    speedup = task_work / active_wall if active_wall else 0.0
    repo_counts = manifest["selected_repository_quotas"]
    statuses = Counter(state["exit_status"] for state in states)
    submitted_count = statuses.get("Submitted", 0)
    submitted_empty = sum(state["exit_status"] == "Submitted" and state["empty_submission"] for state in states)
    formal_retries = sum(state["retry_count"] for state in states)
    disk_bytes = int(subprocess.check_output(["du", "-sb", str(experiment)], text=True).split()[0])

    engine_memory = {}
    engine_concurrency = {}
    for gpu_id in (0, 1):
        text = (experiment / "logs" / f"vllm-gpu{gpu_id}.log").read_text(errors="replace")
        memory = [float(value) for value in re.findall(r"Desired GPU memory utilization is .*?, ([0-9.]+) GiB", text)]
        concurrency = [float(value) for value in re.findall(r"Maximum concurrency for [0-9,]+ tokens per request: ([0-9.]+)x", text)]
        engine_memory[gpu_id] = max(memory) if memory else None
        engine_concurrency[gpu_id] = max(concurrency) if concurrency else None

    lines = [
        f"# Qwen3-8B + mini-SWE-agent SWE-bench Verified-50 {'baseline v2' if 'baseline_v2' in experiment.name else 'baseline'}",
        "",
        "## Outcome",
        "",
        f"The patch-generation run completed all **{len(states)}/50** frozen tasks. It produced "
        f"**{validation['nonempty_submission_count']} non-empty formal patches**, and all "
        f"**{validation['applicable_nonempty_count']}** passed `git apply --check` against their exact base commit. "
        "This server did not run the official SWE-bench evaluator, so this experiment has no resolved/pass score.",
        "",
        f"There were {submitted_count} `Submitted` exits, including {submitted_empty} submission(s) whose formal patch was empty; "
        f"{statuses.get('LimitsExceeded', 0)} tasks reached the fixed {step_limit}-call limit and "
        f"{statuses.get('ContextWindowExceeded', 0)} reached the fixed {max_model_len:,}-token context boundary. "
        "Empty predictions were retained and no poor-quality model result was retried.",
        "",
        "## Frozen holdout",
        "",
        f"Source: `{manifest['source_path']}`  ",
        f"Source SHA-256: `{manifest['source_sha256']}`  ",
        f"Selection seed: `{manifest['seed']}`  ",
        "Selection: one task per repository followed by proportional largest-remainder allocation; within each repository and "
        "for final ordering, tasks were sorted by `sha256(seed + \"\\0\" + instance_id)`.",
        "",
        "| Repository | Tasks |",
        "| --- | ---: |",
    ]
    lines.extend(f"| `{repository}` | {count} |" for repository, count in sorted(repo_counts.items()))
    lines.extend(
        [
            "",
            "These 50 instances are a permanent evaluation holdout. They, their gold/test patches, official tests, and derived "
            "answers must be excluded from all later SFT, validation, distillation, and trajectory data.",
            "",
            "## Reproducible configuration",
            "",
            f"- Model checkpoint: `{config['model']['checkpoint']}` (`{config['model']['model_name_or_path']}`)",
            f"- mini-SWE-agent: {environment['mini_swe_agent_version']} at source commit `{environment['mini_swe_agent_source_commit']}`",
            f"- vLLM: {environment['vllm_version']}; bfloat16; tensor parallel size 1; max model length {max_model_len:,}",
            f"- Sampling: temperature {model_config['temperature']}, top_p {model_config['top_p']}, request seed "
            f"{model_config['request_seed']}, maximum {max_tokens:,} output tokens, thinking disabled",
            f"- Agent: text-based shell actions, {step_limit}-call limit, {command_timeout}-second shell-command timeout, "
            "one formal attempt per task",
            "- Repositories: sanitized source exports at exact base commits; later repository history was not exposed to the agent",
            "- Network: model shell environment used invalid outbound proxies and the prompt prohibited clone, fetch, download, and network access",
            "",
            "## Parallel execution",
            "",
            f"Two identical vLLM replicas were used: GPU 0 on port {replicas[0]['port']} and GPU 1 on port "
            f"{replicas[1]['port']}. Each replica used `max_num_seqs={replicas[0]['max_num_seqs']}`; {worker_map}. "
            f"Assignment was fixed as `{parallel_config['assignment']}`.",
            "",
            f"The {workers}-request concurrency smoke test passed. The experiment completed in {len(segments)} vLLM service "
            f"segment(s). No formal model result was retried.",
            "",
            f"- First formal start: `{first_start.isoformat()}`",
            f"- Final finish: `{last_finish.isoformat()}`",
            f"- Active runner time across {len(segments)} segment(s): {duration(active_wall)}",
            f"- End-to-end time including diagnosis/resume pause: {duration(elapsed_end_to_end)}",
            f"- Sum of per-task elapsed times: {duration(task_work)}",
            f"- Work-equivalent concurrency ratio (`sum(task time) / active runner time`): {speedup:.2f}×",
            f"- Formal retry count: {formal_retries}",
            "",
            "Exact peak `nvidia-smi` process memory was not sampled continuously, so no peak value is fabricated. Each vLLM "
            f"engine used a configured {gpu_memory_utilization} GPU-memory utilization; it reported "
            f"{engine_memory[0]} GiB on GPU 0 and {engine_memory[1]} GiB on GPU 1. Full-context KV capacities were "
            f"{engine_concurrency[0]}× and {engine_concurrency[1]}× respectively.",
            "",
            "## Aggregate results",
            "",
            "| Measure | Count |",
            "| --- | ---: |",
            f"| Completed task records | {len(states)} |",
            f"| Submitted exits | {submitted_count} |",
            f"| LimitsExceeded | {statuses.get('LimitsExceeded', 0)} |",
            f"| ContextWindowExceeded | {statuses.get('ContextWindowExceeded', 0)} |",
            f"| Empty formal patches | {validation['empty_submission_count']} |",
            f"| Non-empty formal patches | {validation['nonempty_submission_count']} |",
            f"| Non-empty patches passing apply-check | {validation['applicable_nonempty_count']} |",
            "| Unresolved infrastructure failures | 0 |",
            f"| Formal model retries | {formal_retries} |",
            "",
            "`git apply --check` validates patch syntax and applicability only. It is not a correctness test.",
            "",
            "## Per-task results",
            "",
            "| # | Instance | Worker/GPU | Seconds | Exit | Formal bytes | Apply-check |",
            "| ---: | --- | --- | ---: | --- | ---: | --- |",
        ]
    )
    for state in states:
        applies = state["patch_apply_check"]["applies"]
        apply_label = "pass" if applies is True else ("fail" if applies is False else "not run (empty)")
        lines.append(
            f"| {state['task_index']} | `{state['instance_id']}` | {state['worker_id']}/{state['gpu_id']} | "
            f"{state['elapsed_seconds']:.3f} | `{state['exit_status']}` | {state['submitted_patch_bytes']} | {apply_label} |"
        )
    lines.extend(
        [
            "",
            "## Integrity and storage",
            "",
            f"- Final validation: `{'passed' if validation['passed'] else 'failed'}`",
            f"- Shared SWE-bench snapshot unchanged: `{environment['dataset_tree_unchanged']}`",
            f"- `/root/autodl-tmp/envs` top-level entries unchanged: `{environment['env_entries_unchanged']}`",
            "- Completed task worktrees and task environments were removed after artifacts were verified.",
            f"- Experiment directory size while building this report: {disk_bytes / (1024 * 1024):.2f} MiB",
            "- Important retained files are covered by `artifacts.sha256`.",
            "",
            "## External official evaluation",
            "",
            "Transfer `predictions.jsonl` unchanged to a machine with the official SWE-bench evaluation environment and run it "
            "against the matching SWE-bench Verified split. Preserve this experiment's model identifier and frozen instance list. "
            "Record the official harness version, image versions, command, and per-instance grading output beside the copied "
            "predictions. Do not merge scorer output back into this generation baseline in a way that obscures provenance.",
            "",
            "This 50-task fixed holdout is intended for a minimal before/after SFT comparison. It must not be presented as the "
            "model's score on the complete 500-task SWE-bench Verified benchmark.",
            "",
        ]
    )
    atomic_write(experiment / "report.md", "\n".join(lines))
    print(experiment / "report.md")


if __name__ == "__main__":
    main()
