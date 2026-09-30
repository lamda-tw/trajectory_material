from pathlib import Path
import datetime,fcntl,json,os,subprocess,concurrent.futures,hashlib
OUT=Path(__file__).resolve().parent
PY='/root/autodl-tmp/envs/appworld-0.2.0-py312/bin/python'
def now():return datetime.datetime.now(datetime.timezone.utc).isoformat()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def branch_run(name):
    d=OUT/name;m=json.loads((d/'manifest.json').read_text())
    if m['status']!='prepared':raise RuntimeError(f'{name}: not fresh; inspect before any retry')
    with (Path(m['adapter'])/'adapter_model.safetensors').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==m['adapter_sha256']
    assert not (d/'experiments/outputs').exists()
    env=os.environ.copy();env.update(APPWORLD_ROOT=str(d),APPWORLD_CACHE=str(d/'cache'),CUDA_VISIBLE_DEVICES=str(m['gpu']),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',NO_API_KEY='none',OPENAI_API_KEY='none')
    for k,sub in [('HF_HOME','huggingface'),('VLLM_CACHE_ROOT','vllm'),('TORCHINDUCTOR_CACHE_DIR','torchinductor'),('XDG_CACHE_HOME','xdg')]:
        p=d/'cache'/sub;p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
    cmd=[PY,str(d/'scripts_snapshot/appworld_run_isolated_lora_config.py'),'--root',str(d),'--config-root',str(d/'config/agent_configs'),'--model-path',m['model'],'--adapter-path',m['adapter'],'--vllm-bin','/root/autodl-tmp/envs/qwen3-vllm-py312/bin/vllm','--served-adapter-name',m['served_adapter_name'],'--model-config-name',m['model_config'],'--reasoning-parser','none','--dataset-name','train','--per-task-status-path',str(d/'task_status.jsonl')]
    m.update(status='running',run_started_at=now(),command_argv=cmd);dump(d/'manifest.json',m)
    print(json.dumps({'event':'start','branch':name,'gpu':m['gpu'],'at':now()}),flush=True)
    with (d/'logs/run.log').open('w',buffering=1) as f:
        result=subprocess.run(cmd,cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT)
    m.update(status='awaiting_validation' if result.returncode==0 else 'run_error',exit_code=result.returncode,run_finished_at=now());dump(d/'manifest.json',m)
    print(json.dumps({'event':'end','branch':name,'exit_code':result.returncode,'at':now()}),flush=True)
    if result.returncode:raise RuntimeError(f'{name} failed; see logs')
def gpu0():
    branch_run('CFST-state');branch_run('CFST-Mixed')
def main():
    lock=(OUT/'run.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    m=json.loads((OUT/'manifest.json').read_text());assert m['status']=='prepared'
    m.update(status='running',run_started_at=now(),supervisor_pid=os.getpid());dump(OUT/'manifest.json',m)
    errors=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures=[pool.submit(gpu0),pool.submit(branch_run,'CFST-Action')]
        for future in concurrent.futures.as_completed(futures):
            try:future.result()
            except Exception as e:errors.append(repr(e))
    m.update(status='run_error' if errors else 'awaiting_validation',run_finished_at=now(),errors=errors);dump(OUT/'manifest.json',m)
    if errors:raise RuntimeError(errors)
if __name__=='__main__':main()
