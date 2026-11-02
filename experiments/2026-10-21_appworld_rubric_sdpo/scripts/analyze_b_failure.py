"""Read-only CPU analysis of completed B trajectories; no model or judge calls."""
from common import R,read,write_json,now
import ast
import collections
import csv
import math
import statistics

ROOT=R/'phase_b/runs/mixed'
OUT=R/'phase_b/analysis/failure_diagnosis'


def features(trajectory):
    seen=set();doc_seen=set();last=None;run=0;rows=[]
    for step in trajectory['steps']:
        code=step['code'];calls=[];docs=[];sig='';parse_error=False
        if code.strip():
            try:
                tree=ast.parse(code);sig=ast.dump(tree,include_attributes=False)
                for n in ast.walk(tree):
                    if not isinstance(n,ast.Call):continue
                    name=ast.unparse(n.func)
                    if name.startswith('apis.'):calls.append(name)
                    if name.startswith('apis.api_docs.'):
                        try:
                            args=[ast.literal_eval(a) for a in n.args]
                            kwargs=sorted((k.arg,ast.literal_eval(k.value)) for k in n.keywords)
                            docs.append(repr((name,args,kwargs)))
                        except (ValueError,TypeError):docs.append(None)
            except SyntaxError:parse_error=True;sig=code.strip()
        doc_only=bool(calls) and all(c.startswith('apis.api_docs.') for c in calls)
        repeated=bool(sig and sig in seen)
        repeat_doc=doc_only and bool(docs) and all(x is not None and x in doc_seen for x in docs)
        run=run+1 if sig and sig==last else (1 if sig else 0);last=sig
        business=[c for c in calls if not c.startswith(('apis.api_docs.','apis.supervisor.'))]
        business_non_auth=[c for c in business if not c.endswith(('.login','.logout'))]
        row={'step':step['step'],'docs_only':doc_only,'repeat_code':repeated,'repeat_docs_literal':repeat_doc,
            'business_step':bool(business),'business_non_auth_step':bool(business_non_auth),
            'completion_call':any(c=='apis.supervisor.complete_task' for c in calls),'exact_run_length':run,
            'response_tokens':len(step['response_ids']),'prompt_tokens':len(step['prompt_ids']),
            'sampled_token_nll':-sum(step['old_logprobs'])/len(step['old_logprobs']),
            'traceback':('Traceback' in step['observation']),'syntax_error':parse_error,'apis':calls}
        rows.append(row)
        if sig:seen.add(sig)
        doc_seen.update(x for x in docs if x is not None)
    return rows


def aggregate(rows):
    c={'steps':len(rows)}
    for key in ['docs_only','repeat_code','repeat_docs_literal','business_step','business_non_auth_step','completion_call','traceback']:
        c[key]=sum(x[key] for x in rows);c[key+'_fraction']=c[key]/len(rows) if rows else None
    c['mean_sampled_token_nll']=statistics.mean(x['sampled_token_nll'] for x in rows) if rows else None
    c['mean_response_tokens']=statistics.mean(x['response_tokens'] for x in rows) if rows else None
    return c


