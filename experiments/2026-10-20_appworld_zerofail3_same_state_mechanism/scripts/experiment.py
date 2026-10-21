"""Shared execution utilities; imports do not launch workloads."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from contextlib import contextmanager
import csv,fcntl,json,os,signal,subprocess,sys,time
R=Path(__file__).resolve().parents[1];W=R.parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha
from progress import update
C=json.loads((R/'config/runtime.json').read_text());GPU=C['server']['gpu']
ENV=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0',PYTHONUNBUFFERED='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')

def rows(name='states_selected.csv'):
 with (R/'plan_snapshot'/name).open() as f:return list(csv.DictReader(f))
def read(p):return json.loads(Path(p).read_text())
def key(row):return (row if isinstance(row,str) else row['state_id']).replace(':','__')
def data(row):return read(R/'inputs'/f'{key(row)}.json')
def model_key(m):return f"{m['group']}__seed_{m['training_seed']}"
def models():return read(R/'config/model_aliases_researcher_only.json')
def run_worker(command,log,timeout=5400):
 log=Path(log);log.parent.mkdir(parents=True,exist_ok=True)
 with log.open('a') as f:
  p=subprocess.Popen(command,env=ENV,cwd=R,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   code=p.wait(timeout=timeout)
   if code:raise RuntimeError(f'Worker exit {code}; see {log}')
  finally:
   if p.poll() is None:
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=10)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()

def replay(row,tag,candidate=None,transport_probe=None):
 folder=R/'results/executions'/tag;folder.mkdir(parents=True,exist_ok=True);out=folder/f'{key(row)}.json'
 job={'input':str(R/'inputs'/f'{key(row)}.json'),'input_sha256':file_sha(R/'inputs'/f'{key(row)}.json'),'output':str(out),'runtime':str(R/'runtime/branches'/tag/key(row))}
 if candidate:job.update(candidate=str(candidate),candidate_sha256=file_sha(candidate))
 if transport_probe:job['transport_probe']=transport_probe
 if out.exists():
  result=read(out);assert result['job']==job,'Replay cached job changed';return result
 jobpath=folder/f'{key(row)}.job.json';atomic_json(jobpath,job)
 errorpath=folder/f'{key(row)}.infrastructure_errors.json';errors=read(errorpath) if errorpath.exists() else []
 for attempt in range(len(errors)+1,4):
  try:
   run_worker([C['paths']['appworld_python'],str(R/'scripts/replay_worker.py'),'--job',str(jobpath)],folder/f'{key(row)}.attempt{attempt}.log')
   return read(out)
  except (RuntimeError,subprocess.TimeoutExpired) as e:
   errors.append({'attempt':attempt,'error':repr(e)});atomic_json(errorpath,errors)
 raise RuntimeError(f'Replay infrastructure exhausted 3 attempts: {tag}/{key(row)}')

def evaluate(row,tag,phase,replay_path=None):
 target=R/'results/evaluators'/tag/f'{key(row)}.{phase}.json';replay_path=Path(replay_path) if replay_path else R/'results/executions'/tag/f'{key(row)}.json'
 if target.exists():
  result=read(target);assert result['source_replay']==str(replay_path) and result['state_id']==row['state_id'];return result
 target.parent.mkdir(parents=True,exist_ok=True)
 run_worker([C['paths']['appworld_python'],str(R/'scripts/evaluate_snapshot.py'),'--replay',str(replay_path),'--phase',phase,'--output',str(target)],target.with_suffix('.log'),900)
 return read(target)

def parallel(items,fn,node,total=None,detail=None,max_workers=4):
 results=[];total=len(items) if total is None else total
 with ThreadPoolExecutor(max_workers=max_workers) as pool:
  for f in as_completed([pool.submit(fn,x) for x in items]):
   results.append(f.result());update(node,(detail or '已完成')+f' {len(results)}/{total}',completed=len(results),total=total)
 return results

def gpu_status():
 out=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True)
 selected=[line for line in out.splitlines() if GPU in line];assert len(selected)==1,'GPU1 UUID not found'
 values=[x.strip() for x in selected[0].split(',')];assert values[0]=='1','Physical GPU index changed'
 procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
 pids=[int(line.split(',')[1]) for line in procs.splitlines() if line.split(',')[0].strip()==GPU]
 return {'physical_gpu':1,'uuid':GPU,'free_mib':int(values[2]),'used_mib':int(values[3]),'utilization_percent':int(values[4]),'pids':pids}

@contextmanager
def gpu_lock(node):
 lockpath=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock';lockpath.parent.mkdir(parents=True,exist_ok=True)
 with lockpath.open('a+') as f:
  last=0
  while True:
   st=gpu_status();available=not st['pids'] and st['free_mib']>=C['server']['minimum_free_gpu_gib']*1024
   if available:
    try:fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:available=False
    else:
     st=gpu_status()
     if not st['pids'] and st['free_mib']>=C['server']['minimum_free_gpu_gib']*1024:break
     fcntl.flock(f,fcntl.LOCK_UN)
   if time.time()-last>=300:
    update(node,f"等待GPU1空闲/共享锁，当前显存{st['used_mib']} MiB、进程{st['pids']}。不抢占、不使用GPU0。",'waiting_gpu1');last=time.time()
   time.sleep(30)
  os.environ['CUDA_VISIBLE_DEVICES']=GPU
  update(node,'GPU1已空闲并取得共享锁，开始本实验当前模型批次。')
  try:yield
  finally:fcntl.flock(f,fcntl.LOCK_UN)
