"""One isolated live Python/AppWorld branch, a fixed first response, then a fixed receiver."""
from pathlib import Path
import argparse,json,os,sys,time,traceback
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha,parse_code
from policy_server import sample_step,request
from sampling import bounded_sample
from api_capture import attach_capture
from replay_worker import fingerprint,save_exact_snapshot,encode

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--job',type=Path,required=True);args=ap.parse_args();job=json.loads(args.job.read_text());cfg=json.loads((R/'config/runtime.json').read_text());inp=Path(job['input']);candidatep=Path(job['candidate']);expectedp=Path(job['expected_first_execution']);d=json.loads(inp.read_text());candidate=json.loads(candidatep.read_text());expected=json.loads(expectedp.read_text());runtime=Path(job['runtime']);out=Path(job['output'])
 for p,field in [(inp,'input_sha256'),(candidatep,'candidate_sha256'),(expectedp,'expected_first_execution_sha256')]:assert file_sha(p)==job[field],field
 assert cfg['server']['gpu']=='GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
 runtime.mkdir(parents=True,exist_ok=True)
 if not (runtime/'data').exists():(runtime/'data').symlink_to(cfg['paths']['appworld_data'],target_is_directory=True)
 cache=runtime/'cache';cache.mkdir(exist_ok=True)
 if not (cache/'tests').exists():(cache/'tests').symlink_to(cfg['paths']['appworld_test_cache'],target_is_directory=True)
 os.environ['APPWORLD_ROOT']=str(runtime);os.environ['APPWORLD_CACHE']=str(cache);os.chdir(runtime)
 from appworld import AppWorld,update_root
 update_root(str(runtime));began=time.monotonic();k=int(d['state']['before_step']);max_extra=job['max_followup_calls'];readouts=job['readouts'];assert k+max_extra<=50
 result={'state_id':d['state']['state_id'],'task_id':d['state']['task_id'],'job':job,'observations':[],'followup_steps':[],'readout_actual_followup_steps':{}}
 messages=[dict(m) for m in d['messages']]
 generation_dir=Path(job['generation_directory']);generation_dir.mkdir(parents=True,exist_ok=True)
 with AppWorld(task_id=d['state']['task_id'],experiment_name='branch',max_interactions=50,load_ground_truth=True,ground_truth_mode='minimal',random_seed=100,raise_on_failure=True) as world:
  baseline=dict(world.shell.user_ns)
  for s in d['history']:
   obs=world.execute(s['code']) if s['code'] else '';assert obs==s['observation'],'Continuation prefix observation mismatch'
   result['observations'].append({'step':s['step'],'original_sha256':digest(s['observation']),'replay_sha256':digest(obs),'exact_match':True})
  result['before']=fingerprint(world,baseline);result['before_sha256']=digest(result['before'])
  assert not result['before']['unsupported_variables'] and result['before_sha256']==expected['before_sha256'],'Continuation prefix fingerprint mismatch'
  world.save_state();save_exact_snapshot(world,runtime/'snapshots/before')
  captures=attach_capture(world.requester,encode)
  code=candidate['code'];request_start=len(world.requester.request_tracker.requests);obs=world.execute(code) if code else ''
  result['candidate']={'text':candidate['text'],'code':code,'observation':obs,'execution_error':obs.startswith('Execution failed.'),'no_code':not bool(code),'actual_requests':encode(world.requester.request_tracker.requests[request_start:]),'actual_request_methods_urls':[{'method':x['method'],'url':x['url']} for x in world.requester.request_tracker.requests[request_start:]]}
  result['candidate']['local_api_responses']=list(captures)
  result['after']=fingerprint(world,baseline)
  assert not result['after']['unsupported_variables'],'Unsupported post-first-action state'
  assert obs==expected['candidate']['observation'] and result['after']==expected['after'],'Fixed first action replay mismatch'
  world.save_state();save_exact_snapshot(world,runtime/'snapshots/after')
  messages.append({'role':'assistant','content':candidate['history_assistant_text']+'\n\n'})
  if code:messages.append({'role':'user','content':'Output:\n```\n'+obs.rstrip()+'\n```\n\n'})
  termination='no_python_code' if not code else 'completion_api' if world.task_completed() else None
  def snapshot(h,actual):
   name=f'h{h}';result[name]=fingerprint(world,baseline);world.save_state();save_exact_snapshot(world,runtime/'snapshots'/name);result['readout_actual_followup_steps'][name]=actual
  for j in range(1,max_extra+1):
   if termination:break
   absolute=k+j;path=generation_dir/f'step_{absolute:02d}.json';seed=100+absolute-1
   if path.exists():
    sample=json.loads(path.read_text());tokenized=request(cfg,'/tokenize',{'model':job['served_model_name'],'messages':messages,'add_generation_prompt':True,'add_special_tokens':False,'chat_template_kwargs':{'enable_thinking':False}})['tokens']
    assert sample['prompt_ids']==tokenized and sample['receiver_sha256']==job['receiver_sha256'] and sample['absolute_step']==absolute and sample['sampling_seed']==seed,'Cached continuation input changed'
   else:
    sample=bounded_sample(cfg,job['served_model_name'],messages,seed,path,{'receiver_sha256':job['receiver_sha256'],'absolute_step':absolute,'sampling_seed':seed})
    if sample is None:termination='context_limit';break
   code=sample['code'];request_start=len(world.requester.request_tracker.requests);capture_start=len(captures);obs=world.execute(code) if code else ''
   step=dict(sample,step=absolute,followup_step=j,observation=obs,execution_error=obs.startswith('Execution failed.'),actual_requests=encode(world.requester.request_tracker.requests[request_start:]),actual_request_methods_urls=[{'method':x['method'],'url':x['url']} for x in world.requester.request_tracker.requests[request_start:]])
   step['local_api_responses']=captures[capture_start:]
   result['followup_steps'].append(step);messages.append({'role':'assistant','content':sample['history_assistant_text']+'\n\n'})
   if not code:termination='no_python_code'
   else:
    messages.append({'role':'user','content':'Output:\n```\n'+obs.rstrip()+'\n```\n\n'})
    if world.task_completed():termination='completion_api'
   if j in readouts:snapshot(j,j)
   result['termination']=termination or 'in_progress';atomic_json(out.with_suffix('.partial.json'),result)
  performed=len(result['followup_steps'])
  if not termination:termination='followup_budget_limit'
  for h in readouts:
   if f'h{h}' not in result:snapshot(h,performed)
  result.update(termination=termination,performed_followup_steps=performed,all_observations_exact=True,environment_supported=True,first_action_replay_exact=True,elapsed_seconds=time.monotonic()-began)
 atomic_json(out,result);out.with_suffix('.partial.json').unlink(missing_ok=True)
 print(json.dumps({'state_id':result['state_id'],'followup_steps':performed,'termination':termination,'seconds':result['elapsed_seconds']}),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:traceback.print_exc();raise
