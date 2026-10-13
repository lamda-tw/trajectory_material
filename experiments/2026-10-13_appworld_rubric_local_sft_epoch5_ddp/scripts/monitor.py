from pathlib import Path
from datetime import datetime
import json,time
R=Path(__file__).resolve().parents[1]
while True:
 state=json.loads((R/'STATUS.json').read_text());record={'time':datetime.now().astimezone().isoformat(),'experiment':state['phase'],'stage':state.get('stage')}
 for rel,key in [('training/rubric/PROGRESS.json','training'),('evaluation/rubric/STATUS.json','evaluation')]:
  p=R/rel
  if p.exists():
   d=json.loads(p.read_text());record[key]={k:d[k] for k in ['phase','epoch','update','update_in_epoch','total_updates','loss','completed','total','successes','elapsed_seconds'] if k in d}
 print(json.dumps(record),flush=True)
 if state['phase']!='running':break
 time.sleep(45)
