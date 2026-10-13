"""Own only this experiment's subprocesses; resume saved, identical stages."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl,hashlib,json,os,signal,subprocess,time
R=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def write(p,v):
 tmp=p.with_suffix('.tmp.json');tmp.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def stage(kind,arm,gpu):
 complete=R/('training' if kind=='train' else 'evaluation')/arm/('COMPLETE.json' if kind=='train' else 'SUMMARY.json')
 if complete.exists():return
 cfg=json.loads((R/'config/training.json').read_text());python=cfg['training_python'] if kind=='train' else '/usr/local/bin/python'
 if kind!='train':python='/root/autodl-tmp/envs/appworld-0.2.0-py312/bin/python'
 command=[python,'-u',str(R/'scripts'/('train_local.py' if kind=='train' else 'evaluate.py')),'--arm',arm,'--execute']
 env=dict(os.environ,CUDA_VISIBLE_DEVICES=str(gpu),HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',OMP_NUM_THREADS='4',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
 if kind=='evaluate':env.update(OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
 record={'kind':kind,'arm':arm,'gpu':gpu,'command':command,'started_at':now(),'status':'running'};meta=R/'logs'/f'{kind}_{arm}.json'
 with (R/'logs'/f'{kind}_{arm}.log').open('a') as log:
  p=subprocess.Popen(command,cwd=R,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);record['pid']=p.pid;write(meta,record)
  print(json.dumps({'event':'stage_started',**record}),flush=True)
  try:code=p.wait()
  except BaseException:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=30)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
   raise
 record.update(status='complete' if code==0 and complete.exists() else 'error',exit_code=code,finished_at=now());write(meta,record)
 print(json.dumps({'event':'stage_finished',**record}),flush=True)
 if record['status']!='complete':raise RuntimeError(f'{kind}/{arm} failed; inspect its preserved log')

def lane0():
 stage('evaluate','base',0);stage('train','rubric',0);stage('evaluate','rubric',0)
def lane1():
 stage('train','uniform',1);stage('evaluate','uniform',1)
def main():
 lock=(R/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 assert json.loads((R/'data/VALIDATION.json').read_text())['phase']=='passed'
 frozen_path=R/'EXECUTION_MANIFEST.json'
 files=[R/'PLAN.md',*sorted((R/'config').glob('*')), *sorted((R/'scripts').glob('*.py')),*sorted((R/'runtime_code').glob('*.py')),R/'data/DATA_MANIFEST.json']
 hashes={str(p.relative_to(R)):sha(p) for p in files if p.is_file()}
 if frozen_path.exists():
  old=json.loads(frozen_path.read_text())
  for p,h in old['files'].items():assert sha(R/p)==h,p
 else:write(frozen_path,{'frozen_at':now(),'files':hashes,'user_constraints':['existing_actions_only','no_external_judge','LoRA','DEV57'],'training_seed':20261013})
 status={'phase':'running','started_at':now(),'pid':os.getpid(),'lanes':{'0':'base DEV57 -> rubric train -> rubric DEV57','1':'uniform train -> uniform DEV57'}};write(R/'STATUS.json',status)
 try:
  with ThreadPoolExecutor(max_workers=2) as pool:
   fs=[pool.submit(lane0),pool.submit(lane1)]
   for f in as_completed(fs):f.result()
  status.update(phase='runs_complete_awaiting_analysis',finished_at=now());write(R/'STATUS.json',status)
 except BaseException as e:
  status.update(phase='error',error=repr(e),updated_at=now());write(R/'STATUS.json',status);raise
if __name__=='__main__':main()
