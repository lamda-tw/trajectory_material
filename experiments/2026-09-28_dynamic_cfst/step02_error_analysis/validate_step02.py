#!/usr/bin/env python3
"""Check frozen split, annotation pointers and baseline integrity without inference."""
import collections,csv,datetime,hashlib,json,random,re
from pathlib import Path
from inspect_saved_trajectories import load_task,ROOT
STAGE=Path(__file__).resolve().parent
BASE=STAGE.parent/'step01_train90_student_rollouts'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def readj(p):return json.loads(p.read_text())
def lines(p):return [json.loads(x) for x in p.read_text().splitlines()]
checks=[]
def check(name,condition):
    checks.append({'check':name,'passed':bool(condition)})
split=readj(STAGE/'task_split.json')
rows=list(csv.DictReader((BASE/'task_results.csv').open()))
by_id={r['task_id']:r for r in rows}
ids=(BASE/'config/task_ids.txt').read_text().splitlines()
source=split['source_task_ids'];holdout=split['check_task_ids']
check('60/30 complete unique task partition',len(source)==len(set(source))==60 and len(holdout)==len(set(holdout))==30 and not set(source)&set(holdout) and set(source+holdout)==set(ids))
fam=lambda ts:{by_id[t]['scenario_id'] for t in ts}
check('20/10 disjoint family partition',len(fam(source))==20 and len(fam(holdout))==10 and not fam(source)&fam(holdout))
family_diffs=collections.defaultdict(set)
for r in rows:family_diffs[r['scenario_id']].add(int(r['difficulty']))
check('each family has one difficulty',all(len(v)==1 for v in family_diffs.values()))
rng=random.Random(20260928);expected_source_families=[]
for diff,n in [(1,8),(2,8),(3,4)]:
    fs=sorted(k for k,v in family_diffs.items() if v=={diff});rng.shuffle(fs)
    expected_source_families+=fs[:n]
    saved=split['strata'][diff-1]
    check(f'difficulty {diff} seeded family order',saved['shuffled_family_order']==fs and saved['source_families']==fs[:n] and saved['check_families']==fs[n:])
check('task list order matches original train order',source==[t for t in ids if by_id[t]['scenario_id'] in expected_source_families] and holdout==[t for t in ids if by_id[t]['scenario_id'] not in expected_source_families])
for name,ts,expected in [('source',source,{'1':24,'2':24,'3':12}),('check',holdout,{'1':12,'2':12,'3':6})]:
    check(f'{name} difficulty quota',dict(collections.Counter(by_id[t]['difficulty'] for t in ts))==expected)
    check(f'{name} plain task list',(STAGE/f'{name}_task_ids.txt').read_text().splitlines()==ts)
    records=[by_id[t] for t in ts]
    counts={'tasks':len(ts),'families':len(fam(ts)), 'success':sum(r['status']=='success' for r in records), 'failed':sum(r['status']=='failed' for r in records), 'context_failures':sum(r['status']=='failed' and int(r['context_error_count'])>0 for r in records), 'non_context_failures':sum(r['status']=='failed' and int(r['context_error_count'])==0 for r in records), 'difficulty_counts':expected}
    check(f'{name} result summary',split[f'{name}_summary']==counts)
for name,p in [('task_results.csv',BASE/'task_results.csv'),('task_ids.txt',BASE/'config/task_ids.txt')]:check(f'unchanged split input {name}',split['input_hashes'][name]==sha(p))
check('source inventory exact baseline rows',list(csv.DictReader((STAGE/'source_task_inventory.csv').open()))==[by_id[t] for t in source])
queue=list(csv.DictReader((STAGE/'review_queue.csv').open()))
initial=[r for r in queue if r['batch']=='initial_10']
check('all source failures queued once',len(queue)==31 and {r['task_id'] for r in queue}=={t for t in source if by_id[t]['status']=='failed'})
check('review 10 non-context source failures from 10 families',len(initial)==10 and len({r['scenario_id'] for r in initial})==10 and all(r['task_id'] in source and by_id[r['task_id']]['status']=='failed' and int(by_id[r['task_id']]['context_error_count'])==0 for r in initial))
check('review difficulty quota',dict(collections.Counter(r['difficulty'] for r in initial))=={'1':1,'2':6,'3':3})
non_context=sorted(t for t in source if by_id[t]['status']=='failed' and int(by_id[t]['context_error_count'])==0)
rr=random.Random(20260928);rr.shuffle(non_context)
expected=[];seen=set()
for d,q in [(1,1),(2,6),(3,3)]:
    group=[]
    for t in non_context:
        f=by_id[t]['scenario_id']
        if int(by_id[t]['difficulty'])==d and f not in seen and len(group)<q:group.append(t);seen.add(f)
    expected+=group
