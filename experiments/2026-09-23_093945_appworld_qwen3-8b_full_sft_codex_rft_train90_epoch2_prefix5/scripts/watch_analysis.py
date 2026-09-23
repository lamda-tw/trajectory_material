#!/usr/bin/env python3
"""Run read-only result analysis once each fixed pipeline stage finishes."""
import json,os,subprocess,time
from pathlib import Path
T=Path(__file__).resolve().parent.parent;W=T.parent.parent
E=Path(json.loads((T/'manifest.json').read_text())['evaluation_experiment'])
env=os.environ.copy();env.update(PYTHONDONTWRITEBYTECODE='1',MPLCONFIGDIR=str(T/'cache/matplotlib'),TMPDIR=str(T/'tmp'),XDG_CACHE_HOME=str(T/'cache/xdg'))
def state(root):return json.loads((root/'manifest.json').read_text())['status']
def execute(script,log):
    with log.open('w') as f:subprocess.run([str(W/'.conda-training/bin/python'),str(script)],cwd=W,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
while not (T/'metrics/metrics.json').exists():
    if state(T)=='FAILED':raise RuntimeError('Training pipeline failed')
    time.sleep(20)
assert json.loads((T/'metrics/metrics.json').read_text())['status']=='SUCCESS'
execute(T/'scripts/audit_training.py',T/'logs/06_prefix_audit.log')
print('Training prefix audit and loss plots completed.',flush=True)
while state(E)!='EVALUATION_COMPLETE_AWAITING_REPORT':
    if state(T)=='FAILED' or state(E)=='FAILED':raise RuntimeError('Pipeline failed')
    time.sleep(20)
execute(E/'scripts/build_comparison.py',E/'logs/02_comparison.log')
execute(E/'scripts/render_reports.py',E/'logs/03_render_reports.log')
print('Official score comparison and draft reports completed; case review and final artifact audit remain.',flush=True)
