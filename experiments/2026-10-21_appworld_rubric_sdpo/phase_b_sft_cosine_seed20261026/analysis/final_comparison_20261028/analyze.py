"""CPU-only final audit. Never launches models, evaluators, judges, or training."""
from pathlib import Path
import sys, json, math, ast, csv, copy, statistics
from collections import Counter
from datetime import datetime

B=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(B/'scripts'))
from b_common import R,read,write_json,file_sha,now,check_preparation
from b_report_helpers import behavior,parse_checks,paired,csv_write
from b_retention import validate_committed
from b_learning_rate import learning_rate
OUT=Path(__file__).resolve().parent
BASE=R/'phase_b_sft_seed20261026'


def api_sequence(t):
    rows=[]
    for step in t['steps']:
        code=step.get('code','');calls=[]
        try:
            for node in ast.walk(ast.parse(code)):
                if isinstance(node,ast.Call):
                    fn=ast.unparse(node.func)
                    if fn.startswith('apis.'):
                        safe={kw.arg:kw.value.value for kw in node.keywords if kw.arg in ('app_name','api_name') and isinstance(kw.value,ast.Constant)}
                        calls.append({'api':fn,**safe})
        except SyntaxError:pass
        rows.append({'step':step['step'],'calls':calls,'has_code':bool(code.strip()),'finish_reason':step.get('finish_reason')})
    return rows


