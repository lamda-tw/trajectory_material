from pathlib import Path
import json,os,subprocess,datetime,hashlib
import run as original
OUT=Path(__file__).resolve().parent
now=original.now;dump=original.dump

def run_branch(name,replay=False):
 d=OUT/name;m=json.loads((d/'manifest.json').read_text())
 assert m['status']==('run_error' if replay else 'prepared')
 with (Path(m['adapter'])/'adapter_model.safetensors').open('rb') as f:assert hashlib.file_digest(f,'sha256').hexdigest()==m['adapter_sha256']
 env=os.environ.copy();env.update(APPWORLD_ROOT=str(d),APPWORLD_CACHE=str(d/'cache'),CUDA_VISIBLE_DEVICES=str(m['gpu']),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1',NO_API_KEY='none',OPENAI_API_KEY='none')
 for k,sub in [('HF_HOME','huggingface'),('VLLM_CACHE_ROOT','vllm'),('TORCHINDUCTOR_CACHE_DIR','torchinductor'),('XDG_CACHE_HOME','xdg')]:
  p=d/'cache'/sub;p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
 if replay:
  env.update(CFST_REPLAY_TASK='afc0fce_3',CFST_REPLAY_LOG=str(d/'runtime_abort01/afc0fce_3/logs/lm_calls.jsonl'))
 cmd=[original.PY,str(OUT/'resilient_entry.py'),str(d/'scripts_snapshot/appworld_run_isolated_lora_config.py'),'--root',str(d),'--config-root',str(d/'config/agent_configs'),'--model-path',m['model'],'--adapter-path',m['adapter'],'--vllm-bin','/root/autodl-tmp/envs/qwen3-vllm-py312/bin/vllm','--served-adapter-name',m['served_adapter_name'],'--model-config-name',m['model_config'],'--reasoning-parser','none','--dataset-name','train','--per-task-status-path',str(d/'task_status.jsonl')]
 if replay:m['resume_started_at']=now()
 else:m['run_started_at']=now()
 m.update(status='running',recovery_command_argv=cmd,logging_only_ellipsis_fix=True);dump(d/'manifest.json',m)
 print(json.dumps({'event':'start','branch':name,'at':now(),'prefix_replay':replay}),flush=True)
 with (d/'logs/run.log').open('a',buffering=1) as f:r=subprocess.run(cmd,cwd=d,env=env,stdout=f,stderr=subprocess.STDOUT)
 m.update(status='awaiting_validation' if r.returncode==0 else 'run_error',exit_code=r.returncode,run_finished_at=now());dump(d/'manifest.json',m)
 print(json.dumps({'event':'end','branch':name,'exit_code':r.returncode,'at':now()}),flush=True)
 if r.returncode:raise RuntimeError(name+' failed')
run_branch('CFST-state',True)
run_branch('CFST-Mixed')
