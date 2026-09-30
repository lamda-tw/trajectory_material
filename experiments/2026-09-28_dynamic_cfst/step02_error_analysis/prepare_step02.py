#!/usr/bin/env python3
"""Freeze the prespecified family split and failure-review order from step 1."""
from pathlib import Path
import collections,csv,datetime,hashlib,json,random,sys
stage=Path(__file__).resolve().parent
source=stage.parent/'step01_train90_student_rollouts'
seed=20260928
if (stage/'task_split.json').exists():
    raise SystemExit('Split already frozen. Refusing to regenerate it.')
rows=list(csv.DictReader((source/'task_results.csv').open()))
ids=(source/'config/task_ids.txt').read_text().splitlines()
assert len(rows)==len(ids)==90 and {r['task_id'] for r in rows}==set(ids)
by_id={r['task_id']:r for r in rows}
families=collections.defaultdict(list)
for row in rows:families[row['scenario_id']].append(row)
assert len(families)==30 and all(len(v)==3 for v in families.values())
assert all(len({r['difficulty'] for r in v})==1 for v in families.values())
rng=random.Random(seed)
source_families=[];check_families=[];strata=[]
for diff,nsource in [(1,8),(2,8),(3,4)]:
    family_ids=sorted(k for k,v in families.items() if int(v[0]['difficulty'])==diff)
    rng.shuffle(family_ids)
    a,b=family_ids[:nsource],family_ids[nsource:]
    source_families.extend(a);check_families.extend(b)
    strata.append({'difficulty':diff,'shuffled_family_order':family_ids,'source_families':a,'check_families':b})
source_ids=[t for t in ids if by_id[t]['scenario_id'] in source_families]
check_ids=[t for t in ids if by_id[t]['scenario_id'] in check_families]
assert len(source_ids)==60 and len(check_ids)==30
assert not set(source_ids)&set(check_ids) and not set(source_families)&set(check_families)
def summarize(task_ids):
    data=[by_id[t] for t in task_ids]
    return {'tasks':len(data),'families':len({r['scenario_id'] for r in data}),
        'success':sum(r['status']=='success' for r in data),'failed':sum(r['status']=='failed' for r in data),
        'context_failures':sum(r['status']=='failed' and int(r['context_error_count'])>0 for r in data),
        'non_context_failures':sum(r['status']=='failed' and int(r['context_error_count'])==0 for r in data),
        'difficulty_counts':dict(collections.Counter(r['difficulty'] for r in data))}
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
manifest={'created_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'seed':seed,'python_version':sys.version.split()[0],
 'split_algorithm':'One random.Random(20260928); for difficulty 1,2,3 sort family IDs, shuffle in place, take first 8,8,4 as sources; remaining 4,4,2 as checks.',
 'input_hashes':{'task_results.csv':sha(source/'task_results.csv'),'task_ids.txt':sha(source/'config/task_ids.txt')},
 'source_adapter_sha256':json.loads((source/'manifest.json').read_text())['adapter_sha256'],
 'strata':strata,'source_task_ids':source_ids,'check_task_ids':check_ids,
 'source_summary':summarize(source_ids),'check_summary':summarize(check_ids),
 'purpose':'Incremental repair-source/check split; all 90 tasks were seen during the old adapter SFT.',
 'review_policy':{'seed':seed,'rng_independent_of_split':True,'quota':{'1':1,'2':6,'3':3},'unique_family_first':True,'context_failure_fallback_only':True}}
(stage/'task_split.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
for name,task_ids in [('source',source_ids),('check',check_ids)]:
    (stage/f'{name}_task_ids.txt').write_text(''.join(t+'\n' for t in task_ids))
with (stage/'source_task_inventory.csv').open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(by_id[t] for t in source_ids)
review_rng=random.Random(seed)
non_context=sorted(t for t in source_ids if by_id[t]['status']=='failed' and int(by_id[t]['context_error_count'])==0)
review_rng.shuffle(non_context)
selected=[];seen_families=set();quotas={1:1,2:6,3:3}
for diff in (1,2,3):
    for t in non_context:
        family=by_id[t]['scenario_id']
        if int(by_id[t]['difficulty'])==diff and quotas[diff]>0 and family not in seen_families:
            selected.append(t);seen_families.add(family);quotas[diff]-=1
# Fill any unfulfilled difficulty quota without dropping the maximum-two-per-family rule.
for diff in (1,2,3):
    for t in non_context:
        if t in selected or int(by_id[t]['difficulty'])!=diff or quotas[diff]<=0:continue
        family=by_id[t]['scenario_id']
        if sum(by_id[x]['scenario_id']==family for x in selected)<2:
            selected.append(t);quotas[diff]-=1
for t in non_context:
    if len(selected)>=10:break
    if t in selected:continue
    family=by_id[t]['scenario_id']
    if family not in {by_id[x]['scenario_id'] for x in selected}:
        selected.append(t)
for t in non_context:
    if len(selected)>=10:break
    if t not in selected and sum(by_id[x]['scenario_id']==by_id[t]['scenario_id'] for x in selected)<2:
        selected.append(t)
context=sorted(t for t in source_ids if by_id[t]['status']=='failed' and int(by_id[t]['context_error_count'])>0)
review_rng.shuffle(context)
ordered=selected+[t for t in non_context if t not in selected]+context
with (stage/'review_queue.csv').open('w',newline='') as stream:
    writer=csv.DictWriter(stream,fieldnames=['review_order','task_id','scenario_id','difficulty','batch','context_error','selection_reason','trajectory_dir'])
    writer.writeheader()
    for i,t in enumerate(ordered,1):
        r=by_id[t];ctx=int(r['context_error_count'])>0
        writer.writerow({'review_order':i,'task_id':t,'scenario_id':r['scenario_id'],'difficulty':r['difficulty'],
            'batch':'initial_10' if t in selected else ('context_backup' if ctx else 'non_context_backup'),
            'context_error':ctx,'selection_reason':'固定种子、难度配额、优先不同任务族' if t in selected else ('超限案例单独待查' if ctx else '固定随机顺序备选'),
            'trajectory_dir':r['trajectory_dir']})
print(json.dumps({'source':manifest['source_summary'],'check':manifest['check_summary'],'initial_10':selected,'initial_families':len({by_id[t]['scenario_id'] for t in selected}),'unfilled_initial_quotas':quotas},ensure_ascii=False,indent=2))
