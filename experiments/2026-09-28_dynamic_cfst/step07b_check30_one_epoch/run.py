"""Evaluate three frozen 1epoch adapters; preserve old outputs and stop at check30."""
from pathlib import Path
import concurrent.futures
import datetime
import fcntl
import hashlib
import json
import os
import signal
import subprocess
import time
import psutil

OUT=Path(__file__).resolve().parent
PY='/root/autodl-tmp/envs/appworld-0.2.0-py312/bin/python'
BRANCHES=['CFST-state','CFST-Action','CFST-Mixed']
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(p,x):
    temp=p.with_suffix(p.suffix+'.tmp')
    temp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    temp.replace(p)
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def cleanup_tracked(tracked):
    live=[]
    for pid,created in tracked.items():
        try:
            p=psutil.Process(pid)
            if p.create_time()==created and p.status()!=psutil.STATUS_ZOMBIE:live.append(p)
        except psutil.NoSuchProcess:pass
    for p in live:
        try:p.terminate()
        except psutil.NoSuchProcess:pass
    gone,alive=psutil.wait_procs(live,timeout=8)
    for p in alive:
        try:p.kill()
        except psutil.NoSuchProcess:pass
    psutil.wait_procs(alive,timeout=5)
    return [p.pid for p in live]

def branch_run(name,gpu):
    d=OUT/name;m=json.loads((d/'manifest.json').read_text())
    if m['status']!='prepared':raise RuntimeError(f'{name}: not fresh; inspect before retry')
    assert sha(Path(m['adapter'])/'adapter_model.safetensors')==m['adapter_sha256']
    assert not (d/'experiments/outputs').exists()
    env=os.environ.copy()
    for key in ['CFST_REPLAY_LOG','CFST_REPLAY_TASK']:env.pop(key,None)
    env.update(APPWORLD_ROOT=str(d),APPWORLD_CACHE=str(d/'cache'),CUDA_VISIBLE_DEVICES=str(gpu),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',NO_API_KEY='none',OPENAI_API_KEY='none')
    for key,sub in [('HF_HOME','huggingface'),('VLLM_CACHE_ROOT','vllm'),('TORCHINDUCTOR_CACHE_DIR','torchinductor'),('XDG_CACHE_HOME','xdg')]:
        p=d/'cache'/sub;p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
    cmd=[PY,str(OUT/'resilient_entry.py'),str(d/'scripts_snapshot/appworld_run_isolated_lora_config.py'),'--root',str(d),'--config-root',str(d/'config/agent_configs'),'--model-path',m['model'],'--adapter-path',m['adapter'],'--vllm-bin','/root/autodl-tmp/envs/qwen3-vllm-py312/bin/vllm','--served-adapter-name',m['served_adapter_name'],'--model-config-name',m['model_config'],'--reasoning-parser','none','--dataset-name','train','--per-task-status-path',str(d/'task_status.jsonl')]
    m.update(status='running',gpu=gpu,run_started_at=now(),command_argv=cmd,prefix_replay=False);dump(d/'manifest.json',m)
    print(json.dumps({'event':'start','branch':name,'gpu':gpu,'at':now()}),flush=True)
    tracked={}
    with (d/'logs/run.log').open('x',buffering=1) as log:
        proc=subprocess.Popen(cmd,cwd=d,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        m['runner_pid']=proc.pid;dump(d/'manifest.json',m)
        while proc.poll() is None:
            try:
                for child in psutil.Process(proc.pid).children(recursive=True):
                    try:tracked[child.pid]=child.create_time()
                    except psutil.NoSuchProcess:pass
            except psutil.NoSuchProcess:pass
            time.sleep(2)
    cleaned=cleanup_tracked(tracked)
    dump(d/'runtime_processes.json',dict(tracked=tracked,cleanup_pids=cleaned,cleanup_scope='Only descendants observed under this branch runner, with creation-time match.'))
    m.update(status='awaiting_validation' if proc.returncode==0 else 'run_error',exit_code=proc.returncode,run_finished_at=now());dump(d/'manifest.json',m)
    print(json.dumps({'event':'end','branch':name,'exit_code':proc.returncode,'at':now()}),flush=True)
    if proc.returncode:raise RuntimeError(name+' failed; inspect logs without changing protocol')
    return gpu

def main():
    lock=(OUT/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    m=json.loads((OUT/'manifest.json').read_text());assert m['status']=='prepared'
    assert sha(OUT/'resilient_entry.py')==m['logging_wrapper_sha256']
    m.update(status='running',run_started_at=now(),supervisor_pid=os.getpid(),scheduling='State on GPU0 and Action on GPU1; Mixed starts once either finishes.');dump(OUT/'manifest.json',m)
    errors=[];mixed_started=False
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        running={pool.submit(branch_run,'CFST-state',0):'CFST-state',pool.submit(branch_run,'CFST-Action',1):'CFST-Action'}
        while running:
            done,_=concurrent.futures.wait(running,return_when=concurrent.futures.FIRST_COMPLETED)
            for future in done:
                name=running.pop(future)
                try:
                    gpu=future.result()
                    if not mixed_started and not errors:
                        running[pool.submit(branch_run,'CFST-Mixed',gpu)]='CFST-Mixed';mixed_started=True
                except Exception as exc:errors.append({'branch':name,'error':repr(exc)})
    m.update(status='run_error' if errors else 'awaiting_validation',run_finished_at=now(),errors=errors,branches={b:json.loads((OUT/b/'manifest.json').read_text()) for b in BRANCHES});dump(OUT/'manifest.json',m)
    if errors:raise RuntimeError(errors)
    print(json.dumps({'event':'all_check30_runs_completed','at':now()}),flush=True)
if __name__=='__main__':main()
