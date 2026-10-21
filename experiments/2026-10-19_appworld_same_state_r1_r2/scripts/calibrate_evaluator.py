from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import json,os,subprocess,sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json
cfg=json.loads((R/'config/runtime.json').read_text());ids=json.loads((R/'plan_snapshot/same_state_audit.json').read_text())['pilot_state_ids']
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0')
def one(s):
 key=s.replace(':','__');root=R/'calibration/raw/evaluator';root.mkdir(parents=True,exist_ok=True);path=root/f'{key}.job.json';output=root/f'{key}.replay.json'
 job={'input':str(R/'inputs'/f'{key}.json'),'candidate':str(R/'calibration/raw/original_actions'/f'{key}.json'),'output':str(output),'runtime':str(R/'runtime/calibration_action'/key)};atomic_json(path,job)
 with (root/f'{key}.log').open('w') as log:
  subprocess.run([cfg['paths']['appworld_python'],str(R/'scripts/replay_worker.py'),'--job',str(path)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=5400)
  replay=json.loads(output.read_text());original=json.loads(Path(job['candidate']).read_text());reference=json.loads((R/'calibration/raw/replay'/f'{key}__a.json').read_text())
  assert replay['all_observations_exact'] and replay['before_sha256']==reference['before_sha256'] and replay['candidate']['observation']==original['observation']
  checks={}
  for phase in ['before','after']:
   target=root/f'{key}.{phase}.json';subprocess.run([cfg['paths']['appworld_python'],str(R/'scripts/evaluate_snapshot.py'),'--replay',str(output),'--phase',phase,'--output',str(target)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900);checks[phase]=json.loads(target.read_text())
  assert checks['before']['checks'].keys()==checks['after']['checks'].keys()
 return {'state_id':s,'candidate_feedback_matches_original':True,'isolated_evaluator_db_verified':True,'before_passes':checks['before']['num_passes'],'after_passes':checks['after']['num_passes'],'tests':checks['before']['num_tests'],'branch_db_changed':replay['before']['db_tables']!=replay['after']['db_tables']}
rows=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 for f in as_completed([pool.submit(one,s) for s in ids]):
  rows.append(f.result());atomic_json(R/'calibration/evaluator_audit.json',rows);print(json.dumps({'completed':len(rows),**rows[-1]}),flush=True)
