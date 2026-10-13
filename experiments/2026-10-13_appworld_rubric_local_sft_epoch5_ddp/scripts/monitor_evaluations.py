from pathlib import Path
from datetime import datetime
import json,time
R=Path(__file__).resolve().parents[1]
while True:
 try:
  state=json.loads((R/'STATUS.json').read_text())
  record={'time':datetime.now().astimezone().isoformat(),'experiment':state['phase'],'stage':state.get('stage'),'evaluations':{}}
  for epoch,arm in [(1,'epoch1'),(3,'epoch3'),(5,'rubric')]:
   p=R/f'evaluation/{arm}/STATUS.json'
   if p.exists():
    d=json.loads(p.read_text());record['evaluations'][str(epoch)]={k:d[k] for k in ['phase','completed','total','successes'] if k in d}
  print(json.dumps(record),flush=True)
  if state['phase'] in ['complete','error']:break
 except (FileNotFoundError,json.JSONDecodeError) as e:
  print(json.dumps({'monitor_read_retry':str(e)}),flush=True)
 time.sleep(45)
