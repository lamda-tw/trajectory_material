#!/usr/bin/env python3
"""Preserve historical vLLM argv; only pin/record the owned physical GPU1 process."""
import json
import os
from pathlib import Path
import sys

expected='GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
if os.environ.get('CUDA_VISIBLE_DEVICES') != expected:
    raise RuntimeError('Historical evaluation is restricted to physical GPU1')
root=Path(__file__).resolve().parents[1]
stage=Path(os.environ['HISTORICAL_STAGE_ROOT']).resolve()
if not stage.is_relative_to(root/'evaluation/historical_protocol_trend'):
    raise RuntimeError('Invalid owned output root')
pid=os.getpid()
if os.getpgid(pid)!=pid:
    raise RuntimeError('Expected an isolated server process group')
start=Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[19]
(stage/'server_owned.json').write_text(json.dumps(dict(pid=pid,start_ticks=start,gpu_uuid=expected,argv=sys.argv)))
env=dict(os.environ,JOINT_VLLM_GPU1_COMPAT='1')
env['PYTHONPATH']=str(root/'scripts/vllm_uuid_compat')+(os.pathsep+env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
executable='/root/autodl-tmp/envs/qwen3-vllm-py312/bin/vllm'
os.execve(executable,[executable,*sys.argv[1:]],env)
