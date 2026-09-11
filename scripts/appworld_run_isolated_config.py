#!/usr/bin/env python3
"""Run AppWorld's official CLI while storing auto-generated config in the run root."""

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
    args = parser.parse_args()

    os.makedirs(args.config_root, exist_ok=True)

    # Prepend a writable config overlay without altering the installed environment.
    import appworld_agents.configs as configs_package

    config_paths = list(configs_package.__path__)
    if args.config_root not in config_paths:
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
        dataset_name="dev",
        dry_run=False,
        task_id=None,
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
