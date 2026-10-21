from pathlib import Path
import json,subprocess,sys,os
from concurrent.futures import ThreadPoolExecutor,as_completed
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json
from progress import update
c=json.loads((R/'config/runtime.json').read_text());audit=json.loads((R/'plan_snapshot/same_state_audit.json').read_text())
update('授权与GPU1核对','物理GPU1显存0MiB，无计算进程；UUID已冻结。','complete')
update('输入token核验','299正式+8校准状态全部逐token等于原轨迹。','complete')
jobs=[]
for s in audit['pilot_state_ids']:
 key=s.replace(':','__')
 for rep in ['a','b']:
  name=f'{key}__{rep}';job={'input':str(R/'inputs'/f'{key}.json'),'output':str(R/'calibration/raw/replay'/f'{name}.json'),'runtime':str(R/'runtime/calibration'/name)};jobs.append(job)
def one(job):
 path=R/'calibration/raw/jobs'/f"{Path(job['output']).stem}.json";atomic_json(path,job)
 with path.with_suffix('.log').open('w') as log:
  subprocess.run([c['paths']['appworld_python'],str(R/'scripts/replay_worker.py'),'--job',str(path)],stdout=log,stderr=subprocess.STDOUT,env=dict(os.environ,CUDA_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0'),check=True,timeout=5400)
 return json.loads(Path(job['output']).read_text())
results=[]
with ThreadPoolExecutor(max_workers=4) as pool:
 for f in as_completed([pool.submit(one,j) for j in jobs]):
  results.append(f.result());update('双重重放校准',f'{len(results)}/16独立重放完成。',completed=len(results),total=16)
rows=[]
for s in audit['pilot_state_ids']:
 a,b=sorted([x for x in results if x['state_id']==s],key=lambda x:x['job']['output'])
 rows.append({'state_id':s,'both_observations_exact':a['all_observations_exact'] and b['all_observations_exact'],'fingerprints_equal':a['before_sha256']==b['before_sha256'],'unsupported_a':a['before']['unsupported_variables'],'unsupported_b':b['before']['unsupported_variables'],'seconds':[a['elapsed_seconds'],b['elapsed_seconds']]})
atomic_json(R/'calibration/replay_audit.json',rows)
ok=all(x['both_observations_exact'] and x['fingerprints_equal'] and not x['unsupported_a'] and not x['unsupported_b'] for x in rows)
update('双重重放校准','8状态双重重放通过。' if ok else '存在差异，正式生成门禁保持关闭；详见 calibration/replay_audit.json。','complete' if ok else 'needs_diagnosis')
if not ok:raise SystemExit(2)
