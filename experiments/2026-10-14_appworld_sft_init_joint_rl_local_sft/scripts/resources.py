"""Strict physical GPU1 guard; never fall back to another device."""
import os,subprocess
from common import ROOT,read,require

def require_free_gpu(gpu,minimum_free_gpu_gib):
    expected=read(ROOT/'config/resource_policy.json')['physical_gpu_uuid']
    require(gpu==expected and os.environ.get('CUDA_VISIBLE_DEVICES')==expected,'Only launcher-pinned physical GPU1 permitted')
    lines=subprocess.check_output(['nvidia-smi','--id=1','--query-gpu=uuid,memory.free','--format=csv,noheader,nounits'],text=True).strip().split(',')
    require(lines[0].strip()==expected,'GPU1 identity changed')
    require(float(lines[1])/1024>=minimum_free_gpu_gib,'Insufficient free GPU1 memory')
