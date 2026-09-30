"""Finalize only after all three frozen branch runs complete successfully."""
from pathlib import Path
import json,time,subprocess,datetime,os
S=Path(__file__).resolve().parent
names=['CFST-state','CFST-Action','CFST-Mixed']
while True:
 branches={b:json.loads((S/b/'manifest.json').read_text()) for b in names}
 if all(m['status'] in ['awaiting_validation','completed'] and m.get('exit_code')==0 for m in branches.values()):break
 time.sleep(15)
p=S/'manifest.json';m=json.loads(p.read_text())
if m['status']=='completed':raise SystemExit(0)
(S/'supervisor_before_validation.json').write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
m.update(status='awaiting_validation',branches=branches,run_finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),resolved_errors=m.pop('errors',[]),errors=[],completion_supervisor_pid=os.getpid())
p.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
subprocess.run(['/root/miniconda3/bin/python',str(S/'finalize.py')],cwd=S,check=True)
