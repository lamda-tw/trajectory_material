#!/usr/bin/env python3
"""Run AppWorld test_normal with the frozen bare Qwen3-8B baseline protocol."""

from __future__ import annotations

import argparse
import json
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--vllm-bin", required=True)
    parser.add_argument("--task-id")
    args = parser.parse_args()

    os.makedirs(args.config_root, exist_ok=True)

    import appworld_agents.configs as configs_package

    if args.config_root not in list(configs_package.__path__):
        configs_package.__path__.insert(0, args.config_root)

    from appworld.cli import run

    server_command = (
        f"{args.vllm_bin} serve {args.model_path} "
        "--served-model-name Qwen/Qwen3-8B "
        "--reasoning-parser deepseek_r1 "
        "--max-num-seqs 3 "
        "--max-model-len 32000 "
        "--enable-auto-tool-choice "
        "--tool-call-parser hermes "
        "--port {port}"
    )
    override = json.dumps(
        {
            "config": {
                "model_server": {
                    "command": server_command,
                    "timeout": 1200,
                    "show_logs": True,
                }
            }
        }
    )

    run(
        experiment_name="auto",
        model_name="qwen3-8b-with-reasoning",
        agent_name="simplified_react_code_agent",
        dataset_name="test_normal",
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
