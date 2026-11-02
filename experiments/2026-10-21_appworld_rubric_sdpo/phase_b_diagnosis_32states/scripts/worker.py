"""Replay an original state in a fresh AppWorld and execute at most four actions."""
from pathlib import Path
import sys,os,argparse,time
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from a_common import read,write_json,digest,file_sha,CPU,parse_code
from a_state import fingerprint,encode
from api_capture import attach_capture
from a_policy_server import sample_step
from b_appworld_log_compat import install_request_log_compatibility
p=argparse.ArgumentParser();p.add_argument('--job',required=True);args=p.parse_args();job=read(args.job)
cfg=read(D/'config/runtime.json');auth=read(D/'config/authorization.json');assert not auth['training']
s=read(job['state_path']);assert file_sha(job['state_path'])==job['state_sha256']
runtime=Path(job['runtime']);runtime.mkdir(parents=True,exist_ok=True)
for rel,source in [('data',cfg['paths']['appworld_data']),('cache/tests',cfg['paths']['appworld_test_cache'])]:
 path=runtime/rel;path.parent.mkdir(parents=True,exist_ok=True)
 if not path.exists():path.symlink_to(source,target_is_directory=True)
os.environ.update(CPU,APPWORLD_ROOT=str(runtime),APPWORLD_CACHE=str(runtime/'cache'));os.chdir(runtime)
from appworld import AppWorld,update_root
update_root(str(runtime));install_request_log_compatibility();started=time.monotonic()
result={'job':job,'state_id':s['id'],'replay_matches':[],'actions':[],'parameter_updates':0}
with AppWorld(task_id=s['task_id'],experiment_name='diagnosis',max_interactions=50,load_ground_truth=True,ground_truth_mode='minimal',random_seed=100,raise_on_failure=True) as world:
 baseline=dict(world.shell.user_ns);capture=attach_capture(world.requester,encode)
 for old in s['history']:
  obs=world.execute(old['code']) if old['code'] else ''
  result['replay_matches'].append({'step':old['step'],'exact':obs==old['observation'],'original_sha256':digest(old['observation']),'actual_sha256':digest(obs)})
 before=fingerprint(world,baseline)
 result.update(before=before,before_sha256=digest(before),prefix_api_sha256=digest(capture),all_observations_exact=all(x['exact'] for x in result['replay_matches']),environment_supported=not before['unsupported_variables'])
 assert result['all_observations_exact'] and result['environment_supported'] and not before['completed'],'Invalid original state replay'
 if job['condition']!='replay':
  reference=read(D/'replay'/s['id']/'result.json')
  assert result['before_sha256']==reference['before_sha256'] and result['prefix_api_sha256']==reference['prefix_api_sha256'],'Branch state differs from frozen replay'
  messages=list(s['messages']);result['termination']='four_action_budget'
  for i in range(4):
   current=messages+([{'role':'user','content':s['c2_message']}] if i==0 and job['condition']=='C2' else [])
   g=sample_step(cfg,job['served_model'],current,100+i,evaluation=True)
   if g is None:result['termination']='context_limit';break
   if i==0:assert g['prompt_ids']==s['example']['teacher_prompt_ids' if job['condition']=='C2' else 'prompt_ids']
   code,history=parse_code(g['text']);n=len(capture);obs=world.execute(code) if code else ''
   row={**g,'step':s['target_step']+i,'code':code,'history_assistant_text':history,'observation':obs,'execution_error':obs.startswith('Execution failed.'),'api_responses':capture[n:],'completed':bool(world.task_completed())}
   result['actions'].append(row);write_json(job['output']+'.partial',result)
   messages.append({'role':'assistant','content':history+'\n\n'})
   if not code:result['termination']='no_python_code';break
   messages.append({'role':'user','content':'Output:\n```\n'+obs.rstrip()+'\n```\n\n'})
   if row['completed']:result['termination']='completion_api';break
  result['after']=fingerprint(world,baseline)
result['elapsed_seconds']=time.monotonic()-started;write_json(job['output'],result)
print({'state':s['id'],'model':job.get('model'),'condition':job['condition'],'actions':len(result['actions']),'seconds':round(result['elapsed_seconds'],1)},flush=True)
