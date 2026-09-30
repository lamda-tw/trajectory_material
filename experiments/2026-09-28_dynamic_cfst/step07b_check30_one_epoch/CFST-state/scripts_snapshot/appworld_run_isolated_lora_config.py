#!/usr/bin/env python3
"""Run AppWorld Dev with a local Qwen3 base and a vLLM LoRA adapter."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import time


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--adapter-path", required=True)
    parser.add_argument("--vllm-bin", required=True)
    parser.add_argument("--served-adapter-name", default="appworld-codex-rft-train90-epoch5")
    parser.add_argument(
        "--model-config-name",
        choices=("qwen3-8b-with-reasoning", "qwen3-8b-without-reasoning"),
        default="qwen3-8b-with-reasoning",
    )
    parser.add_argument(
        "--reasoning-parser",
        choices=("deepseek_r1", "none"),
        default="deepseek_r1",
    )
    parser.add_argument("--dataset-name", default="dev")
    parser.add_argument("--task-id")
    parser.add_argument("--per-task-status-path")
    args = parser.parse_args()

    os.makedirs(args.config_root, exist_ok=True)
    import appworld_agents.configs as configs_package

    if args.config_root not in list(configs_package.__path__):
        configs_package.__path__.insert(0, args.config_root)

    if args.reasoning_parser == "none":
        from appworld_agents.code.simplified.language_model import LanguageModel

        original_generate = LanguageModel.generate

        def generate_with_normalized_reasoning_content(self, *call_args, **call_kwargs):
            output = original_generate(self, *call_args, **call_kwargs)
            if output.get("reasoning_content") is None:
                output["reasoning_content"] = ""
            return output

        LanguageModel.generate = generate_with_normalized_reasoning_content

    if args.per_task_status_path:
        from appworld import evaluate_task
        from appworld.apps.lib.models.db import CachedDBHandler
        from appworld_agents.code.simplified.agent import Agent

        status_path = os.path.abspath(args.per_task_status_path)
        os.makedirs(os.path.dirname(status_path), exist_ok=True)
        expected_experiment_name = (
            f"simplified_react_code_agent/alibaba/{args.model_config_name}/{args.dataset_name}"
        )
        original_solve_task = Agent.solve_task
        per_task_counter = {"completed": 0}

        def solve_task_with_per_task_evaluation(self, task_id):
            started_at = time.monotonic()
            original_solve_task(self, task_id)
            CachedDBHandler.reset()
            try:
                tracker = evaluate_task(
                    task_id=task_id,
                    experiment_name=expected_experiment_name,
                    suppress_errors=True,
                    save_report=True,
                )
                per_task_counter["completed"] += 1
                succeeded = bool(tracker.success)
                record = {
                    "completed_index": per_task_counter["completed"],
                    "task_id": task_id,
                    "status": "success" if succeeded else "failed",
                    "task_goal_completion": 100.0 if succeeded else 0.0,
                    "test_pass_percentage": tracker.pass_percentage,
                    "passed_tests": tracker.pass_count,
                    "failed_tests": tracker.fail_count,
                    "num_tests": tracker.num_tests,
                    "difficulty": tracker.difficulty,
                    "elapsed_seconds": round(time.monotonic() - started_at, 3),
                }
            except Exception as exception:
                per_task_counter["completed"] += 1
                record = {
                    "completed_index": per_task_counter["completed"],
                    "task_id": task_id,
                    "status": "evaluation_error",
                    "task_goal_completion": None,
                    "error_type": type(exception).__name__,
                    "error": str(exception),
                    "elapsed_seconds": round(time.monotonic() - started_at, 3),
                }
            finally:
                CachedDBHandler.reset()
            with open(status_path, "a", encoding="utf-8") as status_file:
                status_file.write(json.dumps(record, ensure_ascii=False) + "\n")
                status_file.flush()
                os.fsync(status_file.fileno())
            print("PER_TASK_EVALUATION " + json.dumps(record, ensure_ascii=False), flush=True)

        Agent.solve_task = solve_task_with_per_task_evaluation

    from appworld.cli import run

    q = shlex.quote
    reasoning_parser_arg = (
        "" if args.reasoning_parser == "none"
        else f"--reasoning-parser {q(args.reasoning_parser)} "
    )
    server_command = (
        f"{q(args.vllm_bin)} serve {q(args.model_path)} "
        f"--served-model-name Qwen/Qwen3-8B "
        f"--enable-lora --lora-modules {q(args.served_adapter_name)}={q(args.adapter_path)} "
        f"--max-lora-rank 8 "
        f"{reasoning_parser_arg}"
        f"--max-num-seqs 3 "
        f"--max-model-len 32000 "
        f"--enable-auto-tool-choice "
        f"--tool-call-parser hermes "
        f"--port {{port}}"
    )
    override = json.dumps(
        {
            "config": {
                "agent": {"model_config": {"name": args.served_adapter_name}},
                "model_server": {
                    "command": server_command,
                    "timeout": 1200,
                    "show_logs": True,
                },
            }
        }
    )
    run(
        experiment_name="auto",
        model_name=args.model_config_name,
        agent_name="simplified_react_code_agent",
        dataset_name=args.dataset_name,
        dry_run=False,
        task_id=args.task_id,
        with_evaluation=True,
        override=override,
        clear_first=False,
        num_processes=1,
        process_index=None,
        with_setup=False,
        root=args.root,
    )


if __name__ == "__main__":
    main()
