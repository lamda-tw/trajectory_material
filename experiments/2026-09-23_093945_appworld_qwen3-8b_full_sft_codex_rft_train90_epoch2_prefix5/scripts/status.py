import json, shutil, time
from pathlib import Path
T=Path(__file__).resolve().parent.parent
E=Path(json.loads((T/'manifest.json').read_text())['evaluation_experiment'])
out={'train_status':(T/'STATUS.txt').read_text().strip(),'eval_status':(E/'STATUS.txt').read_text().strip(),'free_disk_gib':round(shutil.disk_usage(T).free/1024**3,1)}
h=T/'metrics/training_history.jsonl'
if h.exists():
    rows=[json.loads(x) for x in h.read_text().splitlines() if x.strip()]; last=rows[-1] if rows else {}
    out['training']={k:last.get(k) for k in ['step','epoch','train_loss','learning_rate','elapsed_seconds']}
    out['training']['log_age_seconds']=round(time.time()-h.stat().st_mtime)
    if rows: out['training']['peak_gpu_allocated_gib']=round(max(r['peak_allocated_gib'] for x in rows for r in x['ranks']),2)
s=E/'task_status.jsonl'
if s.exists():
    rows=[json.loads(x) for x in s.read_text().splitlines() if x.strip()]
    out['evaluation']={'completed':len(rows),'success':sum(x['status']=='success' for x in rows),'last':rows[-1] if rows else None,'status_age_seconds':round(time.time()-s.stat().st_mtime)}
r=T/'logs/resource_usage.jsonl'
if r.exists():
    with r.open('rb') as f:
        f.seek(max(0,r.stat().st_size-6000)); lines=f.read().splitlines()
    if lines: out['resources']=json.loads(lines[-1])
import sys, subprocess
if out['train_status'].startswith('TRAINING_COMPLETE') or out['eval_status'].startswith(('RUNNING_EVALUATION','EVALUATION_COMPLETE','SUCCESS')):
    out.pop('resources',None)
    out['live_gpu']=subprocess.check_output(['nvidia-smi','--query-gpu=index,memory.used,utilization.gpu','--format=csv,noheader'],text=True).strip()
if '--compact' in sys.argv:
    if 'resources' in out:
        r=out['resources'];out['resources']={k:r[k] for k in ['time_utc','gpu_csv','memory.events'] if k in r}
    if 'evaluation' in out and out['evaluation']['last']:
        r=out['evaluation']['last'];out['evaluation']['last']={k:r[k] for k in ['task_id','status','completed_index'] if k in r}
print(json.dumps(out,ensure_ascii=False,indent=2))
