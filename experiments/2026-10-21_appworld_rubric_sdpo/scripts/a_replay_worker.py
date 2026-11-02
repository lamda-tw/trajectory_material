"""Fresh process/world per branch; full prefix replay reconstructs Python and DB state."""
from a_common import *
import argparse,time
from a_state import fingerprint,save_exact_snapshot,encode
from api_capture import attach_capture
def main():
 p=argparse.ArgumentParser();p.add_argument('--job',required=True);a=p.parse_args();job=read(a.job);authorize();cfg=config()
 d=read(job['input']);assert file_sha(job['input'])==job['input_sha256']
 runtime=Path(job['runtime']);runtime.mkdir(parents=True,exist_ok=True)
 if not (runtime/'data').exists():(runtime/'data').symlink_to(cfg['paths']['appworld_data'],target_is_directory=True)
 cache=runtime/'cache';cache.mkdir(exist_ok=True)
 if not (cache/'tests').exists():(cache/'tests').symlink_to(cfg['paths']['appworld_test_cache'],target_is_directory=True)
 os.environ.update(CPU,APPWORLD_ROOT=str(runtime),APPWORLD_CACHE=str(cache));os.chdir(runtime)
 from appworld import AppWorld,update_root
 update_root(str(runtime));t=time.monotonic();out={'state_id':d['state']['public_state_id'],'job':job,'observations':[]}
 with AppWorld(task_id=d['state']['task_id'],experiment_name='branch',max_interactions=50,load_ground_truth=True,ground_truth_mode='minimal',random_seed=100,raise_on_failure=True) as world:
  baseline=dict(world.shell.user_ns);capture=attach_capture(world.requester,encode)
  for s in d['history']:
   obs=world.execute(s['code']) if s['code'] else ''
   out['observations'].append({'step':s['step'],'exact_match':obs==s['observation'],'original_sha256':digest(s['observation']),'replay_sha256':digest(obs),'replayed':obs})
  before=fingerprint(world,baseline);out.update(before=before,before_sha256=digest(before),all_observations_exact=all(x['exact_match'] for x in out['observations']),environment_supported=not before['unsupported_variables'],prefix_api_responses=list(capture),prefix_api_sha256=digest(capture))
  world.save_state();save_exact_snapshot(world,runtime/'snapshots/before')
  if job.get('candidate'):
   assert file_sha(job['candidate'])==job['candidate_sha256'];g=read(job['candidate']);code=g['code'];n=len(capture);request_start=len(world.requester.request_tracker.requests)
   obs=world.execute(code) if code else ''
   out['candidate']={'text':g['text'],'code':code,'observation':obs,'execution_error':obs.startswith('Execution failed.'),'no_code':not bool(code),'code_repeated':bool(code.strip()) and code.strip() in [x['code'].strip() for x in d['history']],'actual_requests':encode(world.requester.request_tracker.requests[request_start:]),'local_api_responses':capture[n:]}
   out['after']=fingerprint(world,baseline);out['termination']='no_python_code' if not code else ('completion_api' if out['after']['completed'] else 'diagnostic_one_action_budget')
   world.save_state();save_exact_snapshot(world,runtime/'snapshots/after')
 out['elapsed_seconds']=time.monotonic()-t;write_json(job['output'],out)
 print(json.dumps({'state':out['state_id'],'observations_exact':out['all_observations_exact'],'supported':out['environment_supported'],'seconds':out['elapsed_seconds']}),flush=True)
if __name__=='__main__':main()
