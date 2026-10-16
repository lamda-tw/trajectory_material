from pathlib import Path
from datetime import datetime
import json,time
R=Path(__file__).resolve().parents[1]
while True:
 state=json.loads((R/'STATUS.json').read_text());record={'time':datetime.now().astimezone().isoformat(),'experiment':state['phase'],'stage':state.get('stage')}
 for rel,key in [('training/uniform/PROGRESS.json','training'),('evaluation/uniform/STATUS.json','evaluation')]:
  p=R/rel
  if p.exists():
   d=json.loads(p.read_text());record[key]={k:d[k] for k in ['phase','epoch','update','total_updates','loss','elapsed_seconds','completed','total','successes'] if k in d}
 print(json.dumps(record),flush=True)
 if state['phase'] in ['complete','error']:break
 time.sleep(45)
