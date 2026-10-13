"""Evaluate user-requested saved checkpoints only after all five epochs finish."""
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import json,os,subprocess,time
R=Path(__file__).resolve().parents[1]
def now():return datetime.now().astimezone().isoformat()
def dump(p,x):
 tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def one(epoch):
 cfg=json.loads((R/f'config/eval_epoch{epoch}.json').read_text())
 for attempt in range(1,4):
  cmd=[cfg['paths']['appworld_python'],'-u',str(R/'scripts/evaluate_checkpoint.py'),'--epoch',str(epoch),'--execute'];rec={'kind':f'evaluate_epoch{epoch}','attempt':attempt,'started_at':now(),'command':cmd,'status':'running'};path=R/f'logs/checkpoint_epoch{epoch}_attempt_{attempt}.json'
  with path.with_suffix('.log').open('w') as f:
   env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUNBUFFERED='1');p=subprocess.Popen(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);rec['pid']=p.pid;dump(path,rec);code=p.wait()
  rec.update(exit_code=code,status='complete' if code==0 else 'error',finished_at=now());dump(path,rec)
  if code==0:return
  if attempt==3:raise RuntimeError(f'epoch {epoch} DEV failed after 3 attempts')
  time.sleep(10)
while True:
 state=json.loads((R/'STATUS.json').read_text())
 if state['phase']=='complete':break
 if state['phase']=='error':raise RuntimeError(state)
 if state['phase']=='runs_complete_awaiting_analysis':
  try:
   state['original_stage_finished_at']=state['finished_at'];state.update(phase='running',stage='evaluate_epoch1_and_epoch3');dump(R/'STATUS.json',state)
   cfg=json.loads((R/'config/training.json').read_text());subprocess.run([cfg['training_python'],str(R/'scripts/preserve_checkpoints.py')],cwd=R,check=True)
   with ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(one,[1,3]))
   state.update(phase='runs_complete_awaiting_analysis',stage='analysis',finished_at=now());dump(R/'STATUS.json',state)
   for name in ['analyze_results.py','write_report.py','finalize.py']:subprocess.run(['python',str(R/'scripts'/name)],cwd=R,check=True)
  except BaseException as e:
   state.update(phase='error',error=repr(e),finished_at=now());dump(R/'STATUS.json',state);raise
  break
 time.sleep(30)
