#!/usr/bin/env python3
"""Run the frozen one-epoch branches sequentially, without touching prior results."""
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[2]
PYTHON = ROOT / ".conda-training/bin/python"
TORCHRUN = ROOT / ".conda-training/bin/torchrun"
BRANCHES = ["CFST-state", "CFST-Action", "CFST-Mixed"]

def status(state, **kwargs):
    value = {"status": state, "updated_at_utc": datetime.now(timezone.utc).isoformat(), **kwargs}
    (OUT / "status.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(value, ensure_ascii=False), flush=True)

def main():
    if any((OUT / b / "train.log").exists() for b in BRANCHES):
        raise FileExistsError("training logs already exist; refusing to overwrite a run")
    env = dict(os.environ, TOKENIZERS_PARALLELISM="false", PYTHONUNBUFFERED="1",
               TORCH_NCCL_ASYNC_ERROR_HANDLING="1", CUDA_VISIBLE_DEVICES="0,1",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    if not (OUT / "training_plan.json").exists():
        with (OUT / "prepare_output.json").open("x") as log:
            subprocess.run([str(PYTHON), str(OUT / "prepare_step06b.py")], env=env, stdout=log, check=True)
    completed = []
    for branch in BRANCHES:
        command = [str(TORCHRUN), "--standalone", "--nproc_per_node=2",
                   str(OUT / "train_cfst_branch.py"), "--config", str(OUT / branch / "training_config.json")]
        status("training", current_branch=branch, completed_branches=completed, command=command)
        with (OUT / branch / "train.log").open("x") as log:
            subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, check=True)
        completed.append(branch)
        status("branch_completed", current_branch=branch, completed_branches=completed)
    status("trained_pending_validation", completed_branches=completed, evaluation_started=False)

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        status("FAILED", error=repr(exc))
        raise
