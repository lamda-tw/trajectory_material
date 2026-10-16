"""Candidate selection analysis using only frozen R1-R8 labels. No training."""
from pathlib import Path
import csv,json,hashlib,math
from collections import Counter
ROOT=Path(__file__).resolve().parent
source=ROOT.parent/'step_labels.csv'
with source.open() as f: rows=list(csv.DictReader(f))
for x in rows:
    labels=x['labels'];assert len(labels)==8 and set(labels)<=set('PFUN')
    for c in 'PFUN':x[c+'_count']=labels.count(c)
    x['net_score']=x['P_count']-x['F_count']
    x['candidate_score_ge_4']=int(x['net_score']>=4)
with (ROOT/'all_step_scores.csv').open('w',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def describe(a):
    return {'steps':len(a),'fraction':len(a)/len(rows),'tasks_diagnostic_only':len({x['task_id'] for x in a}),
        'trajectories_diagnostic_only':len({x['trajectory_id'] for x in a}),
        'any_F':sum(x['F_count']>0 for x in a),'any_U':sum(x['U_count']>0 for x in a),
        'labels':{f'R{i}':dict(Counter(x[f'R{i}'] for x in a)) for i in range(1,9)}}
n=math.ceil(.3*len(rows));cut=sorted((x['net_score'] for x in rows),reverse=True)[n-1]
strict=[x for x in rows if x['net_score']>cut]; tied=[x for x in rows if x['net_score']==cut]
summary={'status':'analysis_and_recommendation_only_not_training_manifest','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
 'score':{'P':1,'F':-1,'U':0,'N':0},'selection_inputs':'R1-R8 labels only; IDs identify rows; task and trajectory coverage is diagnostic, never a filter.',
 'all_steps':describe(rows),'distribution':dict(sorted(Counter(x['net_score'] for x in rows).items())),
 'thresholds':{str(t):describe([x for x in rows if x['net_score']>=t]) for t in range(0,8)},
 'exact_top_30_percent':{'rounding':'ceil','target_steps':n,'boundary_score':cut,'strictly_above':len(strict),'boundary_pool':len(tied),'required_from_boundary':n-len(strict),'boundary_pool_any_F':sum(x['F_count']>0 for x in tied)},
 'recommendation':{'rule':'P_count - F_count >= 4','extra_filters':[],'status':'proposed based on distribution, not optimized against DEV outcomes','rationale':'Near 30 percent without arbitrarily splitting a large tied score group. Includes every step meeting the same threshold, including F/U labels.'},
 'limitations':['Equal dimension weights and compensability are assumptions, not calibrated learning value.','U and N share numeric weight but retain distinct labels.','Applicable-dimension count affects attainable score.','Step labels do not localize good/bad target tokens.','Positive SFT imitates all target tokens of a selected step; a negative rubric label does not create negative loss.']}
(ROOT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'top30':summary['exact_top_30_percent'],'ge4':summary['thresholds']['4']},ensure_ascii=False))
