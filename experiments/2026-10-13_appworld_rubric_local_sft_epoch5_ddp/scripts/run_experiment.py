from pathlib import Path
from datetime import datetime
import hashlib,json,os,subprocess,sys,time,signal
R=Path(__file__).resolve().parents[1]
def now():return datetime.now().astimezone().isoformat()
def dump(p,x):
 tmp=p.with_name(p.name+'.tmp');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
assert (R/'probe/COMPLETE.json').exists()
assert json.loads((R/'probe/COMPLETE.json').read_text())['phase']=='complete'
assert 'PASS:' in (R/'logs/test_ddp_loss.log').read_text()
files=[R/'PLAN.md',R/'data/DATA_MANIFEST.json',R/'data/FIVE_EPOCH_VALIDATION.json',R/'probe/COMPLETE.json']
for d in ['config','scripts','runtime_code']:files += [p for p in (R/d).iterdir() if p.is_file()]
manifest={'frozen_at':now(),'files':{str(p.relative_to(R)):sha(p) for p in files},'initialization':'fresh_base_and_LoRA','constraints':['rubric_only','5_epochs','no_old_adapter','no_teacher_actions','DEV57_only_after_epoch5']}
assert not (R/'EXECUTION_MANIFEST.json').exists();dump(R/'EXECUTION_MANIFEST.json',manifest)
cfg=json.loads((R/'config/training.json').read_text());ec=json.loads((R/'config/eval_rubric.json').read_text())
state={'phase':'running','started_at':now(),'pid':os.getpid(),'stage':'train','epochs':5};dump(R/'STATUS.json',state)
monitor_log=(R/'logs/gpu_usage.csv').open('w');mon=subprocess.Popen(['nvidia-smi','--query-gpu=timestamp,index,utilization.gpu,memory.used,memory.total,power.draw','--format=csv','-l','10'],stdout=monitor_log,stderr=subprocess.STDOUT)
try:
 for name,cmd in [('train',[cfg['training_python'],'-m','torch.distributed.run','--standalone','--nproc_per_node=2',str(R/'scripts/train_ddp.py'),'--execute']),('evaluate',[ec['paths']['appworld_python'],'-u',str(R/'scripts/evaluate.py'),'--arm','rubric','--execute'])]:
  state['stage']=name;dump(R/'STATUS.json',state)
  for attempt in range(1,4):
   env=dict(os.environ,CUDA_VISIBLE_DEVICES='0,1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUNBUFFERED='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',TOKENIZERS_PARALLELISM='false',PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True')
   rec={'kind':name,'attempt':attempt,'started_at':now(),'command':cmd,'status':'running'}
   with (R/f'logs/{name}_attempt_{attempt}.log').open('w') as f:
    p=subprocess.Popen(cmd,cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True);rec['pid']=p.pid;dump(R/f'logs/{name}_attempt_{attempt}.json',rec)
    code=p.wait()
   rec.update(exit_code=code,status='complete' if code==0 else 'error',finished_at=now());dump(R/f'logs/{name}_attempt_{attempt}.json',rec)
   if code==0:break
   if attempt==3:raise RuntimeError(f'{name} failed after 3 attempts; see logs')
   time.sleep(10)
 state.update(phase='runs_complete_awaiting_analysis',finished_at=now(),stage='analysis');dump(R/'STATUS.json',state)
except BaseException as e:
 state.update(phase='error',error=repr(e),finished_at=now());dump(R/'STATUS.json',state);raise
finally:
 mon.terminate();mon.wait(timeout=15);monitor_log.close()