def save_csv(name,rows):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    batch_stats=[];train_rows=[];task_stats=[];feedback_samples=[];all_feedback=[]
    for batch in range(1,37):
        folder=ROOT/f'batch_{batch:03d}';data=read(folder/'dataset.json');metrics=read(folder/'checkpoint/metrics.json')
        mapped={(e['trajectory_id'],e['step']):e for e in data['examples']}
        step_losses={(e['trajectory_id'],e['step']):e['loss'] for e in read(folder/'checkpoint/step_metrics.json')}
        rows=[];terminations=collections.Counter()
        for item in read(folder/'collection.json')['trajectories']:
            tr=read(folder/item['path']);fs=features(tr);terminations[tr['termination']]+=1
            judgement=read(folder/'judging'/item['id']/'judgement.json');feedback={f['step_id']:f for f in judgement['feedback']}
            for x in fs:
                e=mapped[(item['id'],x['step'])]
                x.update(batch=batch,epoch=1 if batch<=18 else 2,trajectory_id=item['id'],task_id=e['task_id'],branch=e['branch'],labels=e['labels'],loss=step_losses.get((item['id'],x['step'])))
                if x['step'] in feedback:
                    f=feedback[x['step']];entry={'batch':batch,'trajectory_id':item['id'],'step':x['step'],'labels':e['labels'],
                        'docs_only':x['docs_only'],'repeat_docs_literal':x['repeat_docs_literal'],**f}
                    all_feedback.append(entry)
                    if x['repeat_docs_literal'] and batch in (1,18,25,30,36) and len(feedback_samples)<35:feedback_samples.append(entry)
            rows.extend(fs)
            task_stats.append({'batch':batch,'epoch':1 if batch<=18 else 2,'task_id':tr['job']['task_id'],'steps':len(fs),
                'termination':tr['termination'],'docs_only_steps':sum(x['docs_only'] for x in fs),'max_exact_code_run':max(x['exact_run_length'] for x in fs)})
        train_rows.extend(rows)
        rec={'batch':batch,'epoch':1 if batch<=18 else 2,**aggregate(rows),
            'sft_steps':metrics['counts'].get('sft',0),'sdpo_steps':metrics['counts'].get('sdpo',0),
            'sft_docs_only':sum(x['docs_only'] for x in rows if x['branch']=='sft'),
            'sdpo_docs_only':sum(x['docs_only'] for x in rows if x['branch']=='sdpo'),
            'sdpo_repeat_docs':sum(x['repeat_docs_literal'] for x in rows if x['branch']=='sdpo'),
            'sft_repeat_docs':sum(x['repeat_docs_literal'] for x in rows if x['branch']=='sft'),
            'sft_loss':metrics['sft_loss'],'sdpo_loss':metrics['sdpo_loss'],'sft_grad_norm':metrics['sft_grad_norm'],
            'sdpo_grad_norm':metrics['weighted_sdpo_grad_norm'],'grad_cosine':metrics['branch_grad_cosine'],
            'context_limit_tasks':terminations['context_limit'],'step_limit_tasks':terminations['step_limit'],
            'completion_api_tasks':terminations['completion_api'],'max_task_step_share':max(x['steps'] for x in task_stats if x['batch']==batch)/len(rows)}
        batch_stats.append(rec)
    epochs={}
    for epoch in (1,2):
        rows=[x for x in train_rows if x['epoch']==epoch];bs=[x for x in batch_stats if x['epoch']==epoch]
        epochs[str(epoch)]={'all':aggregate(rows),'by_branch':{b:aggregate([x for x in rows if x['branch']==b]) for b in ['sft','sdpo','mask']},
            'FAIL_rules':dict(collections.Counter(f'R{i+1}' for x in rows for i,l in enumerate(x['labels']) if l=='F')),
            'mean_sft_loss':statistics.mean(x['sft_loss'] for x in bs),'mean_sdpo_loss':statistics.mean(x['sdpo_loss'] for x in bs),
            'mean_sft_grad_norm':statistics.mean(x['sft_grad_norm'] for x in bs),'mean_sdpo_grad_norm':statistics.mean(x['sdpo_grad_norm'] for x in bs),
            'mean_grad_cosine':statistics.mean(x['grad_cosine'] for x in bs),'termination':dict(collections.Counter(x['termination'] for x in task_stats if x['epoch']==epoch))}
    dev={};dev_tasks=[]
    for epoch in (1,2):
        folder=ROOT/f'epoch_{epoch:02d}_dev57';summary=read(folder/'summary.json');rows=[]
        for result in summary['results']:
            tr=read(folder/'trajectories'/(result['task_id']+'.json'));fs=features(tr);rows.extend(fs)
            dev_tasks.append({'epoch':epoch,'task_id':result['task_id'],'success':result['success'],'passes':result['num_passes'],
                'tests':result['num_tests'],'termination':tr['termination'],'steps':len(fs),'docs_only_steps':sum(x['docs_only'] for x in fs),
                'repeat_docs_steps':sum(x['repeat_docs_literal'] for x in fs),'repeat_code_steps':sum(x['repeat_code'] for x in fs),
                'business_non_auth_steps':sum(x['business_non_auth_step'] for x in fs),'max_exact_code_run':max(x['exact_run_length'] for x in fs)})
        this=[x for x in dev_tasks if x['epoch']==epoch]
        dev[str(epoch)]={**aggregate(rows),'successes':summary['successes'],'macro_test_pass_fraction':summary['macro_test_pass_fraction'],
            'terminations':dict(collections.Counter(x['termination'] for x in this)),
            'tasks_with_at_least_5_identical_consecutive_blocks':sum(x['max_exact_code_run']>=5 for x in this),
            'tasks_no_business_non_auth_call':sum(x['business_non_auth_steps']==0 for x in this)}
    result={'generated_at':now(),'methods':{'docs_only':'At least one statically named apis call; every such call is apis.api_docs.*. Unrelated dynamic calls are not resolved.',
        'repeat_code':'Exact AST-normalized code seen earlier in the same trajectory, excluding empty code.',
        'repeat_docs_literal':'All documentation calls have literal arguments and identical API/argument tuples seen earlier; this is an audit indicator, not a new rubric label.',
        'sampled_token_nll':'Mean old sampled-token negative log probability per step; not full vocabulary entropy. Dev temperature zero is not comparable to train sampling.'},
        'training_epochs':epochs,'dev':dev,'feedback_count':len(all_feedback),
        'feedback_repeat_doc_with_R6_F':sum(x['repeat_docs_literal'] and x['labels'][5]=='F' for x in all_feedback),
        'sdpo_losses_by_behavior':{k:{'count':len(a),'mean_loss':statistics.mean(x['loss'] for x in a)} for k,a in {
            'repeated_doc':[x for x in train_rows if x['branch']=='sdpo' and x['repeat_docs_literal']],
            'non_repeated_doc':[x for x in train_rows if x['branch']=='sdpo' and x['docs_only'] and not x['repeat_docs_literal']],
            'not_doc_only':[x for x in train_rows if x['branch']=='sdpo' and not x['docs_only']]}.items()}}
    save_csv('training_by_batch.csv',batch_stats);save_csv('training_by_task.csv',task_stats);save_csv('dev57_behavior_by_task.csv',dev_tasks)
    save_csv('training_step_features.csv',[{k:v for k,v in x.items() if k!='apis'} for x in train_rows])
    write_json(OUT/'summary.json',result);write_json(OUT/'repeated_doc_feedback_samples.json',feedback_samples)
    print(__import__('json').dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