check('initial review order matches seed and quotas',[r['task_id'] for r in initial]==expected)
context=sorted(t for t in source if by_id[t]['status']=='failed' and int(by_id[t]['context_error_count'])>0);rr.shuffle(context)
check('remaining review order matches seed',[r['task_id'] for r in queue]==expected+[t for t in non_context if t not in expected]+context)
annotations=lines(STAGE/'review_annotations.jsonl');candidates=lines(STAGE/'repair_candidates.jsonl')
check('annotation order matches frozen initial queue',[r['task_id'] for r in annotations]==expected)
check('3 primary and 2 backup candidates',len(candidates)==5 and [r['candidate_rank'] for r in candidates]==list(range(1,6)) and [r['selection'] for r in candidates]==['primary']*3+['backup']*2)
check('candidate families are distinct sources',len({r['family_id'] for r in candidates})==5 and {r['task_id'] for r in candidates}<=set(expected))
official=readj(ROOT/'evaluations/train.json')['individual']
for r in annotations:
    t=r['task_id'];n=r['replace_action_index_1based'];path,calls,steps=load_task(t)
    check(f'{t}: official counts',not official[t]['success'] and r['baseline_passed_tests']==len(official[t]['passes']) and r['baseline_total_tests']==official[t]['num_tests'])
    fractions=re.findall(r'(\d+)/(\d+)',r['official_failure_summary_zh'])
    check(f'{t}: prose official counts',all((int(a),int(b))==(r['baseline_passed_tests'],r['baseline_total_tests']) for a,b in fractions))
    check(f'{t}: action/request mapping',len(steps)==len(calls) and all((m:=re.search(r'```python\n(.*?)```',c['output']['choices'][0]['message'].get('content') or '',re.S)) and m.group(1).strip()==s['code'].strip() for c,s in zip(calls,steps)))
    check(f'{t}: original action and pointers',r['lm_call_line_1based']==n and r['environment_header_line']==steps[n-1]['line'] and r['original_action']==steps[n-1]['code'] and all(e['environment_header_line']==steps[e['action_index_1based']-1]['line'] and e['environment_io_path']==str(path) for e in r['evidence']))
    check(f'{t}: verbatim code excerpt',any(r['key_code_excerpt'] in s['code'] for s in steps))
    messages=calls[n-1]['input']['messages']
    digest=hashlib.sha256(json.dumps(messages,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    check(f'{t}: prefix digest and budget',r['input_messages_sha256']==digest and r['original_prompt_tokens']==calls[n-1]['output']['usage']['prompt_tokens'] and r['original_prompt_tokens']+3000<=32000 and r['prefix_action_count']==n-1 and r['remaining_student_actions_after_replacement']==50-n)
    check(f'{t}: prefix no server-log contamination',not re.search(r'APIServer pid|EngineCore_DP|Avg prompt throughput',json.dumps(messages)))
    check(f'{t}: all evidence paths exist',all(Path(p).is_file() for p in r['paths'].values()))
    check(f'{t}: evidence hashes',all(sha(Path(r['paths'][k]))==v for k,v in r['source_hashes'].items()))
    check(f'{t}: repair status is unverified',r['prefix_replay_validated'] is False and r['repair_attempted'] is False and r['repair_success'] is None and r['teacher_completion'] is None and r['official_score_after_repair'] is None)
for r in candidates:
    annotation=next(a for a in annotations if a['task_id']==r['task_id'])
    check(f"{r['task_id']}: candidate matches annotation",all(annotation[k]==v for k,v in r.items() if k!='selection'))
# Verify hashes of reviewed original artifacts only; do not inspect holdout trajectories.
baseline_hashes=readj(BASE/'metrics/evidence_sha256.json');nchecked=0
for rel,expected_hash in baseline_hashes.items():
    if any('/tasks/'+t+'/' in rel for t in expected) or rel.endswith('/evaluations/train.json'):
        check(f'baseline unchanged: {rel}',sha(BASE/rel)==expected_hash);nchecked+=1
summary=readj(STAGE/'summary.json')
check('summary label counts',dict(collections.Counter(r['primary_label'] for r in annotations))==summary['tentative_primary_labels'])
check('no inference, teacher, replay or training recorded',all(summary[k]==0 for k in ['model_inference_runs','teacher_calls','environment_replays','training_runs','verified_successful_repairs']))
manifest=readj(STAGE/'manifest.json')
check('manifest frozen file hashes',manifest['split_file_sha256']==sha(STAGE/'task_split.json') and manifest['review_queue_sha256']==sha(STAGE/'review_queue.csv'))
result={'passed':all(c['passed'] for c in checks),'check_count':len(checks),'reviewed_baseline_files_verified':nchecked,'failed_checks':[c['check'] for c in checks if not c['passed']], 'checks':checks,'scope':'Offline data consistency only; does not validate causal diagnoses, prefix replay or repair success.','completed_at_utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
(STAGE/'validation.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
if result['passed']:
    hashes={p.name:sha(p) for p in sorted(STAGE.iterdir()) if p.is_file() and p.name!='artifact_sha256.json'}
    (STAGE/'artifact_sha256.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in result.items() if k!='checks'},ensure_ascii=False,indent=2))
raise SystemExit(0 if result['passed'] else 1)
