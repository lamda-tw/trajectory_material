"""Derived descriptive statistics only; no model calls or raw-label mutations."""
from pathlib import Path
from collections import Counter
from statistics import mean
import csv,json
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def rows(p):return list(csv.DictReader((R/p).open()))
s=rows('analysis/step_labels.csv');t=rows('analysis/trajectory_metrics.csv')
a=read('analysis/attempts.json');w=read('analysis/within_task_comparison.json')
c=[json.loads(x) for x in (R/'analysis/step_candidates.jsonl').read_text().splitlines()]
out={'scope':'Descriptive analyses after all scoring finished; not causal validation or gold labels.'}
out['step_flags']={'any_F':sum(any(x[f'R{i}']=='F' for i in range(1,9)) for x in s),'only_R8_F':sum(x['R8']=='F' and all(x[f'R{i}']!='F' for i in range(1,8)) for x in s),'no_F_or_U':sum(all(x[f'R{i}'] not in 'FU' for i in range(1,9)) for x in s)}
out['tasks_with_success']=len({x['task_id'] for x in t if x['official_success']=='True'})
out['termination']=dict(Counter(x['termination'] for x in t))
out['step_outcomes']=dict(Counter(x['official_success'] for x in s))
out['within_task']={}
for i in range(1,9):
 k=f'R{i}_F_fraction_applicable_success_minus_failure';v=[x[k] for x in w if x[k] is not None]
 out['within_task'][f'R{i}']={'tasks':len(v),'lower_F_fraction_for_success':sum(x<0 for x in v),'equal':sum(x==0 for x in v),'higher':sum(x>0 for x in v),'mean_difference':mean(v) if v else None}
out['candidates']={'records':len(c),'distinct_steps':len({(x['id'],x['step']) for x in c}),'by_kind':dict(Counter(x['kind'] for x in c)),'recovery_with_business_F':sum(x.get('business_failure_still_present',False) for x in c),'recovery_from_official_failure':sum(x['kind']=='execution_recovery_candidate' and not x['official_success_for_analysis_only'] for x in c)}
invalid=[x for x in a if x['status']!='valid'];out['invalid_attempts']=[{k:v for k,v in x.items() if k!='usage_reported'} for x in invalid]
out['invalid_attempt_usage']=dict(sum((Counter(x['usage_reported'] or {}) for x in invalid),Counter()))
p=read('analysis/legacy_pilot_comparison.json')
out['legacy_pilot_changes_by_rubric']=dict(Counter(x['rubric'] for x in p['changes']))
out['mechanical_miss_labels']=dict(Counter(x['observed'] for x in read('analysis/mechanical_checks.json')['checks'] if not x['matches'] and x['kind']=='additional_nonempty_python_block'))
(R/'analysis/report_metrics.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(out,ensure_ascii=False,indent=2))
