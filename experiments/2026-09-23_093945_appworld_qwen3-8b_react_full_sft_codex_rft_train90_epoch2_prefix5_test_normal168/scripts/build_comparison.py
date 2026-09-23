#!/usr/bin/env python3
"""Audit fixed epoch2 evaluation against unchanged epoch5 and LoRA references."""
import collections, csv, json, os, subprocess, sys
from datetime import datetime, timezone
from pathlib import Path
E=Path(__file__).resolve().parent.parent
W=E.parent.parent
sys.path.insert(0,str(E/'scripts_snapshot'))
from analyze_appworld_matched_rollouts import analyze, OUTPUT, read_json
from build_appworld_full_sft_aligned_dev_report import load_score_snapshot,load_task_ids,audit_task_status,audit_run,sha256
from build_full_sft_test168_comparison import paired_analysis

def write(path,value): path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
def csvwrite(path,rows):
    with path.open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def pair(a,b,ids,la,lb):
    raw=paired_analysis(a,b,ids)
    result={'a':la,'b':lb,'both_success':raw['both_success'],'a_only_success':raw['full_sft_only_success'],
        'b_only_success':raw['lora_only_success'],'both_failed':raw['both_failed'],
        'a_regressions_by_terminal':raw['regressions_by_terminal'],'scenario_bootstrap':raw['scenario_bootstrap']}
    result['scenario_outcomes']=[{'scenario_id':r['scenario_id'],'task_ids':r['task_ids'],'a_success':r['full_sft_success_count'],
        'b_success':r['lora_success_count'],'delta':r['delta']} for r in raw['scenario_outcomes']]
    c=raw['both_without_context_error']
    result['both_without_context_error']={'task_ids':c['task_ids'],'task_count':c['task_count'],'a_success':c['full_sft_success'],'b_success':c['lora_success']}
    result['a_gains_by_b_terminal']=dict(collections.Counter(b['per_task'][t]['terminal_group'] for t in result['a_only_success']))
    return result

