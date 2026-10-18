from pathlib import Path
import json,hashlib,random
R=Path(__file__).resolve().parents[1];cfg=json.loads((R/'config/training.json').read_text());rows=[json.loads(x) for x in (R/'data/step_inventory.jsonl').read_text().splitlines()]
pred={'random':lambda r:True,'net3':lambda r:r['P']-r['F']>=3,'pass4':lambda r:r['P']>=4,'zerofail3':lambda r:r['F']==0 and r['P']>=3,'highfail3':lambda r:r['F']>=3}
sets={};records=[]
for arm,fn in pred.items():
 pool=sorted([r for r in rows if fn(r)],key=lambda r:r['id'])
 for seed in cfg['seeds']:
  actual=[json.loads(x)['id'] for x in (R/f'data/{arm}/seed_{seed}/selection.jsonl').read_text().splitlines()]
  rng=random.Random(int(hashlib.sha256(f'{seed}:{arm}:selection'.encode()).hexdigest()[:16],16));expected=[r['id'] for r in rng.sample(pool,1710)]
  assert actual==expected and len(set(actual))==1710
  if arm=='zerofail3':assert set(actual)=={r['id'] for r in pool}
  sets[(arm,seed)]=set(actual);records.append({'arm':arm,'seed':seed,'candidate_steps':len(pool),'selected_steps':len(actual),'per_candidate_inclusion_probability':1710/len(pool),'exact_global_sample_reproduced':True})
for arm in cfg['arms']:
 if arm!='zerofail3':assert len({frozenset(sets[arm,s]) for s in cfg['seeds']})==3
result={'passed':True,'method':'One random.sample over each entire score-defined candidate pool; no task IDs read by sampling logic','no_task_quotas':True,'no_redistribution':True,'no_outcome_weighting':True,'runs':records}
(R/'checks/global_sampling.json').write_text(json.dumps(result,indent=2)+'\n');print('PASS: all 15 selections exactly reproduce full-pool uniform sampling; no quotas or redistribution')
