"""Assemble completed human/agent evidence review without modifying judge labels."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json, hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
validation=read(ROOT/'analysis/validation.json')
assert validation['passed'] and validation['trajectories']==540
plan=read(ROOT/'review/semantic_sample_plan.json')
notes=read(ROOT/'review/reviewer_notes.json')
ids={x['id'] for x in plan['samples']}
assert len(ids)==12 and set(notes)==ids and all(x['reviewed'] for x in notes.values())
frozen=read(ROOT/'review/raw_evidence_checks.json')
results=[]
for c in frozen['checks']:
    payload=ROOT/'inputs'/f"{c['id']}.json"
    assert sha(payload)==frozen['input_hashes'][c['id']]
    rows={x[0]:x for x in read(ROOT/'runs/scoring'/c['id']/'judgement.json')['steps']}
    row=rows[c['step_id']]
    observed=row[1][int(c['rubric'][1:])-1]
    results.append({**c,'observed':observed,'matched':observed==c['expected'],'judge_reason':row[2]})
flags=read(ROOT/'analysis/mechanical_review_flags.json')
mechanical_notes=read(ROOT/'review/mechanical_notes.json') if flags else []
assert len(mechanical_notes)==len(flags)
assert all(x.get('reviewed') for x in mechanical_notes)
errors=[e for n in notes.values() for e in n['confirmed_errors']]
boundaries=[e for n in notes.values() for e in n['boundary_disagreements']]
for n in mechanical_notes:
    errors.extend(n.get('confirmed_errors',[])); boundaries.extend(n.get('boundary_disagreements',[]))
for r in results:
    if not r['matched']:
        assert any((x['id'],x['step_id'],x['rubric'])==(r['id'],r['step_id'],r['rubric']) for x in errors+boundaries),r
steps=sum(len(read(ROOT/'runs/scoring'/i/'judgement.json')['steps']) for i in ids)
review={'complete':True,'completed_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
 'method':'Primary agent inspected compact raw histories, expanded critical evidence, all sample labels and 53 targeted checks frozen before corresponding scores arrived. No independent gold-standard judge or semantic rerolls.',
 'sample_trajectories':len(ids),'sample_steps':steps,'pilot_trajectories':8,
 'pilot_review':'review/pilot_review.json','sample_plan':'review/semantic_sample_plan.json',
 'frozen_checks_sha256':sha(ROOT/'review/raw_evidence_checks.json'),'targeted_checks':len(results),
 'targeted_checks_matched':sum(r['matched'] for r in results),'check_results':results,
 'case_notes':notes,'mechanical_scan':{'trajectories':540,'steps':9886,'flags':flags,'review_notes':mechanical_notes,'scope':'Conservative direct non-business API calls with R5!=N; explicit execution failures with R1!=F. This is not complete program analysis.'},
 'confirmed_errors':errors,'boundary_disagreements':boundaries,
 'accepted_labels_edited':False,'semantic_rerolls':0,
 'limitations':['Purposive checks do not estimate overall label accuracy.','Only selected critical evidence is reviewed, not every cell against an independent gold standard.','Boundary disagreements remain in original scores and must be considered explicitly by downstream filtering.']}
(ROOT/'review/semantic_review.json').write_text(json.dumps(review,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:review[k] for k in ['complete','sample_trajectories','sample_steps','targeted_checks','targeted_checks_matched']}))
