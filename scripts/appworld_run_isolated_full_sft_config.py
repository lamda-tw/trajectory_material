#!/usr/bin/env python3
"""Run AppWorld Dev with a full-SFT Qwen3 model served by vLLM."""

from __future__ import annotations

import argparse
import json
import os
import shlex


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--config-root", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--vllm-bin", required=True)
    parser.add_argument("--served-model-name", default="appworld-qwen3-8b-full-sft-67")
    args = parser.parse_args()

    os.makedirs(args.config_root, exist_ok=True)
    import appworld_agents.configs as configs_package

    if args.config_root not in list(configs_package.__path__):
        configs_package.__path__.insert(0, args.config_root)

    from appworld.cli import run

    q = shlex.quote
    server_command = (
        f"{q(args.vllm_bin)} serve {q(args.model_path)} "
        f"--served-model-name {q(args.served_model_name)} "
        f"--reasoning-parser deepseek_r1 "
        f"--max-num-seqs 3 "
        f"--max-model-len 32000 "
        f"--enable-auto-tool-choice "
        f"--tool-call-parser hermes "
        f"--port {{port}}"
    )
    override = json.dumps(
        {
            "config": {
                "agent": {"model_config": {"name": args.served_model_name}},
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
