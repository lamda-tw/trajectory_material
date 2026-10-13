"""Fresh DEV57 with the same non-thinking sampler as the source trajectories."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
import argparse,hashlib,json,os,signal,subprocess,sys,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,ids,file_sha
from policy_server import owned_server

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--epoch',type=int,choices=[1,3],required=True);ap.add_argument('--execute',action='store_true');args=ap.parse_args();assert args.execute;args.arm=f'epoch{args.epoch}'
 out=R/'evaluation'/args.arm;out.mkdir(parents=True,exist_ok=True)
 cfg_path=R/f'config/eval_{args.arm}.json';c=json.loads(cfg_path.read_text());tasks=ids(R/'config/dev.txt');assert len(tasks)==57
 assert json.loads((R/'training/rubric/COMPLETE.json').read_text())['epochs']==5
 checkpoint=R/'training/rubric'/f'epoch_{args.epoch:02d}_adapter'
 if checkpoint:
  done=json.loads((R/'CHECKPOINTS_135.json').read_text())['checkpoints'][str(args.epoch)]
  for n,h in done['adapter_files'].items():assert file_sha(checkpoint/n)==h
 policy='base' if checkpoint is None else file_sha(checkpoint/'adapter_model.safetensors')
 config_sha=file_sha(cfg_path);jobs=[];records={};started=time.monotonic()
 for task in tasks:
  job={'mode':'dev','task_id':task,'seed':100,'sample':0,'update':args.epoch*1220,'episode_id':f'{args.arm}__dev__{task}','runtime_name':args.arm,'model':c['server']['model_name'] if checkpoint is None else c['server']['adapter_name'],'output':str(out/'trajectories'/f'{task}.json'),'fingerprint':config_sha,'policy_id':policy,'config_path':str(cfg_path)}
  jobs.append(job)
  if Path(job['output']).exists():
   d=json.loads(Path(job['output']).read_text());assert d['job']==job;records[task]=compact(job,d)
 pending=[j for j in jobs if j['task_id'] not in records]
 def status(phase):atomic_json(out/'STATUS.json',{'phase':phase,'arm':args.arm,'completed':len(records),'total':57,'successes':sum(x['success'] for x in records.values()),'elapsed_current_invocation_seconds':time.monotonic()-started})
 def one(job):
  path=out/'jobs'/f"{job['task_id']}.json";atomic_json(path,job)
  env=dict(os.environ,APPWORLD_CACHE=str(R/'runtime'/args.arm/'cache'),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
  log=path.with_suffix('.log')
  with log.open('a') as f:
   p=subprocess.Popen([c['paths']['appworld_python'],'-u',str(R/'runtime_code/rollout_worker.py'),'--job',str(path),'--execute'],cwd=R,env=env,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   try:
    code=p.wait(timeout=33000)
    if code:raise RuntimeError(f"Infrastructure error {code}; {log}")
   finally:
    if p.poll() is None:
     os.killpg(p.pid,signal.SIGTERM)
     try:p.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
  d=json.loads(Path(job['output']).read_text());assert d['job']==job
  return compact(job,d)
 status('running')
 try:
  if pending:
   with owned_server(c,out/'server',checkpoint):
    with ThreadPoolExecutor(max_workers=3) as pool:
     futures={pool.submit(one,j):j for j in pending}
     for future in as_completed(futures):
      row=future.result();records[row['task_id']]=row;status('running');atomic_json(out/'task_results.json',[records[t] for t in tasks if t in records]);print(json.dumps({'event':'task_done','arm':args.arm,'completed':len(records),**row}),flush=True)
  assert len(records)==57
  rows=[records[t] for t in tasks];result={'phase':'complete','arm':args.arm,'tasks':57,'successes':sum(x['success'] for x in rows),'TGC':sum(x['success'] for x in rows)/57,'mean_test_pass_fraction':sum(x['passes']/x['tests'] for x in rows)/57,'steps':sum(x['steps'] for x in rows),'generated_tokens':sum(x['generated_tokens'] for x in rows),'elapsed_current_invocation_seconds':time.monotonic()-started,'policy_id':policy,'config_sha256':config_sha,'results':rows}
  atomic_json(out/'SUMMARY.json',result);status('complete');print(json.dumps({k:v for k,v in result.items() if k!='results'}),flush=True)
 except BaseException as e:
  status('error');atomic_json(out/'ERROR.json',{'error':repr(e)});raise

def compact(job,d):
 e=d['official_evaluation'];assert type(e['success']) is bool and e['num_tests']>0
 return {'task_id':job['task_id'],'success':e['success'],'passes':e['num_passes'],'tests':e['num_tests'],'steps':len(d['steps']),'termination':d['termination'],'generated_tokens':sum(len(s['response_ids']) for s in d['steps']),'elapsed_seconds':d['elapsed_seconds'],'source':job['output'],'sha256':file_sha(job['output'])}
if __name__=='__main__':main()
