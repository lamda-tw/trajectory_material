"""Reference replay and cached-action execution with one infrastructure retry."""
from a_common import *
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,signal,time
def replay(item,tag,candidate=None):
 x,p=item;sid=x['state_id'];dest=R/'phase_a/execution'/tag/sid;dest.mkdir(parents=True,exist_ok=True)
 inp=R/'phase_a/inputs/replay'/(sid+'.json')
 if not inp.exists():
  s=p['state'];assert file_sha(s['source'])==s['source_sha256'];t=read(s['source']);frozen_json(inp,{'state':s,'history':t['steps'][:s['target_step']-1]})
 job={'input':str(inp),'input_sha256':file_sha(inp),'output':str(dest/'result.json'),'runtime':str(R/'runtime/phase_a_branches'/tag/sid)}
 if candidate:job.update(candidate=str(candidate),candidate_sha256=file_sha(candidate))
 frozen_json(dest/'job.json',job)
 if Path(job['output']).exists():
  result=read(job['output']);assert result['job']==job;return result
 errors=read(dest/'infrastructure_errors.json') if (dest/'infrastructure_errors.json').exists() else []
 for attempt in range(len(errors)+1,3):
  with (dest/f'attempt_{attempt}.log').open('a') as log:
   proc=subprocess.Popen([config()['paths']['appworld_python'],str(R/'scripts/a_replay_worker.py'),'--job',str(dest/'job.json')],env=CPU,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
   try:
    code=proc.wait(timeout=1800)
    if code:raise RuntimeError(f'worker exit {code}: {dest}')
    return read(job['output'])
   except (RuntimeError,subprocess.TimeoutExpired) as e:
    errors.append({'attempt':attempt,'error':str(e),'time':now()});write_json(dest/'infrastructure_errors.json',errors)
   finally:
    if proc.poll() is None:
     os.killpg(proc.pid,signal.SIGTERM)
     try:proc.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 return {'state_id':sid,'infrastructure_failure':True,'errors':errors}
def references(stage):
 authorize();items=packages(stage);results=[]
 def one(item):
  a=replay(item,stage+'_reference_a');b=replay(item,stage+'_reference_b')
  valid=all(not v.get('infrastructure_failure') and v['all_observations_exact'] and v['environment_supported'] for v in [a,b])
  same=valid and a['before_sha256']==b['before_sha256'] and a['prefix_api_sha256']==b['prefix_api_sha256']
  return {'state_id':item[0]['state_id'],'eligible':bool(same),'replicas_valid':valid,'before_sha256':a.get('before_sha256'),'prefix_api_sha256':a.get('prefix_api_sha256'),'unsupported':a.get('before',{}).get('unsupported_variables',[]),'observation_mismatches':[o['step'] for o in a.get('observations',[]) if not o['exact_match']],'infrastructure_failure':a.get('infrastructure_failure',False) or b.get('infrastructure_failure',False)}
 with ThreadPoolExecutor(max_workers=4) as pool:
  for f in as_completed([pool.submit(one,item) for item in items]):
   results.append(f.result());write_json(R/'phase_a/analysis'/f'{stage}_replay_audit.partial.json',results);status(stage+'_reference_replay',completed=len(results),total=len(items),eligible=sum(x['eligible'] for x in results))
 results.sort(key=lambda x:x['state_id']);frozen_json(R/'phase_a/config'/f'{stage}_replay_eligibility.json',{'stage':stage,'frozen_before_generation':True,'states':results})
 return results
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--stage',choices=['calibration','formal'],required=True);references(ap.parse_args().stage)
