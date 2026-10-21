"""Frozen single-step experiment; calibration acceptance is a required gate."""
from experiment import *
from policy_server import owned_server,sample_step
from common import parse_code
from sampling import bounded_sample
from judging import judge,public_prefix
from public_payload import sanitize

ROWS=rows()
def verify_gate():
 gate=read(R/'config/calibration_accepted.json');assert gate['accepted'] and gate['evaluator_verified'] and gate['continuation_verified']
 for path,sha in gate['frozen_files'].items():assert file_sha(R/path)==sha,('Frozen protocol changed',path)
 return gate

def cards():
 frozen=R/'config/cards_frozen.json'
 if frozen.exists():
  d=read(frozen);assert len(d['cards'])==129 and d['frozen_before_any_formal_candidate']
  for sid,h in d['cards'].items():assert file_sha(R/'judge_runs/cards'/key(sid)/'judgement.json')==h
  return
 assert not any(p for p in (R/'results/generations').glob('*/*.json') if not p.parent.name.startswith('calibration_')),'Formal outputs exist before card freeze'
 def one(row):return judge('card',public_prefix(data(row)),R/'judge_runs/cards'/key(row))
 parallel(sorted(ROWS,key=lambda r:digest(['20261020:card_order',r['state_id']])),one,'129张正式前缀卡',detail='正式盲前缀卡',max_workers=8)
 atomic_json(frozen,{'cards':{r['state_id']:file_sha(R/'judge_runs/cards'/key(r)/'judgement.json') for r in ROWS},'card_prompt_sha256':file_sha(R/'config/card_prompt.txt'),'frozen_before_any_formal_candidate':True})
 update('129张正式前缀卡','129张前缀卡已在任何正式候选生成前冻结，机会标签固定。','complete')

def references():
 def one(row):
  x=replay(row,'reference');valid=x['all_observations_exact'] and x['environment_supported']
  if valid:evaluate(row,'reference','before')
  return {'state_id':row['state_id'],'replay_valid':valid,'observations_exact':x['all_observations_exact'],'supported':x['environment_supported'],'before_sha256':x['before_sha256']}
 result=parallel(ROWS,one,'正式前缀重放',detail='参考前缀和before-evaluator');atomic_json(R/'analysis/reference_audit.json',result)
 update('正式前缀重放',f"129状态已核验，其中{sum(x['replay_valid'] for x in result)}可比；不可靠状态不替换、不补零。",'complete')
 return {x['state_id']:x for x in result}

def execute(row,m,gen,reference):
 name=model_key(m);target=R/'results/paired_checks'/name/f'{key(row)}.json'
 if target.exists():
  result=read(target);assert result['generation_sha256']==file_sha(gen);return result
 if not reference['replay_valid']:result={'state_id':row['state_id'],'model':name,'status':'common_reference_unreliable','execution_valid':False,'after_state_supported':False}
 else:
  x=replay(row,name,gen);valid=x['all_observations_exact'] and x['environment_supported'] and x['before_sha256']==reference['before_sha256'];ev=evaluate(row,name,'after') if valid else None
  result={'state_id':row['state_id'],'model':name,'status':'complete' if valid else 'branch_replay_mismatch','execution_valid':valid,'after_state_supported':not bool(x['after']['unsupported_variables']),'before_sha256':x['before_sha256'],'execution_error':x['candidate']['execution_error'],'no_code':x['candidate']['no_code'],'db_changed':x['before']['db_tables']!=x['after']['db_tables'],'after_evaluator':None if ev is None else {'passes':ev['num_passes'],'tests':ev['num_tests'],'success':ev['success']}}
 result['generation_sha256']=file_sha(gen);atomic_json(target,result);return result

