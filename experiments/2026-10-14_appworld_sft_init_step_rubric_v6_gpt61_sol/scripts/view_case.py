"""Compact evidence view for researcher review; never used as judge input."""
from pathlib import Path
import json,sys,re
ROOT=Path(__file__).resolve().parents[1]
for sid in sys.argv[1:]:
 p=json.loads((ROOT/'inputs'/f'{sid}.json').read_text()); f=ROOT/'runs/scoring'/sid/'judgement.json'; labels={z[0]:z[1:] for z in json.loads(f.read_text())['steps']} if f.exists() else {}
 print('\nTRAJECTORY',sid,'TASK',p['task'].split('Task:')[-1])
 for s in p['steps']:
  obs=s['observation']
  if 'apis.api_docs.' in s['code'] and 'Execution failed.' not in obs:
   obs='[documentation read; body omitted in compact view]'
  else:
   try: obs=json.dumps(json.loads(obs),ensure_ascii=False)
   except ValueError: pass
   obs=re.sub(r'eyJ[A-Za-z0-9_.-]{30,}','<SYNTHETIC_JWT_VIEW_REDACTED>',obs)
  print(json.dumps({'step':s['id'],'labels':labels.get(s['id']),'commentary':s['commentary'][:950],'code':s['code'][:2500],'observation':obs[:1900]},ensure_ascii=False))
