from pathlib import Path
import json,time,os
r=Path(__file__).resolve().parents[1]
previous=None
while True:
 result={}
 for group,arms in [('training',['uniform','rubric']),('evaluation',['base','uniform','rubric'])]:
  for arm in arms:
   p=r/group/arm/('PROGRESS.json' if group=='training' else 'STATUS.json')
   if not p.exists():continue
   d=json.loads(p.read_text())
   result[f'{group}/{arm}']={k:d[k] for k in ['phase','completed_updates','current_update','micro','micro_total','completed','total'] if k in d}
 state=json.loads((r/'STATUS.json').read_text());result['experiment']=state['phase']
 if result!=previous:print(json.dumps(result,ensure_ascii=False),flush=True);previous=result
 if state['phase']!='running':break
 time.sleep(45)
