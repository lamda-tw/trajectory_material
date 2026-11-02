"""Live five-epoch report: saved artifacts only, no inference/evaluator reruns."""
from b_common import *
from collections import Counter
import ast,csv,math,re


def csv_write(path,rows):
    path.parent.mkdir(parents=True,exist_ok=True)
    if not rows:return
    with path.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def behavior(t):
    c=Counter(steps=len(t['steps']));seen=set();last=None;streak=0;longest=0
    for s in t['steps']:
        code=(s.get('code') or '').strip()
        try:
            tree=ast.parse(code);sig=ast.dump(tree,include_attributes=False)
            calls=[ast.unparse(n.func) for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func).startswith('apis.')]
        except SyntaxError:sig=code;calls=[]
        docs=bool(calls) and all(n.startswith('apis.api_docs.') for n in calls)
        business=any(not n.startswith(('apis.api_docs.','apis.supervisor.')) and n.rsplit('.',1)[-1] not in ('login','logout') for n in calls)
        c['docs_steps']+=docs;c['repeated_docs_steps']+=docs and sig in seen
        c['business_api_steps']+=business;c['response_tokens']+=len(s['response_ids'])
        if code:seen.add(sig)
        streak=streak+1 if docs and sig==last else int(docs);longest=max(longest,streak);last=sig if docs else None
    c['longest_docs_streak']=longest
    return dict(c)


def parse_checks(path):
    checks={};duplicates=[]
    duplicate_label='assert user_id to message mapping from notifications match private_data.venmo_user_id_to_notification_messages'
    identities={'venmo_user_id_to_notification_messages','venmo_user_id_to_notification_payment_request_ids'}
    for m in re.finditer(r'>> (Passed|Failed) Requirement\n(.*?)(?=>> (?:Passed|Failed) Requirement|\Z)',path.read_text(),re.S):
        desc=m[2].split('```')[0];desc=' '.join(l.strip() for l in desc.splitlines() if not l.startswith('─') and l.strip()!='None');desc=' '.join(desc.split())
        passed=m[1]=='Passed'
        if desc==duplicate_label:
            found=re.findall(r'(venmo_user_id_to_notification_(?:messages|payment_request_ids)) =',m[2])
            duplicates.append((found[0] if len(found)==1 else None,passed))
            continue
        assert desc and desc not in checks,(path,desc)
        checks[desc]=passed
    if duplicates:
        assert len(duplicates)==2,(path,duplicates)
        identified={name:passed for name,passed in duplicates if name is not None}
        unresolved=[passed for name,passed in duplicates if name is None]
        remaining=identities-set(identified)
        assert len(remaining)==len(unresolved) and (not unresolved or len(set(unresolved))==1),(path,duplicates)
        for name in remaining:identified[name]=unresolved[0]
        for name,passed in identified.items():checks[duplicate_label+' [code: '+name+']']=passed
    return checks


def epoch_record(epoch):
    folder=run_dir('sft')/f'epoch_{epoch:02d}_dev57'
    path=folder/'summary.json'
    if not path.exists():return None
    cached=B/'analysis/epoch_cache'/f'epoch_{epoch:02d}.json';h=file_sha(path)
    if cached.exists():
        value=read(cached);assert value['source_sha256']==h;return value
    summ=read(path);assert summ['tasks']==len(summ['results'])==57
    assert {x['task_id'] for x in summ['results']}==set((B/'config/dev57.txt').read_text().split())
    counts=Counter();terms=Counter();rows=[]
    for row in summ['results']:
        p=folder/'trajectories'/(row['task_id']+'.json');assert file_sha(p)==row['trajectory_sha256']
        t=read(p);assert t['official_evaluation']['success']==row['success'];c=behavior(t)
        counts.update({k:v for k,v in c.items() if k!='longest_docs_streak'});terms[t['termination']]+=1
        report=Path(t['job']['runtime'])/'experiments/outputs'/t['job']['episode_id']/'tasks'/row['task_id']/'evaluation/report.md'
        checks=parse_checks(report);assert len(checks)==row['num_tests'] and sum(checks.values())==row['num_passes']
        rows.append({**row,**c,'checks':checks,'trajectory':str(p),'official_report':str(report),'official_report_sha256':file_sha(report)})
    n=counts['steps'];behavior_summary={**counts,'docs_fraction':counts['docs_steps']/n,'repeated_docs_fraction':counts['repeated_docs_steps']/n,
        'long_loop_tasks':sum(x['longest_docs_streak']>=5 for x in rows),'context_limit_tasks':terms['context_limit'],
        'no_python_code_tasks':terms['no_python_code'],'business_api_tasks':sum(x['business_api_steps']>0 for x in rows),'terminations':dict(terms)}
    value={'source_sha256':h,'epoch':epoch,'summary_path':str(path),'successes':summ['successes'],'task_goal_completion':summ['task_goal_completion'],
        'macro_test_pass_fraction':summ['macro_test_pass_fraction'],'passes':sum(x['num_passes'] for x in rows),'tests':sum(x['num_tests'] for x in rows),
        'mean_steps':n/57,'behavior':behavior_summary,'results':rows}
    write_json(cached,value);return value


def paired(a,b):
    left={x['task_id']:x for x in a['results']};right={x['task_id']:x for x in b['results']};rows=[]
    assert left.keys()==right.keys()
    for task in sorted(left):
        x,y=left[task],right[task];assert x['checks'].keys()==y['checks'].keys()
        gain=sum(y['checks'][k]>x['checks'][k] for k in x['checks']);loss=sum(y['checks'][k]<x['checks'][k] for k in x['checks'])
        rows.append({'from_epoch':a['epoch'],'to_epoch':b['epoch'],'task_id':task,'success_gained':int(y['success'] and not x['success']),
            'success_lost':int(x['success'] and not y['success']),'checks_gained':gain,'checks_lost':loss,'net_checks':gain-loss,
            'before_longest_docs':x['longest_docs_streak'],'after_longest_docs':y['longest_docs_streak']})
    return rows


