"""Authorized serial GPU1 experiment; stops on any failed validation/stage."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,fcntl,hashlib,json,os,subprocess,sys,time,threading,traceback
R=Path(__file__).resolve().parents[1];W=R.parents[1]
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
def read(p):return json.loads(Path(p).read_text())
def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.tmp.{os.getpid()}.{threading.get_ident()}');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');a=ap.parse_args();assert a.execute
 cfg=read(R/'config/training.json');scope=read(R/'runtime/execution_scope.json');active_seeds=scope['active_seeds'];assert active_seeds==[20261015,20261016,20261017];ec=read(R/'config/evaluation.json');prior=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft';done=read(prior/'ROUND_01_COMPLETE.json');assert done['passed'] and done['optimizer_updates']==15;assert sha(Path(done['final_adapter'])/'adapter_model.safetensors')==done['adapter_sha256']
 gpu=subprocess.check_output(['nvidia-smi','--id=1','--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],text=True).strip().split(',');assert gpu[0].strip()==cfg['gpu_uuid'];assert int(gpu[1])<500,'GPU1 busy; do not preempt'
 lock=(prior/'runtime/gpu1.lock').open('a+');fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 own=(R/'runtime/pipeline.lock').open('a+');fcntl.flock(own.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 for check in ['loss_math.json','data_validation.json','global_sampling.json']:assert read(R/'checks'/check)['passed']
 for rel,h in read(R/'data/DATA_MANIFEST.json')['artifacts'].items():assert sha(R/rel)==h,rel
 frozen=R/'EXECUTION_MANIFEST.json'
 if frozen.exists():
  for rel,h in read(frozen)['files'].items():assert sha(R/rel)==h,rel
 else:
  paths=[p for d in ['scripts','runtime_code','config','checks'] for p in (R/d).rglob('*') if p.is_file() and '__pycache__' not in str(p)]+[R/'data/DATA_MANIFEST.json',R/'PLAN.md']
  dump(frozen,{'at':now(),'user_authorized':True,'files':{str(p.relative_to(R)):sha(p) for p in paths},'arms':cfg['arms'],'steps_per_arm':1710,'no_quality_filters':True,'single_gpu':cfg['gpu_uuid']})
 env=dict(os.environ,CUDA_VISIBLE_DEVICES=cfg['gpu_uuid'],CUDA_DEVICE_ORDER='PCI_BUS_ID',WORLD_SIZE='1',LOCAL_WORLD_SIZE='1',LOCAL_RANK='0',RANK='0',OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',PYTHONUNBUFFERED='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTHONDONTWRITEBYTECODE='1',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
 state={'phase':'running','pid':os.getpid(),'started_at':now(),'physical_gpu':1,'arms':cfg['arms'],'runs':len(active_seeds)*len(cfg['arms']),'stage':'starting'};halt=threading.Event()
 def heartbeat():
  while not halt.is_set():
   snapshot=dict(state);snapshot['heartbeat_at']=now();dump(R/'STATUS.json',snapshot);halt.wait(15)
 thread=threading.Thread(target=heartbeat,daemon=True);thread.start()
 def stage(name,cmd):
  state.update(stage=name,stage_started_at=now());dump(R/'STATUS.json',dict(state));log=R/'logs'/f'{name}.log';log.parent.mkdir(parents=True,exist_ok=True)
  with log.open('a') as f:
   p=subprocess.Popen(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT);state['child_pid']=p.pid;state['active_log']=str(log);code=p.wait()
  state.pop('child_pid',None)
  if code:raise RuntimeError(f'{name} exited {code}; inspect {log}. No automatic data/recipe change.')
 def evaluate(arm,seed=20261015,epoch=0):
  run='base' if arm=='base' else f'{arm}/seed_{seed}/epoch_{epoch:02d}'
  if not (R/'evaluation'/run/'SUMMARY.json').exists():stage(f'eval_{arm}_{seed}_e{epoch}',[ec['paths']['appworld_python'],'-u',str(R/'scripts/evaluate.py'),'--arm',arm,'--seed',str(seed),'--epoch',str(epoch),'--execute'])
  stage('summarize',['python',str(R/'scripts/summarize.py')])
 try:
  probe=R/'probe/random/seed_20261015/COMPLETE.json'
  if not probe.exists():stage('probe',[cfg['training_python'],'-u',str(R/'scripts/train.py'),'--arm','random','--seed','20261015','--probe'])
  assert read(probe)['probe'] and read(probe)['samples']==2
  evaluate('base')
  for epoch in cfg['eval_epochs']:
   for seed in active_seeds:
    for arm in cfg['arms']:
     state.update(arm=arm,seed=seed,target_epoch=epoch)
     if not (R/f'training/{arm}/seed_{seed}/epoch_{epoch:02d}.json').exists():stage(f'train_{arm}_{seed}_to_e{epoch}',[cfg['training_python'],'-u',str(R/'scripts/train.py'),'--arm',arm,'--seed',str(seed),'--until-epoch',str(epoch)])
     init=read(R/f'training/{arm}/seed_{seed}/INITIALIZATION.json')
     for other in cfg['arms']:
      p=R/f'training/{other}/seed_{seed}/INITIALIZATION.json'
      if p.exists():assert read(p)['initial_adapter_tensor_sha256']==init['initial_adapter_tensor_sha256']
     evaluate(arm,seed,epoch)
  state.update(phase='complete',stage='complete',finished_at=now());dump(R/'COMPLETE.json',state)
 except BaseException as e:
  state.update(phase='error',error=repr(e),traceback=traceback.format_exc(),finished_at=now());raise
 finally:
  halt.set();thread.join(timeout=20);dump(R/'STATUS.json',state)
if __name__=='__main__':main()