def plot(summary):
    os.environ['MPLCONFIGDIR']=str(E/'cache/matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    colors={'epoch2':'#2878b5','epoch5':'#d66140','lora':'#47966e'}
    labels={'epoch2':'Full SFT: 2 epochs','epoch5':'Full SFT: 5 epochs','lora':'LoRA: 5 epochs'}
    fig,axes=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
    x=np.arange(4); width=.26
    for i,key in enumerate(['epoch2','epoch5','lora']):
        item=summary['models'][key]
        values=[item['aggregate']['task_goal_completion']]+[item['difficulty'][str(k)]['tgc'] for k in [1,2,3]]
        bars=axes[0].bar(x+(i-1)*width,values,width,color=colors[key],label=labels[key])
        axes[0].bar_label(bars,fmt='%.1f',padding=3,fontsize=8)
    axes[0].set(xticks=x,xticklabels=['All 168','Level 1 (57)','Level 2 (48)','Level 3 (63)'],ylabel='Task goal completion (%)',ylim=(0,max(75,15+max(v['difficulty'][str(d)]['tgc'] for v in summary['models'].values() for d in [1,2,3]))),title='Same test_normal protocol')
    axes[0].legend(frameon=False,fontsize=8);axes[0].grid(axis='y',alpha=.2);axes[0].set_axisbelow(True)
    p=summary['epoch2_vs_epoch5'];counts=[len(p[k]) for k in ['both_success','a_only_success','b_only_success','both_failed']]
    bars=axes[1].bar(['Both\nsuccess','Epoch 2\nonly','Epoch 5\nonly','Both\nfail'],counts,color=['#47966e',colors['epoch2'],colors['epoch5'],'#9ba1a9'])
    axes[1].bar_label(bars,padding=3)
    axes[1].set(ylabel='Number of tasks',ylim=(0,max(counts)*1.2+3),title='Two vs five epochs: paired outcomes')
    axes[1].grid(axis='y',alpha=.2);axes[1].set_axisbelow(True)
    for ext in ['png','pdf']:fig.savefig(E/('metrics/performance_comparison.'+ext),dpi=180)
    plt.close(fig)

def main():
    manifest=read_json(E/'manifest.json');T=Path(manifest['training_experiment'])
    assert (E/'logs/run_exit_code.txt').read_text().strip()=='0'
    server_audit=read_json(E/'config/model_server_protocol_audit.json');assert server_audit['status']=='PASS' and server_audit['compared_fields']==13
    ids=load_task_ids(E/'data/datasets/test_normal.txt',168)
    assert sha256(E/'data/datasets/test_normal.txt')==manifest['dataset_sha256']
    roots={'epoch2':E,'epoch5':Path(manifest['reference_epoch5_test_experiment']),'lora':Path(manifest['reference_lora_test_experiment'])}
    labels={'epoch2':'全参数 SFT 第2轮','epoch5':'全参数 SFT 第5轮','lora':'LoRA 第5轮'}
    served={'epoch2':manifest['served_model_name'],'epoch5':'appworld-qwen3-8b-codex-rft-train90-epoch5','lora':'appworld-codex-rft-train90-epoch5'}
    scores={key:load_score_snapshot(labels[key],root,ids,OUTPUT,'test_normal') for key,root in roots.items()}
    assert scores['epoch5']['success_count']==28 and scores['lora']['success_count']==51
    for score in scores.values():
        assert score['aggregate']['task_goal_completion']==round(100*score['success_count']/168,1)
        assert score['aggregate']['scenario_goal_completion']==round(100*score['successful_scenario_count']/56,1)
        assert score['evaluator_tests']['total']==1077
    status=audit_task_status(E/'task_status.jsonl',ids,scores['epoch2']['individual'])
    assert status['strictly_one_row_per_task'] and status['latest_rows_cover_dataset']
    for key in ['malformed_line_numbers','evaluation_error_task_ids','status_success_mismatch_ids','test_count_mismatch_ids']:assert not status[key]
    rows=[json.loads(x) for x in (E/'task_status.jsonl').read_text().splitlines() if x.strip()]
    assert [x['completed_index'] for x in rows]==list(range(1,169))
    assert [x['task_id'] for x in rows]==ids,'Task execution order differs from fixed dataset order'
    assert all(x['status'] in ('success','failed') for x in rows)
    assert all((E/'experiments/outputs'/OUTPUT/'tasks'/t/'misc/finished').is_file() for t in ids)
    run=audit_run(E,status);assert run['final_exit_code']==0 and not run['anomalies'],run
    analyses={key:analyze(root,ids,scores[key]['individual'],served[key]) for key,root in roots.items()}
    for key,data in analyses.items():
        assert not data['request_parameter_mismatches'],(key,data['request_parameter_mismatches'])
        c=data['totals'];assert c['lm_requests']==c['model_responses']+c.get('error_responses',0)
        assert c.get('other',0)==0,'Non-context model error requires investigation'
        for task in ids:
            a,b=data['per_task'][task],analyses['epoch2']['per_task'][task]
            assert a['first_prompt_sha256']==b['first_prompt_sha256'] and a['first_prompt_tokens']==b['first_prompt_tokens'] and a['first_prompt_tokens']>0,(key,task)
            assert a['fixed_request_parameter_hashes']==b['fixed_request_parameter_hashes'],(key,task)
        relative=Path('config/agent_configs')/(OUTPUT+'.jsonnet')
        assert (roots[key]/relative).read_bytes()==(E/relative).read_bytes(),key
        write(E/f'metrics/{key}_rollout_analysis.json',data)
    inventory=read_json(T/'metrics/model_inventory.json')['artifacts/model']
    assert all((T/'artifacts/model'/name).stat().st_size==data['bytes'] for name,data in inventory['files'].items())
    from action_mix import compare as compare_action_mix
    action_mix=compare_action_mix(W/'data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/train.jsonl',roots,ids,OUTPUT)
    for key in roots:assert action_mix['distributions'][key]['normal_action_count']==analyses[key]['totals']['model_responses']
    write(E/'metrics/action_mix.json',action_mix)
    p=pair(analyses['epoch2'],analyses['epoch5'],ids,'epoch2','epoch5')
    pl=pair(analyses['epoch2'],analyses['lora'],ids,'epoch2','lora')
    taskrows=[]
    for task in ids:
        d={'task_id':task,'difficulty':analyses['epoch2']['per_task'][task]['difficulty']}
        for key in roots:
            r=analyses[key]['per_task'][task]
            for field in ['success','passed_tests','failed_tests','num_tests','terminal_group','answer_failure_kind']:d[key+'_'+field]=r[field]
            for field in ['context_error','python_error','max_50_requests','repeated_identical_code']:d[key+'_'+field]=r['signals'][field]
            for field in ['lm_requests','api_calls','total_tokens','repeated_identical_code_actions']:d[key+'_'+field]=r['counts'].get(field,0)
        d['epoch2_minus_epoch5']=int(d['epoch2_success'])-int(d['epoch5_success'])
        taskrows.append(d)
    csvwrite(E/'task_comparison.csv',taskrows)
    scen=[]
    for row in p['scenario_outcomes']:
        family=row['scenario_id'];members=row['task_ids']
        scen.append({'scenario_id':family,'task_ids':';'.join(members),'epoch2_success':row['a_success'],'epoch5_success':row['b_success'],
            'lora_success':sum(analyses['lora']['per_task'][t]['success'] for t in members),'epoch2_minus_epoch5':row['delta']})
    csvwrite(E/'scenario_comparison.csv',scen)
    for score in scores.values():score.pop('individual')
    training=read_json(T/'metrics/prefix_replay_audit.json');assert training['status']=='PASS'
    summary={'created_at_utc':datetime.now(timezone.utc).isoformat(),'task_count':168,'scenario_count':56,'models':scores,'action_mix':action_mix,
        'epoch2_vs_epoch5':p,'epoch2_vs_lora':pl,'training_prefix_audit':training,'task_status_audit':status,'run_audit':run,
        'protocol_audit':{'initial_messages_equal_tasks':168,'initial_token_count_equal_tasks':168,'fixed_request_parameters_equal':True,'generated_config_equal':True,'server_settings_equal_fields':13,'server_initialization_seed':0,'request_seed':100},
        'diagnostics':{key:{k:data[k] for k in ['totals','all_tasks','failed_tasks','successful_tasks','terminal_groups','answer_failure_kinds','failure_categories','exception_types']} for key,data in analyses.items()}}
    write(E/'summary.json',summary);plot(summary)
    print(json.dumps({'status':'ANALYZED','success':{k:v['success_count'] for k,v in scores.items()},'epoch2_vs_epoch5':{k:len(p[k]) for k in ['both_success','a_only_success','b_only_success','both_failed']},'bootstrap':p['scenario_bootstrap']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
