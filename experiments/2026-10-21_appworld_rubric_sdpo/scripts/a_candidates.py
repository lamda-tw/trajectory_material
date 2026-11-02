"""Frozen next-action generation and isolated execution, followed by offline judging."""
from a_common import *
from a_replay import replay
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,copy,time
from a_policy_server import owned_server,sample_step
def jobs(stage):
 refs={x['state_id']:x for x in read(R/'phase_a/config'/f'{stage}_replay_eligibility.json')['states']}
 out=[]
 for item in packages(stage):
  x,p=item
  if not refs[x['state_id']]['eligible']:continue
  for arm in p['prompts']:
   for i,seed in enumerate(p['sampling_seeds'][arm]):
    ident='candidate_'+digest(['phase_a_blind_v1',x['state_id'],arm,i])[:24]
    out.append({'item':item,'arm':arm,'repeat':i,'seed':seed,'id':ident,'reference':refs[x['state_id']]})
 return sorted(out,key=lambda j:digest(['phase_a_order',j['id']]))
def path_for(stage,j):return R/'phase_a/generations'/stage/(j['id']+'.json')
def generate_one(stage,j,served):
 p=j['item'][1];prompt=p['prompts'][j['arm']];dest=path_for(stage,j)
 c=copy.deepcopy(config());c['agent']['max_new_tokens']=p['max_new_tokens']
 identity={'state_id':j['item'][0]['state_id'],'arm':j['arm'],'repeat':j['repeat'],'seed':j['seed'],'prompt_sha256':digest(prompt['prompt_ids']),'max_new_tokens':p['max_new_tokens'],'temperature':1.0,'model_manifest_sha256':file_sha(R/'phase_a/config/model_manifest.json')}
 if dest.exists():
  g=read(dest);assert g['identity']==identity and g['prompt_ids']==prompt['prompt_ids'];return g
 attempts=dest.parent/'attempts'/dest.name
 audit=read(attempts) if attempts.exists() else {'identity':identity,'attempts':[]}
 assert audit['identity']==identity
 for n in range(len(audit['attempts'])+1,4):
  a={'attempt':n,'started_at':now(),'status':'started'};audit['attempts'].append(a);write_json(attempts,audit)
  try:
   g=sample_step(c,served,prompt['messages'],j['seed'],evaluation=False)
   assert g is not None and g['prompt_ids']==prompt['prompt_ids'],'Actual model input differs from frozen tokens'
   code,fixed=parse_code(g['text']);g.update(identity=identity,candidate_id=j['id'],code=code,history_assistant_text=fixed,physical_gpu=1)
   frozen_json(dest,g);a.update(status='valid',completed_at=now());write_json(attempts,audit);return g
  except (OSError,TimeoutError) as e:
   a.update(status='transport_error',error=str(e));write_json(attempts,audit)
   if n<3:time.sleep(5*n)
  except BaseException as e:
   a.update(status='integrity_error',error=str(e));write_json(attempts,audit);raise
 raise RuntimeError('Three transport attempts exhausted: '+j['id'])
def generate(stage):
 authorize()
 if stage=='formal':assert read(R/'phase_a/config/calibration_execution_gate.json')['allow_formal_generation']
 todo=jobs(stage);manifest=[{k:v for k,v in j.items() if k not in ['item','reference']}|{'state_id':j['item'][0]['state_id']} for j in todo]
 frozen_json(R/'phase_a/config'/f'{stage}_candidate_manifest.json',{'stage':stage,'jobs':manifest,'count':len(todo)})
 pending=[j for j in todo if not path_for(stage,j).exists()]
 if pending:
  with gpu_lock():
   status(stage+'_model_startup',candidates=len(todo),cached=len(todo)-len(pending))
   with owned_server(config(),R/'logs/phase_a_servers'/stage,None) as served:
    with ThreadPoolExecutor(max_workers=3) as pool:
     done=len(todo)-len(pending)
     for f in as_completed([pool.submit(generate_one,stage,j,served) for j in pending]):
      f.result();done+=1;status(stage+'_generation',completed=done,total=len(todo))
 for j in todo:
  assert read(path_for(stage,j))['identity']['prompt_sha256']==digest(j['item'][1]['prompts'][j['arm']]['prompt_ids'])
 status(stage+'_generation_complete',completed=len(todo),total=len(todo),model_server_released=True)
def execute(stage):
 authorize();todo=jobs(stage);result=[]
 def one(j):
  gpath=path_for(stage,j);assert gpath.exists();x=replay(j['item'],stage+'_'+j['id'],gpath);ref=j['reference']
  ok=not x.get('infrastructure_failure') and x['all_observations_exact'] and x['environment_supported'] and x['before_sha256']==ref['before_sha256'] and x['prefix_api_sha256']==ref['prefix_api_sha256']
  return {'id':j['id'],'state_id':j['item'][0]['state_id'],'arm':j['arm'],'repeat':j['repeat'],'generation':str(gpath.relative_to(R)),'generation_sha256':file_sha(gpath),'execution':str((R/'phase_a/execution'/(stage+'_'+j['id'])/j['item'][0]['state_id']/'result.json').relative_to(R)),'execution_valid':ok,'infrastructure_failure':x.get('infrastructure_failure',False)}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for f in as_completed([pool.submit(one,j) for j in todo]):
   result.append(f.result());write_json(R/'phase_a/analysis'/f'{stage}_execution_index.partial.json',result);status(stage+'_candidate_execution',completed=len(result),total=len(todo),valid=sum(x['execution_valid'] for x in result))
 frozen_json(R/'phase_a/analysis'/f'{stage}_execution_index.json',sorted(result,key=lambda x:x['id']))
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['calibration','formal'],required=True);ap.add_argument('--action',choices=['generate','execute'],required=True);a=ap.parse_args();(generate if a.action=='generate' else execute)(a.stage)
