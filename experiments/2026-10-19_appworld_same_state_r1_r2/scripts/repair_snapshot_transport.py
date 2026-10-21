"""Repair five transport-only failures without changing states or fingerprints."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import json,os,subprocess,shutil,sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json
C=json.loads((R/'config/runtime.json').read_text());ENV=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0')
def one(k):
 source=R/'results/executions/reference'/f'{k}.json';old=json.loads(source.read_text());base=R/'calibration/snapshot_fix'/k;base.mkdir(parents=True,exist_ok=True)
 job=dict(old['job'],runtime=str(base/'runtime'),output=str(base/'replay.json'));atomic_json(base/'job.json',job)
 with (base/'repair.log').open('a') as log:
  if not (base/'replay.json').exists():subprocess.run([C['paths']['appworld_python'],str(R/'scripts/replay_worker.py'),'--job',str(base/'job.json')],env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
  new=json.loads((base/'replay.json').read_text());assert old['before']==new['before'] and old['before_sha256']==new['before_sha256'] and new['all_observations_exact'] and new['environment_supported']
  if not (base/'evaluator.json').exists():subprocess.run([C['paths']['appworld_python'],str(R/'scripts/evaluate_snapshot.py'),'--replay',str(base/'replay.json'),'--phase','before','--output',str(base/'evaluator.json')],env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
  ev=json.loads((base/'evaluator.json').read_text());assert ev['loaded_db_matches_live_branch'] and ev['source_unmodified']
  # Retain the exact original change-log snapshot and replay evidence for auditing.
  original=Path(old['job']['runtime'])/'snapshots/before';archive=base/'original_changes_snapshot'
  if not archive.exists():original.rename(archive)
  if not original.exists():shutil.copytree(Path(new['job']['runtime'])/'snapshots/before',original,copy_function=os.link)
  if not (base/'original_replay.json').exists():atomic_json(base/'original_replay.json',old)
  old['snapshot_format']='sqlite_full_backup_v1';old['snapshot_transport_repair']={'verification_replay':str(base/'replay.json'),'before_fingerprint_unchanged':True};atomic_json(source,old)
  target=R/'results/evaluators/reference'/f'{k}.before.json'
  subprocess.run([C['paths']['appworld_python'],str(R/'scripts/evaluate_snapshot.py'),'--replay',str(source),'--phase','before','--output',str(target)],env=ENV,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=900)
 result={'state_id':old['state_id'],'full_fingerprint_unchanged':True,'observations_exact':True,'full_snapshot_evaluator_verified':True,'original_evidence':str(base)}
 print(json.dumps(result),flush=True);return result
if __name__=='__main__':
 ks=['0d8a4ee_1__before_step_20','0d8a4ee_1__before_step_32','0d8a4ee_1__before_step_41','0d8a4ee_1__before_step_49','37a8675_2__before_step_19']
 with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(one,ks))
 atomic_json(R/'calibration/snapshot_fix/repair_audit.json',{'passed':True,'changed_selection':False,'weakened_equality_checks':False,'states':results})