def main():
    check_preparation()
    original=read(BASE/'config/run.json');normalized=copy.deepcopy(read(B/'config/run.json'))
    schedule=normalized['training'].pop('lr_schedule');normalized['experiment']=original['experiment']
    for key in ('collection','evaluation'):normalized[key]['tasks']=original[key]['tasks']
    assert normalized==original
    assert file_sha(B/'config/schedule.json')==file_sha(BASE/'config/schedule.json')
    saved={'constant':read(BASE/'analysis/seed_summary.json'),'cosine':read(B/'analysis/lr_summary.json')}
    cases={};dev_rows=[];dev_aggregate=[];batch_rows=[];protocol={};branch_epochs={}
    task_cases={'b119b1f_2','d4e9306_2','6c2c621_1','df61dc5_1','6171bbc_2','396c5a2_1'}
    for branch,root in [('constant',BASE),('cosine',B)]:
        cfg=read(root/'config/run.json');train=cfg['training'];records=[];previous=None
        for n in range(1,55):
            cp=root/f'runs/sft/batch_{n:03d}/checkpoint';done=validate_committed(cp,allow_pruned=True)
            m=read(cp/'metrics.json');assert m['batch']==n and done['optimizer_updates']==m['optimizer_updates']==n
            assert done['identity']['config_sha256']==file_sha(root/'config/run.json')
            if previous:assert done['identity']['parent_policy']['checkpoint_complete_sha256']==previous
            else:assert done['identity']['parent_policy']['kind']=='base_with_zero_initialized_LoRA'
            previous=file_sha(cp/'COMPLETE.json')
            assert math.isclose(m['lr'],learning_rate(n,train),rel_tol=1e-12)
            assert m['sdpo_loss']==m['weighted_sdpo_grad_norm']==0 and not m['teacher_received_gradient']
            for key in ('sft_loss','sft_grad_norm','lr','student_parameter_delta_norm'):assert math.isfinite(m[key])
            assert read(cp.parent/'acceptance.json')['passed']
            row={k:m[k] for k in ('lr','sft_loss','sft_grad_norm','clipped','student_parameter_delta_norm','seconds','peak_allocated_gib')}
            row.update(branch=branch,batch=n,epoch=(n-1)//18+1);records.append(row);batch_rows.append(row)
        full=[n for n in range(1,55) if (root/f'runs/sft/batch_{n:03d}/checkpoint/state.pt').exists()]
        protocol[branch]={'checked_committed_batches':54,'all_lr_match_plan':True,'optimizer_chain_continuous':True,
            'all_sft_loss_and_grad_finite':True,'sdpo_loss_and_grad_zero':True,'clipped_batches':sum(x['clipped'] for x in records),
            'lr_sum':sum(x['lr'] for x in records),'update_norm_path_length':sum(x['student_parameter_delta_norm'] for x in records),
            'training_seconds':sum(x['seconds'] for x in records),'full_checkpoint_batches':full,
            'model_files_bytes':sum(p.stat().st_size for n in full for p in [root/f'runs/sft/batch_{n:03d}/checkpoint/state.pt',root/f'runs/sft/batch_{n:03d}/checkpoint/adapters/student/adapter_model.safetensors']),
            'epoch_updates':{str(e):{'lr_sum':sum(x['lr'] for x in records if x['epoch']==e),'update_norm_path_length':sum(x['student_parameter_delta_norm'] for x in records if x['epoch']==e)} for e in (1,2,3)}}
        branch_epochs[branch]={}
        for e in (1,2,3):
            value=saved[branch]['epochs'][str(e)];folder=root/f'runs/sft/epoch_{e:02d}_dev57';summ=read(folder/'summary.json')
            assert file_sha(folder/'summary.json')==value['source_sha256'] and summ['tasks']==len(summ['results'])==57
            assert summ['seed']==100 and summ['temperature']==0 and summ['student_without_feedback']
            assert summ['policy_identity']['checkpoint_complete_sha256']==file_sha(root/f'runs/sft/batch_{18*e:03d}/checkpoint/COMPLETE.json')
            assert {x['task_id'] for x in summ['results']}==set((root/'config/dev57.txt').read_text().split())
            counts=Counter();terms=Counter();term_success=Counter();no_code=Counter();output_lengths=[];items=[]
            for row in value['results']:
                p=Path(row['trajectory']);assert file_sha(p)==row['trajectory_sha256']
                t=read(p);assert t['job']['policy_identity']==summ['policy_identity'] and t['job']['seed']==100
                for key in ('success','num_tests','num_passes','num_failures'):assert t['official_evaluation'][key]==row[key]
                actual=behavior(t)
                for key,val in actual.items():assert row[key]==val,(branch,e,row['task_id'],key)
                report=Path(row['official_report']);assert file_sha(report)==row['official_report_sha256']
                checks=parse_checks(report);assert checks==row['checks'];assert len(checks)==row['num_tests'] and sum(checks.values())==row['num_passes']
                for key,val in actual.items():
                    if key!='longest_docs_streak':counts[key]+=val
                term=t['termination'];terms[term]+=1;term_success[term]+=int(row['success'])
                extra={'business_api_task':int(actual['business_api_steps']>0),'five_or_more_repeated_docs':int(actual['repeated_docs_steps']>=5)}
                counts.update(extra)
                if term=='no_python_code':
                    last=t['steps'][-1];text=last.get('text','');no_code['tasks']+=1;no_code['empty_text']+=not text.strip();no_code['any_fence']+='```' in text
                    no_code['finish_stop']+=last.get('finish_reason')=='stop';no_code['finish_length']+=last.get('finish_reason')=='length';output_lengths.append(len(last['response_ids']))
                flat={'branch':branch,'epoch':e,'task_id':row['task_id'],'success':row['success'],'passes':row['num_passes'],'tests':row['num_tests'],'termination':term,**actual,**extra}
                dev_rows.append(flat);items.append(row)
                if row['task_id'] in task_cases:
                    cases[f'{branch}_e{e}_{row["task_id"]}']={**flat,'trajectory_path':str(p),'official_report_path':str(report),'api_sequence':api_sequence(t)}
            for key in ('steps','docs_steps','repeated_docs_steps','business_api_steps'):assert counts[key]==value['behavior'][key]
            assert dict(terms)==value['behavior']['terminations']
            record={'branch':branch,'epoch':e,'successes':sum(x['success'] for x in items),'tasks':57,
                'tgc':sum(x['success'] for x in items)/57,'passes':sum(x['num_passes'] for x in items),'tests':sum(x['num_tests'] for x in items),
                'macro':sum(x['num_passes']/x['num_tests'] for x in items)/57,**dict(counts),'terminations':dict(terms),'success_by_termination':dict(term_success),
                'docs_fraction':counts['docs_steps']/counts['steps'],'repeated_docs_fraction':counts['repeated_docs_steps']/counts['steps'],
                'business_fraction':counts['business_api_steps']/counts['steps'],'mean_steps':counts['steps']/57,'no_code_details':dict(no_code),
                'no_code_last_token_range':[min(output_lengths),max(output_lengths)] if output_lengths else None}
            assert record['successes']==summ['successes'] and math.isclose(record['macro'],summ['macro_test_pass_fraction'])
            dev_aggregate.append(record);branch_epochs[branch][str(e)]=record
    cross={};within={}
    for e in (1,2,3):
        p=paired(saved['constant']['epochs'][str(e)],saved['cosine']['epochs'][str(e)])
        cross[str(e)]={k:sum(x[k] for x in p) for k in ['success_gained','success_lost','checks_gained','checks_lost','net_checks']}
    for e in (2,3):
        p=paired(saved['cosine']['epochs'][str(e-1)],saved['cosine']['epochs'][str(e)])
        within[f'{e-1}_to_{e}']={k:sum(x[k] for x in p) for k in ['success_gained','success_lost','checks_gained','checks_lost','net_checks']}
        within[f'{e-1}_to_{e}']['success_lost_tasks']=[x['task_id'] for x in p if x['success_lost']]
        within[f'{e-1}_to_{e}']['success_gained_tasks']=[x['task_id'] for x in p if x['success_gained']]
    result={'audited_at':now(),'cpu_only':True,'training_or_evaluation_launched':False,'checked_dev_trajectories':len(dev_rows),
        'checked_official_reports':len(dev_rows),'protocol':protocol,'epochs':branch_epochs,'cross_schedule_pairs':cross,'cosine_within_pairs':within,
        'training_epochs':{k:v['training_epochs'] for k,v in saved.items()},'same_seed_initial_sampling':read(B/'analysis/first_batch_sampling_comparison.json'),
        'lr_sum_ratio_cosine_to_constant':protocol['cosine']['lr_sum']/protocol['constant']['lr_sum']}
    write_json(OUT/'audit_summary.json',result);write_json(OUT/'case_sequences.json',cases)
    csv_write(OUT/'dev_tasks.csv',dev_rows);csv_write(OUT/'batch_metrics.csv',batch_rows)
    csv_write(OUT/'epoch_comparison.csv',[{k:v for k,v in x.items() if not isinstance(v,(dict,list)) and k!='no_code_last_token_range'} for x in dev_aggregate])
    print(json.dumps({'audited_at':result['audited_at'],'dev_trajectories':len(dev_rows),'official_reports':len(dev_rows),'committed_batches':108,
        'cosine_full_checkpoints':protocol['cosine']['full_checkpoint_batches'],'lr_sum_ratio':result['lr_sum_ratio_cosine_to_constant'],
        'new_behavior_fields':[{k:x[k] for k in ['branch','epoch','business_api_task','five_or_more_repeated_docs','business_fraction','success_by_termination']} for x in dev_aggregate]},ensure_ascii=False))


if __name__=='__main__':main()
