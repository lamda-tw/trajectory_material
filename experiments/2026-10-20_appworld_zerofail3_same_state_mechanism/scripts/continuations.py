"""Fixed-receiver branch matrix, resumable with first-valid generation preservation."""
from experiment import *
from policy_server import owned_server

def branch(row,first,receiver,served,calibration=False):
 name=model_key(first);receiver_name=model_key(receiver);prefix='calibration_' if calibration else '';first_tag=prefix+name;tag=prefix+'continuation/'+receiver_name+'/'+name
 candidate=R/'results/generations'/first_tag/f'{key(row)}.json';expected=R/'results/executions'/first_tag/f'{key(row)}.json'
 assert read(expected)['all_observations_exact'] and read(expected)['environment_supported']
 folder=R/'results/continuations'/tag;folder.mkdir(parents=True,exist_ok=True);out=folder/f'{key(row)}.json';maximum=3 if calibration else 12;readouts=[1,3] if calibration else [4,12]
 job={'input':str(R/'inputs'/f'{key(row)}.json'),'input_sha256':file_sha(R/'inputs'/f'{key(row)}.json'),'candidate':str(candidate),'candidate_sha256':file_sha(candidate),'expected_first_execution':str(expected),'expected_first_execution_sha256':file_sha(expected),'output':str(out),'runtime':str(R/'runtime/branches'/tag/key(row)),'generation_directory':str(R/'results/continuation_generations'/tag/key(row)),'max_followup_calls':maximum,'readouts':readouts,'served_model_name':served,'receiver':receiver_name,'receiver_sha256':receiver['adapter_sha256'],'first_model':name,'first_seed':first['training_seed'],'calibration':calibration}
 if out.exists():assert read(out)['job']==job,'Continuation cached job changed'
 else:
  jobpath=folder/f'{key(row)}.job.json';atomic_json(jobpath,job);errp=folder/f'{key(row)}.errors.json';errors=read(errp) if errp.exists() else []
  for attempt in range(len(errors)+1,4):
   try:
    run_worker([C['paths']['appworld_python'],str(R/'scripts/continuation_worker.py'),'--job',str(jobpath)],folder/f'{key(row)}.attempt{attempt}.log',7200);break
   except (RuntimeError,subprocess.TimeoutExpired) as e:
    errors.append({'attempt':attempt,'error':repr(e)});atomic_json(errp,errors)
  if not out.exists():raise RuntimeError('Continuation exhausted bounded attempts: '+str(out))
 result=read(out);assert result['first_action_replay_exact']
 evals={}
 for h in readouts:
  ev=evaluate(row,tag,f'h{h}',replay_path=out);evals[f'h{h}']={'passes':ev['num_passes'],'tests':ev['num_tests'],'success':ev['success']}
 summary={'state_id':row['state_id'],'panel':row.get('continuation_panel','calibration'),'first_model':name,'receiver':receiver_name,'status':'complete','first_action_replay_exact':True,'performed_followup_steps':result['performed_followup_steps'],'termination':result['termination'],'readout_actual_followup_steps':result['readout_actual_followup_steps'],'evaluators':evals,'source':str(out)}
 atomic_json(R/'results/continuation_checks'/tag/f'{key(row)}.json',summary);return summary

def run(calibration=False):
 all_models=models();receiver_models=[m for m in all_models if m['training_seed']==20261015]
 node='27个校准动作与短续跑' if calibration else '540个固定策略续跑分支'
 if calibration:
  fixtures=read(R/'plan_snapshot/calibration_followup_manifest.json')['fixtures'];lookup={r['state_id']:r for r in rows('calibration_states.csv')};items=[(lookup[f['state_id']],next(m for m in all_models if m['group']==f['first_action_group'] and m['training_seed']==f['first_action_seed'])) for f in fixtures]
 else:
  from run_phase1 import verify_gate
  verify_gate();assert read(R/'config/phase1_completed.json')['complete']
  selected=rows('continuation_states.csv');valid=[];coverage=[]
  for row in selected:
   checks=[read(R/'results/paired_checks'/model_key(m)/f'{key(row)}.json') for m in all_models]
   ok=all(x['execution_valid'] and x['after_state_supported'] for x in checks)
   coverage.append({'state_id':row['state_id'],'panel':row['continuation_panel'],'common_first_replay_valid':ok,'reason':'valid' if ok else 'first_branch_replay_or_state_encoding_unreliable'})
   if ok:valid.append(row)
  atomic_json(R/'analysis/continuation_state_coverage.json',coverage)
  items=[(r,m) for r in valid for m in all_models]
 results=[]
 for receiver in receiver_models:
  prefix='calibration_' if calibration else '';pending=[]
  for row,first in items:
   tag=prefix+'continuation/'+model_key(receiver)+'/'+model_key(first);target=R/'results/continuation_checks'/tag/f'{key(row)}.json'
   if target.exists():results.append(read(target))
   else:pending.append((row,first))
  if not pending:continue
  with gpu_lock(node):
   adapter=W/receiver['adapter'];assert file_sha(adapter)==receiver['adapter_sha256']
   with owned_server(C,R/'logs/servers'/(prefix+'receiver_'+model_key(receiver)),adapter.parent) as served:
    def one(x):return branch(*x,receiver,served,calibration=calibration)
    # Three live environments at most, matching the service's three sequence slots.
    with ThreadPoolExecutor(max_workers=3) as pool:
     for f in as_completed([pool.submit(one,x) for x in pending]):
      results.append(f.result());update(node,f"接手策略{model_key(receiver)}；完成{len(results)}/{len(items)*3}分支。",completed=len(results),total=len(items)*3)
  atomic_json(R/('calibration/continuation_audit.json' if calibration else 'analysis/continuation_audit.json'),results)
 update(node,f"固定策略续跑{len(results)}/{len(items)*3}分支完成。",'complete',completed=len(results),total=len(items)*3)
 return results
if __name__=='__main__':
 import argparse
 ap=argparse.ArgumentParser();ap.add_argument('--calibration',action='store_true');a=ap.parse_args();run(a.calibration)
