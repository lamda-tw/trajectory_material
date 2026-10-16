"""Wait for the CPU comparison report, audit evidence, and publish completion metadata."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import time
from common import ROOT, dump, now, read, require, sha

D=ROOT/'evaluation/historical_protocol_trend'

def alive(pid):
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except FileNotFoundError:return False

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--watch',action='store_true');args=parser.parse_args()
    while not (D/'REPORT_COMPLETE.json').exists():
        require(args.watch,'Report is not complete')
        time.sleep(10)
    subprocess.run([sys.executable,str(ROOT/'scripts/audit_historical_trend.py')],check=True,
                   env={**os.environ,'CUDA_VISIBLE_DEVICES':''})
    servers=[]
    for step in [0,1,5,10,15]:
        info=read(D/f'step_{step:05d}/server_owned.json')
        servers.append(dict(step=step,pid=info['pid'],alive=alive(info['pid'])))
    require(not any(s['alive'] for s in servers),'Owned inference server still running')
    gpu=subprocess.check_output(['nvidia-smi','--id=1','--query-gpu=index,uuid,memory.used,utilization.gpu',
                                 '--format=csv,noheader'],text=True).strip()
    result=dict(at=now(),complete=True,physical_gpu_indices=[1],report=str(D/'COMPARISON.md'),
        comparison=read(D/'COMPARISON.json'),audit_sha256=sha(D/'FINAL_AUDIT.json'),
        owned_servers=servers,gpu1_observation=gpu)
    dump(ROOT/'HISTORICAL_DEV57_COMPLETE.json',result)
    state=read(ROOT/'STATUS.json')
    state['historical_dev57_trend']=dict(phase='complete',at=result['at'],report=result['report'],tasks=285)
    dump(ROOT/'STATUS.json',state)
    print('Historical-protocol evaluation and independent final audit complete.',flush=True)

if __name__=='__main__':main()
