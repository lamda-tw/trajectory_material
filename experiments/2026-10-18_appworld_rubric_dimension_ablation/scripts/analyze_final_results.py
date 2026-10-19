"""Read-only CPU analysis of frozen training, selections and official evaluator artifacts."""
import csv
import hashlib
import json
import math
import random
import re
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path
from experiment_utils import R, read, dump, sha, jsonl, set_sha, now

O = R / 'analysis_three_seeds'
SEEDS = [20261015, 20261016, 20261017]
ARMS = [f'drop_r{i}' for i in [1, 2, 3, 4, 5, 6, 8]]
TYPES = {
    'target_set_mapping': '完整名单与对应关系', 'local_content_identity': '具体内容与对象',
    'model_scope': '改动的数据类型', 'record_counts': '新增、修改、删除的数量',
    'selection_constraints': '操作对象是否符合条件', 'preservation': '不该改的内容是否保留',
    'answer_null': '按要求提交空答案', 'answer_value': '实际答案是否正确'}


def root(seed):
    return R / 'gpu0_seed_20261017' if seed == 20261017 else R


def save_csv(name, rows):
    with (O / name).open('w', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def parse_report(text):
    chunks = defaultdict(list)
    for match in re.finditer(r'>> (Passed|Failed) Requirement\n(.*?)(?=>> (?:Passed|Failed) Requirement|\Z)', text, re.S):
        description = match[2].split('```')[0]
        description = '\n'.join(l for l in description.splitlines() if not l.startswith('─') and l.strip() != 'None')
        description = ' '.join(description.split())
        chunks[description].append((match[1] == 'Passed', match[2]))
    parsed = {}
    duplicate = 'assert user_id to message mapping from notifications match private_data.venmo_user_id_to_notification_messages'
    for description, matches in chunks.items():
        assert description
        if len(matches) == 1:
            parsed[description] = matches[0][0]
            continue
        assert description == duplicate and len(matches) == 2
        identities = {'venmo_user_id_to_notification_messages', 'venmo_user_id_to_notification_payment_request_ids'}
        identified, passed_without_code = {}, []
        for passed, snippet in matches:
            if passed:
                passed_without_code.append(passed)
            else:
                code = snippet.split('```python', 1)[1]
                names = re.findall(r'(venmo_user_id_to_notification_(?:messages|payment_request_ids)) =', code)
                assert len(names) == 1 and names[0] not in identified
                identified[names[0]] = False
        remaining = identities - identified.keys()
        assert len(remaining) == len(passed_without_code)
        identified.update({name: True for name in remaining})
        for name, passed in identified.items():
            parsed[description + ' [code: ' + name + ']'] = passed
    return parsed


def evaluation():
    mapping = {(x['family'], x['requirement']): x['category'] for x in csv.DictReader((O / 'evaluator_type_mapping.csv').open())}
    assert len(mapping) == 97
    data_root = Path(read(R / 'config/evaluation.json')['paths']['appworld_data'])
    dev = (R / 'config/dev.txt').read_text().split()
    answers = {t: {'is_null': read(data_root / f'tasks/{t}/ground_truth/answer.json') is None,
                   'sha256': sha(data_root / f'tasks/{t}/ground_truth/answer.json')} for t in dev}
    dump(O / 'evaluator_answer_types.json', answers)
    task_rows, checks, behaviors, audit = [], [], [], []
    schemas, inits = {}, {}
    for seed in SEEDS:
        rr = root(seed)
        for arm in ARMS:
            folder = rr / f'evaluation/{arm}/seed_{seed}/epoch_01'
            summary = read(folder / 'SUMMARY.json')
            train = rr / f'training/{arm}/seed_{seed}'
            done = read(train / 'epoch_01.json')
            init = read(train / 'INITIALIZATION.json')
            assert done['updates'] == 679 and done['samples'] == 1358 and not done['probe']
            assert init['fresh_base_no_old_adapter'] and not init['probe']
            assert init['seed'] == seed
            if seed in inits:
                assert inits[seed] == init['initial_adapter_tensor_sha256']
            inits[seed] = init['initial_adapter_tensor_sha256']
            for name, expected in done['adapter_files'].items():
                assert sha(train / 'epoch_01_adapter' / name) == expected
            assert summary['policy_id'] == done['adapter_files']['adapter_model.safetensors']
            assert summary['tasks'] == len(summary['results']) == 57
            assert {x['task_id'] for x in summary['results']} == set(dev)
            run = f'{arm}__seed_{seed}__epoch_01'
            for row in summary['results']:
                task = row['task_id']; family = task.rsplit('_', 1)[0]
                source = Path(row['source']); raw = source.read_bytes()
                assert hashlib.sha256(raw).hexdigest() == row['sha256']
                trace = json.loads(raw); official = trace['official_evaluation']
                report = rr / f'runtime/{run}/experiments/outputs/{run}__dev__{task}/tasks/{task}/evaluation/report.md'
                parsed = parse_report(report.read_text())
                assert len(parsed) == row['tests'] == official['num_tests']
                assert sum(parsed.values()) == row['passes'] == official['num_passes']
                assert all(parsed.values()) == row['success'] == official['success']
                if task in schemas:
                    assert set(parsed) == schemas[task]
                schemas[task] = set(parsed)
                task_rows.append(dict(arm=arm, seed=seed, task_id=task, family=family,
                    passes=row['passes'], tests=row['tests'], fraction=row['passes']/row['tests'], success=row['success']))
                for desc, passed in sorted(parsed.items()):
                    category = mapping[family, desc]
                    if category == 'answer':
                        category = 'answer_null' if answers[task]['is_null'] else 'answer_value'
                    checks.append(dict(arm=arm, seed=seed, task_id=task, family=family, requirement=desc,
                        category=category, passed=int(passed), source=str(report.relative_to(R))))
                codes = [s['code'].strip() for s in trace['steps'] if s['code'].strip()]
                behaviors.append(dict(arm=arm, seed=seed, task_id=task, family=family,
                    steps=len(trace['steps']), errors=sum(s['observation'].startswith('Execution failed.') for s in trace['steps']),
                    doc_steps=sum('apis.api_docs.' in s['code'] for s in trace['steps']),
                    repeated_code_occurrences=len(codes)-len(set(codes)),
                    no_code_steps=sum(not s['code'].strip() for s in trace['steps']),
                    generated_tokens=sum(len(s['response_ids']) for s in trace['steps']), termination=trace['termination']))
            current = [x for x in task_rows if x['arm'] == arm and x['seed'] == seed]
            assert abs(st.mean(x['fraction'] for x in current) - summary['mean_test_pass_fraction']) < 1e-12
            audit.append({'arm': arm, 'seed': seed, 'physical_gpu': 0 if seed == 20261017 else 1,
                          'adapter_sha256': summary['policy_id'], 'reports': 57, 'all_checks_consistent': True})
            print('validated evaluator', arm, seed, flush=True)
    assert len(task_rows) == 1197 and len(checks) == 6111
    assert set(mapping) == {(c['family'], c['requirement']) for c in checks}
    save_csv('evaluator_checks.csv', checks); save_csv('evaluator_tasks.csv', task_rows)
    save_csv('behavior_by_task.csv', behaviors)
    lookup = {(c['arm'],c['seed'],c['task_id'],c['requirement']): c['passed'] for c in checks}
    tasks = {(t['arm'],t['seed'],t['task_id']):t for t in task_rows}
    pairs = []
    for arm in ARMS:
        if arm == 'drop_r5': continue
        for seed in SEEDS:
            for task in dev:
                a,b = tasks[arm,seed,task], tasks['drop_r5',seed,task]
                gains = sum(lookup[arm,seed,task,d] > lookup['drop_r5',seed,task,d] for d in schemas[task])
                losses = sum(lookup[arm,seed,task,d] < lookup['drop_r5',seed,task,d] for d in schemas[task])
                pairs.append(dict(arm=arm,seed=seed,task_id=task,family=a['family'],gains=gains,losses=losses,
                    net=gains-losses,macro_delta=a['fraction']-b['fraction'],success_delta=int(a['success'])-int(b['success']),
                    both_failed=not a['success'] and not b['success']))
    save_csv('evaluator_pairs.csv', pairs)
    types = []
    for cat in TYPES:
        for arm in ARMS:
            selected = [x for x in checks if x['category'] == cat and x['arm'] == arm]
            base = lambda x: lookup['drop_r5',x['seed'],x['task_id'],x['requirement']]
            types.append(dict(category=cat,name=TYPES[cat],arm=arm,checks=len(selected),
                passes=sum(x['passed'] for x in selected),baseline_passes=sum(base(x) for x in selected),
                gains=sum(x['passed']>base(x) for x in selected),losses=sum(x['passed']<base(x) for x in selected),
                net=sum(x['passed']-base(x) for x in selected),
                seed_net=[sum(x['passed']-base(x) for x in selected if x['seed']==s) for s in SEEDS]))
    save_csv('evaluator_type_results.csv', types)
    families,requirements = [], []
    for family in sorted({t['family'] for t in task_rows}):
        f = {'family': family}
        for arm in ARMS:
            xx=[t for t in task_rows if t['family']==family and t['arm']==arm]
            f[arm+'_macro']=st.mean(t['fraction'] for t in xx)
            f[arm+'_successes']=sum(t['success'] for t in xx)
            f[arm+'_passes']=sum(t['passes'] for t in xx)
        families.append(f)
    for family,description in sorted(mapping):
        q={'family':family,'requirement':description,'category':mapping[family,description]}
        for arm in ARMS:
            xx=[x for x in checks if x['arm']==arm and x['family']==family and x['requirement']==description]
            q[arm+'_passes']=sum(x['passed'] for x in xx);q[arm+'_tests']=len(xx)
        requirements.append(q)
    save_csv('evaluator_families.csv',families);save_csv('evaluator_requirements.csv',requirements)
    groups={}
    for arm in ARMS:
        xx=[x for x in task_rows if x['arm']==arm];pp=[p for p in pairs if p['arm']==arm];bb=[x for x in behaviors if x['arm']==arm]
        failed=[p for p in pp if p['both_failed']]
        groups[arm]={'macro':st.mean(x['fraction'] for x in xx),'micro':sum(x['passes'] for x in xx)/sum(x['tests'] for x in xx),
            'passes':sum(x['passes'] for x in xx),'tests':sum(x['tests'] for x in xx),'successes':sum(x['success'] for x in xx),
            'seed_macro':[st.mean(x['fraction'] for x in xx if x['seed']==s) for s in SEEDS],
            'seed_successes':[sum(x['success'] for x in xx if x['seed']==s) for s in SEEDS],
            'zero':sum(x['passes']==0 for x in xx),'partial':sum(0<x['passes']<x['tests'] for x in xx),
            'gains':sum(p['gains'] for p in pp),'losses':sum(p['losses'] for p in pp),
            'both_failed_pairs':len(failed),'both_failed_net':sum(p['net'] for p in failed),
            'both_failed_macro_delta':st.mean(p['macro_delta'] for p in failed) if failed else 0,
            'mean_dev_steps':st.mean(x['steps'] for x in bb),
            'execution_error_rate':sum(x['errors'] for x in bb)/sum(x['steps'] for x in bb),
            'doc_step_rate':sum(x['doc_steps'] for x in bb)/sum(x['steps'] for x in bb),
            'repeated_code_rate':sum(x['repeated_code_occurrences'] for x in bb)/sum(x['steps'] for x in bb),
            'terminations':dict(Counter(x['termination'] for x in bb))}
        if pp:
            family_deltas=[st.mean(p['macro_delta'] for p in pp if p['family']==f) for f in sorted({p['family'] for p in pp})]
            rng=random.Random(20261022)
            samples=sorted(st.mean(rng.choices(family_deltas,k=len(family_deltas))) for _ in range(5000))
            groups[arm]['macro_family_bootstrap_95']=[samples[125],samples[4874]]
            groups[arm]['families_up_equal_down']=[sum(v>1e-12 for v in family_deltas),sum(abs(v)<=1e-12 for v in family_deltas),sum(v < -1e-12 for v in family_deltas)]
            groups[arm]['without_each_seed_delta']={str(s):st.mean(p['macro_delta'] for p in pp if p['seed']!=s) for s in SEEDS}
            # Descriptive leave-one-family-out sensitivity; no post-hoc significance tests.
            groups[arm]['leave_one_family_out_macro_range']=[min(st.mean([v for j,v in enumerate(family_deltas) if j!=i]) for i in range(19)),max(st.mean([v for j,v in enumerate(family_deltas) if j!=i]) for i in range(19))]
    dump(O/'evaluator_summary.json',{'at_beijing':now(),'validated_reports':len(task_rows),'total_check_results':len(checks),
        'distinct_task_checks':sum(map(len,schemas.values())),'requirement_families':len(mapping),'groups':groups,'audit':audit,
        'interval_scope':'Descriptive family bootstrap conditional on these three training seeds; no independent-check or confirmatory significance claim.'})
    return groups


def selections():
    inv=jsonl(R/'data/step_inventory.jsonl');index={x['id']:x for x in inv};assert len(index)==11254
    baseline={x['id'] for x in inv if x['P']>=3 and x['F']==0};assert len(baseline)==1710
    pools={f'drop_r{i+1}':{x['id'] for x in inv if sum(v=='P' for j,v in enumerate(x['labels']) if j!=i)>=3 and all(v!='F' for j,v in enumerate(x['labels']) if j!=i)} for i in range(8)}
    assert baseline==pools['drop_r5']==pools['drop_r7']
    source_rows=defaultdict(list)
    for x in inv:source_rows[x['source']].append(x)
    hashes=read(R/'references/source_hashes.json');features={}
    for path,xx in source_rows.items():
        raw=Path(path).read_bytes();assert hashlib.sha256(raw).hexdigest()==hashes[path];trace=json.loads(raw)
        for x in xx:
            step=trace['steps'][x['step']-1];assert step['step']==x['step'];code=step['code']
            features[x['id']]={'doc': 'apis.api_docs.' in code,'complete': 'apis.supervisor.complete_task(' in code,
                'error':step['observation'].startswith('Execution failed.'),'previous_error':x['step']>1 and trace['steps'][x['step']-2]['observation'].startswith('Execution failed.')}
    pool_rows=[]
    for arm,pool in pools.items():
        removed=baseline-pool;added=pool-baseline
        pool_rows.append({'arm':arm,'candidate_count':len(pool),'retained':len(pool&baseline),'added':len(added),'removed':len(removed),
            'candidate_id_set_sha256':set_sha(pool), 'removed_pass_combinations':dict(Counter(''.join(str(i+1) for i,v in enumerate(index[k]['labels']) if v=='P') for k in removed)),
            'removed_doc_steps':sum(features[k]['doc'] for k in removed),'added_doc_steps':sum(features[k]['doc'] for k in added),
            'added_R6_P':sum(index[k]['labels'][5]=='P' for k in added),
            'added_previous_error':sum(features[k]['previous_error'] for k in added),
            'added_current_execution_error':sum(features[k]['error'] for k in added)})
    dump(O/'selection_pool_changes.json',pool_rows)
    selected={};exposure=[];stats=[]
    for seed in SEEDS:
        rr=root(seed)
        for arm in ARMS:
            rows=jsonl(rr/f'data/{arm}/seed_{seed}/selection.jsonl');ids={x['id'] for x in rows}
            assert len(rows)==len(ids)==1358 and ids<=pools[arm]
            assert all(x==index[x['id']] for x in rows)
            selected[arm,seed]=ids
            for i in range(8):
                c=Counter(x['labels'][i] for x in rows)
                exposure.append(dict(arm=arm,seed=seed,rubric=f'R{i+1}',**{lab:c[lab] for lab in 'PFUN'},
                    P_doc=sum(x['labels'][i]=='P' and features[x['id']]['doc'] for x in rows),
                    P_non_doc=sum(x['labels'][i]=='P' and not features[x['id']]['doc'] for x in rows)))
            task_dist=Counter(x['task_id'] for x in rows)
            stats.append({'arm':arm,'seed':seed,'selected_steps':len(rows),'new_F_steps':len(ids-baseline),
                'target_tokens':sum(x['response_tokens'] for x in rows),'prompt_tokens':sum(x['prompt_tokens'] for x in rows),
                'doc_steps':sum(features[k]['doc'] for k in ids),'complete_steps':sum(features[k]['complete'] for k in ids),
                'execution_error_steps':sum(features[k]['error'] for k in ids),
                'previous_error_steps':sum(features[k]['previous_error'] for k in ids),
                'task_count':len(task_dist),'trajectory_count':len({x['trajectory_id'] for x in rows}),
                'task_entropy':-sum((v/1358)*math.log(v/1358) for v in task_dist.values())})
        for name in ['selection.jsonl','orders.json']:
            assert sha(rr/f'data/drop_r5/seed_{seed}/{name}')==sha(rr/f'data/drop_r7/seed_{seed}/{name}')
        alias=read(rr/f'aliases/drop_r7/seed_{seed}.json')
        for rel,h in alias['source_files'].items():assert sha(rr/rel)==h
    for row in stats:
        ids=selected[row['arm'],row['seed']];ref=selected['drop_r5',row['seed']]
        row['overlap_with_same_seed_baseline']=len(ids&ref)
        row['new_selected_vs_same_seed_baseline']=len(ids-ref)
    save_csv('selection_by_seed.csv',stats);save_csv('rubric_exposure_by_seed.csv',exposure)
    overlap={arm:{f'{a}_{b}':len(selected[arm,a]&selected[arm,b]) for i,a in enumerate(SEEDS) for b in SEEDS[i+1:]} for arm in ARMS}
    dump(O/'selection_cross_seed_overlap.json',overlap)
    dump(O/'baseline_equivalence.json',{'full_rule_steps':1710,'full_rule_id_set_sha256':set_sha(baseline),
        'drop_r5_identical':True,'drop_r7_identical':True,'three_seed_alias_artifacts_verified':True,
        'interpretation':'DropR5 already provides three valid 1358-step full-rule SFT samples; a new arm-specific RNG draw would be another replicate, not a different score predicate.'})
    print('PASS: full-rule equivalence, source hashes, score-only pools, selections and aliases',flush=True)
    return stats


def main():
    groups=evaluation();selection=selections()
    for arm,g in groups.items():
        ss=[x for x in selection if x['arm']==arm]
        print(arm,json.dumps({'successes':g['seed_successes'],'seed_macro':g['seed_macro'],
            'macro':g['macro'],'micro':g['micro'],'gains':g['gains'],'losses':g['losses'],
            'mean_doc_steps':st.mean(x['doc_steps'] for x in ss)},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