def generate_execute(ref):
 node='1161个首步生成与执行';done=0;handles=[]
 with ThreadPoolExecutor(max_workers=4) as cpu:
  for m in models():
   verify_gate();name=model_key(m);folder=R/'results/generations'/name;folder.mkdir(parents=True,exist_ok=True);pending=[]
   for row in ROWS:
    g=folder/f'{key(row)}.json'
    if g.exists():
     x=read(g);assert x['policy_sha256']==m['adapter_sha256'] and x['prompt_ids']==data(row)['prompt_ids'];done+=1;handles.append(cpu.submit(execute,row,m,g,ref[row['state_id']]))
    else:pending.append(row)
   if pending:
    with gpu_lock(node):
     adapter=W/m['adapter'];assert file_sha(adapter)==m['adapter_sha256']
     with owned_server(C,R/'logs/servers'/name,adapter.parent) as served:
      def generate(row):
       d=data(row);g=folder/f'{key(row)}.json';sample=bounded_sample(C,served,d['messages'],100+int(row['before_step'])-1,g,{'state_id':row['state_id'],'policy_sha256':m['adapter_sha256'],'checkpoint_alias':m['alias']},expected_prompt_ids=d['prompt_ids']);assert sample is not None,'Formal state unexpectedly at context limit';return row,g
      with ThreadPoolExecutor(max_workers=3) as gpu:
       for f in as_completed([gpu.submit(generate,r) for r in pending]):
        row,g=f.result();done+=1;handles.append(cpu.submit(execute,row,m,g,ref[row['state_id']]));finished=sum(h.done() and h.exception() is None for h in handles)
        update(node,f'{name}；首步生成{done}/1161，配对执行/evaluator完成{finished}。',generated=done,executed=finished,total=1161)
   for h in handles:
    if h.done():h.result()
   update(node,f'权重{name}的129个首步已生成；累计{done}/1161。',generated=done,total=1161)
  for f in as_completed(handles):
   f.result();finished=sum(h.done() and h.exception() is None for h in handles);update(node,f'全部首步已生成；配对执行/evaluator{finished}/1161。',generated=done,executed=finished,total=1161)
 update(node,'9权重全部1161个首步生成及配对执行/evaluator完成。','complete',generated=done,executed=len(handles),total=1161)

def score():
 common=[r['state_id'] for r in ROWS if all(read(R/'results/paired_checks'/model_key(m)/f'{key(r)}.json')['execution_valid'] for m in models())]
 atomic_json(R/'analysis/common_states.json',{'state_ids':common,'missing_state_ids':[r['state_id'] for r in ROWS if r['state_id'] not in common],'states':len(common),'total':129})
 items=[]
 for m in models():
  for row in ROWS:
   if row['state_id'] not in common:continue
   card=read(R/'judge_runs/cards'/key(row)/'judgement.json');x=read(R/'results/executions'/model_key(m)/f'{key(row)}.json');payload=dict(public_prefix(data(row)),diagnostic_card=card,candidate={k:x['candidate'][k] for k in ['text','code','observation']});clean,_=sanitize(payload)
   items.append({'model':model_key(m),'alias':m['alias'],'state_id':row['state_id'],'payload':payload,'evidence_hash':digest(clean)})
 unique={}
 for x in sorted(items,key=lambda x:digest(['20261020:blind_action',x['alias'],x['state_id']])):unique.setdefault(x['evidence_hash'],x)
 def one(item,repeat=False):
  dest=R/'judge_runs'/('review_repeat' if repeat else 'actions')/item['evidence_hash']
  if repeat:dest=dest/(item['alias']+'_'+key(item['state_id']))
  judge('action',item['payload'],dest,repeat=repeat);return str(dest/'judgement.json')
 parallel(list(unique.values()),one,'行为评分与54条复核',detail='不同公开证据主评分',max_workers=8)
 links=[{k:v for k,v in x.items() if k!='payload'}|{'judgement':str(R/'judge_runs/actions'/x['evidence_hash']/'judgement.json')} for x in items];atomic_json(R/'analysis/judgement_index.json',links)
 lookup={(x['model'],x['state_id']):x for x in items};manifest=read(R/'plan_snapshot/review_manifest.json')['rows'];reviews=[];audit=[]
 for r in manifest:
  name=f"{r['group']}__seed_{r['training_seed']}";valid=r['state_id'] in common;audit.append(dict(r,model=name,common_execution_valid=valid))
  if valid:reviews.append(lookup[name,r['state_id']])
 atomic_json(R/'config/random_review_manifest.json',audit)
 parallel(reviews,lambda x:one(x,True),'行为评分与54条复核',detail='同评委独立上下文复核',max_workers=8)
 update('行为评分与54条复核',f'{len(items)}模型状态行、{len(unique)}种不同证据完成评分；复核{len(reviews)}/54，不替换共同缺失。','complete')

def main():
 verify_gate();assert read(R/'config/external_scoring_authorization.json')['authorized'];cards();ref=references();generate_execute(ref);score();atomic_json(R/'config/phase1_completed.json',{'complete':True,'formal_states':129,'model_actions':1161})
if __name__=='__main__':
 try:main()
 except BaseException as e:update('1161个首步生成与执行',repr(e),'error');raise
