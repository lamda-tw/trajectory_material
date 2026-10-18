"""Fresh DEV57 with the same non-thinking sampler as the source trajectories."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
from datetime import datetime
import argparse,hashlib,json,os,signal,subprocess,sys,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,ids,file_sha
from policy_server import owned_server

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--arm',choices=['base','random','net3','pass4','zerofail3','highfail3'],required=True);ap.add_argument('--seed',type=int,default=20261015);ap.add_argument('--epoch',type=int,default=0);ap.add_argument('--execute',action='store_true');args=ap.parse_args();assert args.execute
 run='base' if args.arm=='base' else f'{args.arm}/seed_{args.seed}/epoch_{args.epoch:02d}'
 out=R/'evaluation'/run;out.mkdir(parents=True,exist_ok=True)
 c=json.loads((R/'config/evaluation.json').read_text());cfg_path=out/'config.json';atomic_json(cfg_path,c);tasks=ids(R/'config/dev.txt');assert len(tasks)==57
 checkpoint=None if args.arm=='base' else R/f'training/{args.arm}/seed_{args.seed}/epoch_{args.epoch:02d}_adapter'
 if checkpoint:
  done=json.loads((checkpoint.parent/f'epoch_{args.epoch:02d}.json').read_text());assert done['epoch']==args.epoch and done['cumulative_updates']==855*args.epoch and not done['probe']
  for n,h in done['adapter_files'].items():assert file_sha(checkpoint/n)==h
 runtime_name=run.replace('/','__');runtime=R/'runtime'/runtime_name;runtime.mkdir(parents=True,exist_ok=True)
 if not (runtime/'data').exists():(runtime/'data').symlink_to(c['paths']['appworld_data'],target_is_directory=True)
 cache=runtime/'cache';cache.mkdir(exist_ok=True)
 if not (cache/'tests').exists():(cache/'tests').symlink_to(c['paths']['appworld_test_cache'],target_is_directory=True)
 policy='base' if checkpoint is None else file_sha(checkpoint/'adapter_model.safetensors')
 config_sha=file_sha(cfg_path);jobs=[];records={};started=time.monotonic()
 for task in tasks:
  job={'mode':'dev','task_id':task,'seed':100,'sample':0,'update':0 if checkpoint is None else 855*args.epoch,'episode_id':f'{runtime_name}__dev__{task}','runtime_name':runtime_name,'model':c['server']['model_name'] if checkpoint is None else c['server']['adapter_name'],'output':str(out/'trajectories'/f'{task}.json'),'fingerprint':config_sha,'policy_id':policy,'config_path':str(cfg_path)}
  jobs.append(job)
  if Path(job['output']).exists():
   d=json.loads(Path(job['output']).read_text());assert d['job']==job;records[task]=compact(job,d)
 pending=[j for j in jobs if j['task_id'] not in records]
 def status(phase):atomic_json(out/'STATUS.json',{'phase':phase,'arm':args.arm,'completed':len(records),'total':57,'successes':sum(x['success'] for x in records.values()),'elapsed_current_invocation_seconds':time.monotonic()-started})
 def one(job):
  path=out/'jobs'/f"{job['task_id']}.json";atomic_json(path,job)
  env=dict(os.environ,APPWORLD_CACHE=str(cache),OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONUNBUFFERED='1',PYTHONDONTWRITEBYTECODE='1')
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
  rows=[records[t] for t in tasks];result={'phase':'complete','arm':args.arm,'seed':args.seed,'epoch':args.epoch,'tasks':57,'successes':sum(x['success'] for x in rows),'TGC':sum(x['success'] for x in rows)/57,'mean_test_pass_fraction':sum(x['passes']/x['tests'] for x in rows)/57,'steps':sum(x['steps'] for x in rows),'generated_tokens':sum(x['generated_tokens'] for x in rows),'elapsed_current_invocation_seconds':time.monotonic()-started,'policy_id':policy,'config_sha256':config_sha,'results':rows}
  atomic_json(out/'SUMMARY.json',result);status('complete');print(json.dumps({k:v for k,v in result.items() if k!='results'}),flush=True)
 except BaseException as e:
  status('error');atomic_json(out/'ERROR.json',{'error':repr(e)});raise

def compact(job,d):
 e=d['official_evaluation'];assert type(e['success']) is bool and e['num_tests']>0
 return {'task_id':job['task_id'],'success':e['success'],'passes':e['num_passes'],'tests':e['num_tests'],'steps':len(d['steps']),'termination':d['termination'],'generated_tokens':sum(len(s['response_ids']) for s in d['steps']),'elapsed_seconds':d['elapsed_seconds'],'source':job['output'],'sha256':file_sha(job['output'])}
if __name__=='__main__':main()
