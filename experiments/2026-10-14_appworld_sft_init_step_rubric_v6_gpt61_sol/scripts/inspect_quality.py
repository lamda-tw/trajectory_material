from pathlib import Path
import json
from analyze_results import narrow_read_only
ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads(p.read_text())
checks=read(ROOT/'review/raw_evidence_checks.json')['checks']; reviewed=[]; mismatch=[]
for c in checks:
 f=ROOT/'runs/scoring'/c['id']/'judgement.json'
 if f.exists():
  j=read(f); rows={r[0]:r for r in j['steps']}; label=rows[c['step_id']][1][int(c['rubric'][1:])-1]; reviewed.append(c)
  if label!=c['expected']: mismatch.append({**c,'observed':label,'reason':rows[c['step_id']][2]})
flags=[]
for f in sorted((ROOT/'runs/scoring').glob('*/judgement.json')):
 p=read(f.parent/'input.json'); j=read(f)
 for s,row in zip(p['steps'],j['steps']):
  if narrow_read_only(s['code']) and row[1][4]!='N': flags.append({'id':f.parent.name,'step_id':s['id'],'rubric':'R5','observed':row[1][4],'reason':row[2],'code':s['code'][:500]})
print(json.dumps({'review_checks_ready':len(reviewed),'review_checks_total':len(checks),'mismatches':mismatch,'R5_mechanical_flags':flags},ensure_ascii=False))
