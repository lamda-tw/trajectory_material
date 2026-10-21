"""Resumable phase1 only. Requires audited calibration, frozen protocol, and GPU1 lock."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,csv,fcntl,json,os,signal,subprocess,sys,time,traceback
R=Path(__file__).resolve().parents[1];W=R.parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha,parse_code
from policy_server import owned_server,sample_step
from judging import judge,public_prefix
from public_payload import sanitize
from progress import update
C=json.loads((R/'config/runtime.json').read_text())
ROWS=list(csv.DictReader((R/'plan_snapshot/states_selected.csv').open()))
GPU='GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
ENV=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0',PYTHONUNBUFFERED='1')

def key(row):return row['state_id'].replace(':','__')
def data(row):return json.loads((R/'inputs'/f'{key(row)}.json').read_text())
def model_key(m):return f"{m['group']}__seed_{m['training_seed']}"
def run_worker(command,log,timeout=5400):
 log.parent.mkdir(parents=True,exist_ok=True)
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

def replay(row,tag,candidate=None):
 folder=R/'results/executions'/tag;folder.mkdir(parents=True,exist_ok=True);out=folder/f'{key(row)}.json';jobpath=folder/f'{key(row)}.job.json'
 job={'input':str(R/'inputs'/f'{key(row)}.json'),'output':str(out),'runtime':str(R/'runtime/branches'/tag/key(row))}
 if candidate:job['candidate']=str(candidate)
 if out.exists():
  result=json.loads(out.read_text());assert result['job']==job;return result
 atomic_json(jobpath,job)
 errors=[]
 for attempt in range(1,3):
  try:
   run_worker([C['paths']['appworld_python'],str(R/'scripts/replay_worker.py'),'--job',str(jobpath)],folder/f'{key(row)}.attempt{attempt}.log')
   return json.loads(out.read_text())
  except (RuntimeError,subprocess.TimeoutExpired) as e:
   errors.append(repr(e));atomic_json(folder/f'{key(row)}.infrastructure_errors.json',errors)
 raise RuntimeError(f'Replay infrastructure failed twice: {tag}/{key(row)}')

def evaluate(row,tag,phase):
 target=R/'results/evaluators'/tag/f'{key(row)}.{phase}.json'
 if target.exists():return json.loads(target.read_text())
 target.parent.mkdir(parents=True,exist_ok=True)
 run_worker([C['paths']['appworld_python'],str(R/'scripts/evaluate_snapshot.py'),'--replay',str(R/'results/executions'/tag/f'{key(row)}.json'),'--phase',phase,'--output',str(target)],target.with_suffix('.log'),900)
 return json.loads(target.read_text())

def freeze_cards():
 def one(row):
  d=data(row);return row['state_id'],judge('card',public_prefix(d),R/'judge_runs/cards'/key(row))
 done=0
 with ThreadPoolExecutor(max_workers=8) as pool:
  for f in as_completed([pool.submit(one,r) for r in sorted(ROWS,key=lambda r:digest(['card_order',r['state_id']]))]):
   f.result();done+=1;update('299张正式前缀卡',f'{done}/299卡片通过结构和证据定位核验；候选生成尚未开始。',completed=done,total=299)
 hashes={r['state_id']:file_sha(R/'judge_runs/cards'/key(r)/'judgement.json') for r in ROWS}
 atomic_json(R/'config/cards_frozen.json',{'cards':hashes,'card_prompt_sha256':file_sha(R/'config/card_prompt.txt'),'frozen_before_any_formal_candidate':not any((R/'results/generations').glob('*/*.json'))})
 update('299张正式前缀卡','299/299卡片已冻结；机会分母不随候选变化。','complete',completed=299,total=299)

def references():
 def one(row):
  x=replay(row,'reference');valid=x['all_observations_exact'] and x['environment_supported']
  if valid:evaluate(row,'reference','before')
  return {'state_id':row['state_id'],'replay_valid':valid,'observations_exact':x['all_observations_exact'],'supported':x['environment_supported'],'before_sha256':x['before_sha256']}
 results=[]
 with ThreadPoolExecutor(max_workers=4) as pool:
  for f in as_completed([pool.submit(one,r) for r in ROWS]):
   results.append(f.result());atomic_json(R/'analysis/reference_audit.json',results);update('正式状态重放核验',f'{len(results)}/299基准前缀及隔离before-evaluator完成。',completed=len(results),total=299)
 update('正式状态重放核验',f'299/299已核验；{sum(x["replay_valid"] for x in results)}可执行，失败状态不替换。','complete')
 return {x['state_id']:x for x in results}

def gpu_available():
 rows=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
 return not any(line.split(',')[0].strip()==GPU for line in rows.splitlines())

def execute_candidate(row,m,gen,reference):
 name=model_key(m)
 if not reference['replay_valid']:
  result={'state_id':row['state_id'],'model':name,'status':'common_reference_unreliable','execution_valid':False}
 else:
  x=replay(row,name,gen);valid=x['all_observations_exact'] and x['environment_supported'] and x['before_sha256']==reference['before_sha256']
  ev=evaluate(row,name,'after') if valid else None
  result={'state_id':row['state_id'],'model':name,'status':'complete' if valid else 'branch_replay_mismatch','execution_valid':valid,'before_sha256':x['before_sha256'],'execution_error':x['candidate']['execution_error'],'no_code':x['candidate']['no_code'],'db_changed':x['before']['db_tables']!=x['after']['db_tables'],'after_evaluator':None if ev is None else {'num_tests':ev['num_tests'],'num_passes':ev['num_passes'],'success':ev['success']}}
 atomic_json(R/'results/paired_checks'/name/f'{key(row)}.json',result)
 return result

def generate_and_execute(models,ref):
 os.environ['CUDA_VISIBLE_DEVICES']=GPU
 lockpath=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock';lockpath.parent.mkdir(parents=True,exist_ok=True)
 handles=[];execution_done=0;generation_done=0
 with ThreadPoolExecutor(max_workers=4) as cpu:
  with lockpath.open('a+') as lock:
   fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
   for m in models:
    name=model_key(m);adapter=W/m['adapter'];assert file_sha(adapter)==m['adapter_sha256']
    folder=R/'results/generations'/name;folder.mkdir(parents=True,exist_ok=True)
    pending=[r for r in ROWS if not (folder/f'{key(r)}.json').exists()]
    for row in ROWS:
     g=folder/f'{key(row)}.json'
     if g.exists():
      x=json.loads(g.read_text());assert x['policy_sha256']==m['adapter_sha256'] and x['prompt_ids']==data(row)['prompt_ids'];generation_done+=1;handles.append(cpu.submit(execute_candidate,row,m,g,ref[row['state_id']]))
    if not pending:continue
    while not gpu_available():
     update('正式单步生成与执行',f'GPU1被其他进程占用，等待，不抢占；已有{generation_done}/2691动作。',status_detail='waiting_gpu1');time.sleep(30)
    update('正式单步生成与执行',f'正在GPU1加载 {name}；累计{generation_done}/2691动作。',generated=generation_done,total=2691)
    with owned_server(C,R/'logs/servers'/name,adapter.parent) as model:
     def generate(row):
      d=data(row);sample=sample_step(C,model,d['messages'],100+int(row['before_step'])-1,evaluation=True)
      assert sample is not None and sample['prompt_ids']==d['prompt_ids'],'Model input token mismatch'
      code,fixed=parse_code(sample['text']);g=folder/f'{key(row)}.json';atomic_json(g,dict(sample,code=code,history_assistant_text=fixed,state_id=row['state_id'],policy_sha256=m['adapter_sha256'],checkpoint_alias=m['alias'],physical_gpu=1))
      return row,g
     with ThreadPoolExecutor(max_workers=3) as gpu:
      for f in as_completed([gpu.submit(generate,r) for r in pending]):
       row,g=f.result();generation_done+=1;handles.append(cpu.submit(execute_candidate,row,m,g,ref[row['state_id']]));execution_done=sum(h.done() and h.exception() is None for h in handles)
       update('正式单步生成与执行',f'{name}：累计生成{generation_done}/2691，执行/evaluator完成{execution_done}。',generated=generation_done,executed=execution_done,total=2691)
    # Fail fast on infrastructure problems already discovered by the CPU lane.
    for h in handles:
     if h.done():h.result()
  for f in as_completed(handles):
   f.result();execution_done=sum(h.done() and h.exception() is None for h in handles)
   update('正式单步生成与执行',f'生成2691/2691；执行/evaluator完成{execution_done}/2691。',generated=generation_done,executed=execution_done,total=2691)
 update('正式单步生成与执行','9模型全部完成生成、配对执行核验和隔离after-evaluator。','complete',generated=2691,executed=2691,total=2691)


def score_all(models):
 common=[]
 for row in ROWS:
  if all(json.loads((R/'results/paired_checks'/model_key(m)/f'{key(row)}.json').read_text())['execution_valid'] for m in models):common.append(row['state_id'])
 atomic_json(R/'analysis/common_states.json',{'state_ids':common,'missing_state_ids':[r['state_id'] for r in ROWS if r['state_id'] not in common],'states':len(common),'total':299})
 items=[];audit=[]
 for m in models:
  for panel,n in [('primary',4)]+[(f'focused_{x}',1) for x in 'ERDS']:
   choices=[r for r in ROWS if r['panel']==panel]
   selected=sorted(choices,key=lambda r:__import__('hashlib').sha256(('20261019:judge_audit:'+m['alias']+'|'+r['state_id']).encode()).hexdigest())[:n]
   audit.extend({'model':model_key(m),'alias':m['alias'],'state_id':r['state_id'],'common_execution_valid':r['state_id'] in common} for r in selected)
  for row in ROWS:
   if row['state_id'] not in common:continue
   d=data(row);card=json.loads((R/'judge_runs/cards'/key(row)/'judgement.json').read_text());execution=json.loads((R/'results/executions'/model_key(m)/f'{key(row)}.json').read_text())
   payload=dict(public_prefix(d),diagnostic_card=card,candidate={k:execution['candidate'][k] for k in ['text','code','observation']});clean,_=sanitize(payload);evidence_hash=digest(clean)
   items.append({'model':model_key(m),'alias':m['alias'],'state_id':row['state_id'],'evidence_hash':evidence_hash,'payload':payload})
 atomic_json(R/'config/random_review_manifest.json',audit)
 # All identical evidence, including full text and feedback, can share the first valid score.
 unique={}
 for item in sorted(items,key=lambda x:digest(['blind_judge_order',x['alias'],x['state_id']])):unique.setdefault(item['evidence_hash'],item)
 def one(item,repeat=False):
  dest=R/'judge_runs'/('review_repeat' if repeat else 'actions')/item['evidence_hash']
  if repeat:dest=dest/(item['alias']+'_'+item['state_id'].replace(':','__'))
  judge('action',item['payload'],dest,repeat=repeat)
  return str(dest/'judgement.json')
 done=0
 with ThreadPoolExecutor(max_workers=8) as pool:
  for f in as_completed([pool.submit(one,v) for v in unique.values()]):
   f.result();done+=1;update('行为评分与72条复核',f'{done}/{len(unique)}条不同证据完成评分（{len(items)}模型×状态行）。',unique_scored=done,unique_total=len(unique))
 links=[{k:v for k,v in x.items() if k!='payload'}|{'judgement':str(R/'judge_runs/actions'/x['evidence_hash']/'judgement.json')} for x in items];atomic_json(R/'analysis/judgement_index.json',links)
 lookup={(x['model'],x['state_id']):x for x in items};review=[lookup[x['model'],x['state_id']] for x in audit if x['common_execution_valid']]
 done=0
 with ThreadPoolExecutor(max_workers=8) as pool:
  for f in as_completed([pool.submit(one,v,True) for v in review]):
   f.result();done+=1;update('行为评分与72条复核',f'主评分完成；同评委独立上下文重复复核{done}/{len(review)}，不称独立评委验证。',reviewed=done,review_available=len(review),review_selected=72)
 update('行为评分与72条复核',f'完成{len(items)}行评分，{len(unique)}种证据；重复复核{len(review)}/72，共同缺失不替换。','complete')

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true',required=True);ap.parse_args()
 gate=json.loads((R/'config/calibration_accepted.json').read_text());assert gate['accepted'] and gate['evaluator_verified']
 for path,sha in gate['frozen_files'].items():assert file_sha(R/path)==sha,('Frozen protocol changed',path)
 assert C['server']['gpu']==GPU and not C['scope']['new_training'] and not C['scope']['old_zerofail'] and not C['scope']['continuation']
 own=(R/'runtime/pipeline.lock').open('a+');fcntl.flock(own,fcntl.LOCK_EX|fcntl.LOCK_NB)
 models=json.loads((R/'plan_snapshot/same_state_models.json').read_text())['models']
 for m in models:m['alias']='checkpoint_'+digest(['20261019:blind_checkpoint',model_key(m)])[:12]
 atomic_json(R/'config/model_aliases_researcher_only.json',models)
 if not (R/'config/cards_frozen.json').exists():freeze_cards()
 else:
  frozen=json.loads((R/'config/cards_frozen.json').read_text());assert len(frozen['cards'])==299
  for sid,sha in frozen['cards'].items():assert file_sha(R/'judge_runs/cards'/sid.replace(':','__')/'judgement.json')==sha
 ref=references();generate_and_execute(models,ref);score_all(models)
 run_worker([sys.executable,str(R/'scripts/analyze_phase1.py')],R/'logs/analysis.log',3600)
 update('evaluator与报告','第一阶段已完成；结果见 REPORT.md。未运行旧ZeroFail3、可选续跑。','complete')
if __name__=='__main__':
 try:main()
 except BaseException as e:
  update('运行异常',repr(e)+'；已保存已有产物，禁止将基础设施错误补零。','error');traceback.print_exc();raise
