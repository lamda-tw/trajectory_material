"""Audit official check30 evaluations and create paired branch comparisons."""
from pathlib import Path
import collections,csv,datetime,hashlib,json,math,re
OUT=Path(__file__).resolve().parent
EXP=OUT.parent
SUB=Path('experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train')
BRANCHES=['CFST-state','CFST-Action','CFST-Mixed']
def read(p):return json.loads(Path(p).read_text())
def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def csvwrite(p,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def listwrite(p,ids):p.write_text(''.join(t+'\n' for t in ids))
def aggregate(rows):
    families=collections.defaultdict(list);diff=collections.defaultdict(lambda:dict(total=0,success=0))
    for r in rows:
        families[r['scenario_id']].append(r['official_success'])
        diff[str(r['difficulty'])]['total']+=1;diff[str(r['difficulty'])]['success']+=int(r['official_success'])
    n=sum(r['official_success'] for r in rows);sgc=sum(all(v) for v in families.values())
    return dict(task_count=len(rows),success_count=n,failure_count=len(rows)-n,task_goal_completion=round(100*n/len(rows),1),successful_family_count=sgc,family_count=len(families),scenario_goal_completion=round(100*sgc/len(families),1),difficulty=dict(diff),context_error_task_ids=[r['task_id'] for r in rows if r['context_error_count']],model_calls=sum(r['lm_calls'] for r in rows),input_tokens=sum(r['input_tokens'] for r in rows),output_tokens=sum(r['output_tokens'] for r in rows))
def main():
    m=read(OUT/'manifest.json');assert m['status'] in ['awaiting_validation','completed']
    ids=(OUT/'check_task_ids.txt').read_text().splitlines();assert len(ids)==len(set(ids))==30
    assert sha(OUT/'check_task_ids.txt')==m['check_ids_sha256']
    assert ids==read(EXP/'step02_error_analysis/task_split.json')['check_task_ids']
    source=set(read(EXP/'step02_error_analysis/task_split.json')['source_task_ids'])
    assert not source&set(ids)
    baseline=jl(OUT/'baseline/trajectory_index.jsonl');base_by={r['task_id']:r for r in baseline}
    assert [r['task_id'] for r in baseline]==ids
    baseline_v=read(OUT/'baseline_reuse_validation.json');assert baseline_v['passed']
    for p,h in baseline_v['evidence_sha256'].items():assert sha(p)==h
    all_rows={'baseline':baseline};summaries={'baseline':aggregate(baseline)};evidence={};checks=[]
    def ck(name,condition,detail=None):
        checks.append(dict(name=name,passed=bool(condition),detail=detail))
        if not condition:raise AssertionError((name,detail))
    ck('baseline_success_17',summaries['baseline']['success_count']==17)
    old=EXP/'step01_train90_student_rollouts'
    for name,h in read(old/'config/source_hashes.json').items():
        path=Path(name) if name.startswith('/') else old/name
        ck('original_source_unchanged/'+name,sha(path)==h)
    baseline_manifest=read(old/'manifest.json')
    ck('original_adapter_still_unchanged',sha(Path(baseline_manifest['adapter'])/'adapter_model.safetensors')==baseline_manifest['adapter_sha256'])
    guard=read(OUT/'old_results_guard.json')
    for path,expected_hash in guard['files_sha256'].items():
        ck('prior_artifact_unchanged/'+path,sha(Path(path))==expected_hash)
    ck('training_stage_one_epoch',m['training_stage']=='step06b_lora_one_epoch')
    trained=read(EXP/'step06b_lora_one_epoch/summary.json')
    ck('one_epoch_training_validated',trained['status']=='SUCCESS' and read(EXP/'step06b_lora_one_epoch/validation.json')['status']=='PASS')
    ck('logging_wrapper_frozen',sha(OUT/'resilient_entry.py')==m['logging_wrapper_sha256'])
    runtime_handling={'logging_only_ellipsis_fix':True,'prefix_replay':False,'teacher_calls':0,'events':{}}

    for branch in BRANCHES:
        d=OUT/branch;bm=read(d/'manifest.json');assert bm['exit_code']==0
        ck(branch+'_adapter_is_correct_1epoch',bm['adapter']==trained['branches'][branch]['adapter_dir'] and bm['adapter_sha256']==trained['branches'][branch]['adapter_model_sha256'])
        ck(branch+'_no_prefix_replay',bm['prefix_replay'] is False)
        events_path=d/'logging_recovery_events.jsonl'
        events=jl(events_path) if events_path.exists() else []
        ck(branch+'_logging_events_only',all(e['event']=='log_only_ellipsis_encoding' for e in events),events)
        runtime_handling['events'][branch]=events
        server_log=(d/SUB/'model_server.log').read_text(errors='replace')
        ck(branch+'_actual_server_32000_window','max_seq_len=32000' in server_log)
        ck(branch+'_actual_server_adapter',bm['adapter'] in server_log)
        ck(branch+'_actual_server_no_reasoning_parser',"reasoning_parser='deepseek_r1'" not in server_log)
        ck(branch+'_split_exact',(d/'data/datasets/train.txt').read_text().splitlines()==ids)
        ck(branch+'_adapter_unchanged',sha(Path(bm['adapter'])/'adapter_model.safetensors')==bm['adapter_sha256'])
        ck(branch+'_runner_identical',sha(d/'scripts_snapshot/appworld_run_isolated_lora_config.py')==m['baseline_runner_sha256'])
        ck(branch+'_config_identical',sha(d/'config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train.jsonnet')==m['baseline_config_sha256'])
        official_path=d/SUB/'evaluations/train.json';official=read(official_path)
        statuses=jl(d/'task_status.jsonl');status_by={r['task_id']:r for r in statuses}
        ck(branch+'_coverage',set(official['individual'])==set(ids)==set(status_by) and len(statuses)==30)
        ck(branch+'_task_order',[r['task_id'] for r in statuses]==ids)
        rows=[]
        for tid in ids:
            task=d/SUB/'tasks'/tid;logs=task/'logs';live=status_by[tid];item=official['individual'][tid]
            required=['logs/lm_calls.jsonl','logs/environment_io.md','logs/api_calls.jsonl','logs/logger.jsonl','misc/finished','evaluation/report.md']
            for name in required:
                p=task/name;ck(f'{branch}/{tid}/{name}',p.is_file())
                evidence[str(p.relative_to(OUT))]=sha(p)
            calls=jl(logs/'lm_calls.jsonl');env=(logs/'environment_io.md').read_text()
            ck(f'{branch}/{tid}/completion',bool(calls) and bool(env) and live['status'] in ['success','failed'])
            ck(f'{branch}/{tid}/official_consistent',(live['status']=='success')==item['success'] and live['passed_tests']==len(item['passes']) and live['failed_tests']==len(item['failures']))
            ck(f'{branch}/{tid}/initial_history_matches_baseline',calls[0]['input']['messages']==jl(base_by[tid]['lm_calls_path'])[0]['input']['messages'])
            ck(f'{branch}/{tid}/max_steps',len(calls)<=50,len(calls))
            inp=out=ctx=err=empty=0;other_errors=[]
            for i,call in enumerate(calls):
                req=call['input'];response=call['output']
                ck(f'{branch}/{tid}/request{i+1}',all(req.get(k)==v for k,v in dict(model=bm['served_adapter_name'],temperature=0,seed=100,max_completion_tokens=3000).items()))
                usage=response.get('usage') or {};inp+=int(usage.get('prompt_tokens') or 0);out+=int(usage.get('completion_tokens') or 0)
                error=response.get('error')
                if error:
                    err+=1
                    if any(w in str(error).lower() for w in ['maximum context length','context length','max_tokens','max_completion_tokens','maximum model length','longer than']):ctx+=1
                    else:other_errors.append(str(error))
                msg=((response.get('choices') or [{}])[0].get('message') or {})
                empty+=not bool((msg.get('content') or '').strip())
            ck(f'{branch}/{tid}/no_infrastructure_request_errors',not other_errors,other_errors)
            row=dict(task_id=tid,scenario_id=tid.rsplit('_',1)[0],status='success' if item['success'] else 'failed',official_success=item['success'],difficulty=item['difficulty'],lm_calls=len(calls),executed_steps=len(re.findall(r'^### Environment Interaction \d+',env,re.M)),api_calls=len(jl(logs/'api_calls.jsonl')),passed_tests=len(item['passes']),failed_tests=len(item['failures']),num_tests=item['num_tests'],elapsed_seconds=live['elapsed_seconds'],input_tokens=inp,output_tokens=out,context_error_count=ctx,request_error_count=err,empty_response_count=empty,has_python_execution_error='execution failed. traceback' in env.lower(),finished=True,termination_category='official_success' if item['success'] else ('context_window_limit' if ctx else ('step_limit' if len(calls)==50 else 'official_tests_failed')),trajectory_dir=str(task),lm_calls_path=str(logs/'lm_calls.jsonl'),environment_io_path=str(logs/'environment_io.md'),official_report_path=str(task/'evaluation/report.md'))
            rows.append(row)
        s=aggregate(rows)
        ck(branch+'_official_aggregate',s['task_goal_completion']==official['aggregate']['task_goal_completion'] and s['scenario_goal_completion']==official['aggregate']['scenario_goal_completion'])
        s['duration_seconds']=(datetime.datetime.fromisoformat(bm['run_finished_at'])-datetime.datetime.fromisoformat(bm['run_started_at'])).total_seconds()
        s['adapter_sha256']=bm['adapter_sha256'];s['teacher_calls']=0
        csvwrite(d/'task_results.csv',rows)
        (d/'trajectory_index.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        listwrite(d/'success_task_ids.txt',[r['task_id'] for r in rows if r['official_success']]);listwrite(d/'failed_task_ids.txt',[r['task_id'] for r in rows if not r['official_success']])
        dump(d/'summary.json',s);evidence[str(official_path.relative_to(OUT))]=sha(official_path)
        all_rows[branch]=rows;summaries[branch]=s
        bm['status']='completed';dump(d/'manifest.json',bm)
    comparisons={};lookup={name:{r['task_id']:r for r in rows} for name,rows in all_rows.items()}
    matrix=[]
    for tid in ids:
        row=dict(task_id=tid,family_id=tid.rsplit('_',1)[0],difficulty=base_by[tid]['difficulty'])
        for name in ['baseline']+BRANCHES:row[name]=lookup[name][tid]['official_success']
        matrix.append(row)
    csvwrite(OUT/'task_comparison.csv',matrix)
    family_rows=[]
    for fam in dict.fromkeys(t.rsplit('_',1)[0] for t in ids):
        tids=[t for t in ids if t.rsplit('_',1)[0]==fam];r=dict(family_id=fam,difficulty=base_by[tids[0]]['difficulty'],task_count=3)
        for name in ['baseline']+BRANCHES:r[name]=sum(lookup[name][t]['official_success'] for t in tids)
        family_rows.append(r)
    csvwrite(OUT/'family_comparison.csv',family_rows)
    for name in BRANCHES:
        gain=[t for t in ids if not base_by[t]['official_success'] and lookup[name][t]['official_success']]
        regress=[t for t in ids if base_by[t]['official_success'] and not lookup[name][t]['official_success']]
        comparisons[name]=dict(success_count=summaries[name]['success_count'],gained_success_count=len(gain),regression_count=len(regress),net_gain=len(gain)-len(regress),gained_task_ids=gain,regressed_task_ids=regress,retained_success_count=17-len(regress),unchanged_failure_count=13-len(gain))
        ck(name+'_net_gain_consistent',len(gain)-len(regress)==summaries[name]['success_count']-17)
        listwrite(OUT/name/'gained_task_ids.txt',gain);listwrite(OUT/name/'regressed_task_ids.txt',regress)
    order=m['selection_rule']['tie_order']
    rank=sorted(BRANCHES,key=lambda name:(-comparisons[name]['net_gain'],comparisons[name]['regression_count'],order.index(name)))
    eligible=[name for name in rank if comparisons[name]['net_gain']>0]
    selection=dict(rule=m['selection_rule'],ranked_branches=rank,eligible_branches=eligible,selected_candidate=eligible[0] if eligible else None,decision='candidate_for_dev57' if eligible else 'retain_original_model_no_positive_check30_gain',dev57_run=False,new_current_student=None,note='Check30 selects a candidate only. Acceptance requires Dev57; no branch is accepted or retrained here.')
    previous=EXP/'step07_check30_evaluation'
    previous_manifest=read(previous/'manifest.json')
    ck('same_check30_as_previous',previous_manifest['check_ids']==ids and previous_manifest['protocol']==m['protocol'])
    vs_previous={};wide=[]
    old_lookup={name:{r['task_id']:r for r in jl(previous/name/'trajectory_index.jsonl')} for name in BRANCHES}
    for name in BRANCHES:
        old_rows=old_lookup[name]
        ck(name+'_previous_full_coverage',set(old_rows)==set(ids))
        old_success=sum(r['official_success'] for r in old_rows.values())
        gained=[t for t in ids if not old_rows[t]['official_success'] and lookup[name][t]['official_success']]
        lost=[t for t in ids if old_rows[t]['official_success'] and not lookup[name][t]['official_success']]
        vs_previous[name]=dict(previous_success_count=old_success,one_epoch_success_count=summaries[name]['success_count'],gained_task_ids=gained,regressed_task_ids=lost,net_change=len(gained)-len(lost))
        ck(name+'_previous_delta_consistent',len(gained)-len(lost)==summaries[name]['success_count']-old_success)
    for row in matrix:
        r=dict(row)
        for name in BRANCHES:r[name+'_previous']=old_lookup[name][row['task_id']]['official_success']
        wide.append(r)
    csvwrite(OUT/'task_comparison_with_previous.csv',wide)
    csvwrite(OUT/'comparison_vs_previous.csv',[dict(branch=b,**v) for b,v in vs_previous.items()])
    summary=dict(status='completed',scope='step07b check30 on step06b 1epoch adapters',training_stage='step06b_lora_one_epoch',baseline_reused=True,baseline_success=17,models=summaries,paired_comparisons=comparisons,comparison_vs_previous=vs_previous,selection=selection,teacher_calls=0,new_training=False,dev57_evaluated=False,runtime_handling=runtime_handling,prior_protected_files_unchanged=len(guard['files_sha256']),limitations=['Check30 tasks were seen in original train90 SFT; held out only from CFST repair answers.','This one-epoch revision follows the previous check30 results, so this is development evidence, not a new independent test.','Single inference seed and one training seed.','State/Action/Mixed each trained one epoch with unequal sample counts, target tokens, and optimizer steps; this is not an equal-budget taxonomy ablation.'],completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    dump(OUT/'summary.json',summary);dump(OUT/'selection.json',selection)
    dump(OUT/'baseline/summary.json',summaries['baseline']);csvwrite(OUT/'baseline/task_results.csv',baseline)
    listwrite(OUT/'baseline/success_task_ids.txt',[r['task_id'] for r in baseline if r['official_success']]);listwrite(OUT/'baseline/failed_task_ids.txt',[r['task_id'] for r in baseline if not r['official_success']])
    dump(OUT/'validation.json',dict(passed=True,checks_total=len(checks),checks_passed=len(checks),checks=checks,complete_new_trajectories=90,baseline_reused_trajectories=30,baseline_evidence_files=180,new_evidence_files=len(evidence)))
    dump(OUT/'evidence_sha256.json',evidence)
    table=['| 原epoch5（复用） | 17/30 | 56.7% | — | — | — | — |']
    for name in BRANCHES:
        r=comparisons[name];oldr=vs_previous[name]
        table.append(f"| {name}-1epoch | {r['success_count']}/30 | {summaries[name]['task_goal_completion']}% | {r['gained_success_count']} | {r['regression_count']} | {r['net_gain']:+d} | {oldr['previous_success_count']}/30 → {r['success_count']}/30（{oldr['net_change']:+d}） |")
    lines=['# CFST第7b步：1epoch模型在冻结检查30题上的评测','',
        '**已完成三个新分支各30题，共90条完整新轨迹及官方评分；原epoch5的17/30经核验复用。旧模型、旧评测结果均保留。** 本步未调用教师、生成训练答案、训练模型或运行Dev57。','',
        '| 模型 | 官方成功 | 成功率 | 新增成功 | 退步 | 相对原epoch5净改善 | 旧版到1epoch |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- |',*table,'',
        '新增成功和退步均相对原epoch5；最右列对比此前约8,000监督tokens版本。', '',
        f"预设选择结果：**{selection['selected_candidate']+'-1epoch进入候选' if eligible else '没有净改善为正的分支，保留原epoch5'}**。"]
    if eligible:lines+=['候选只通过了检查30题的选择门槛，尚未替代当前学生；是否接受更新仍需之后单独执行Dev57。本次不启动Dev57。']
    else:lines+=['按既有规则不进入Dev57，不根据训练loss或旧版比较强行选择一个分支。']
    lines+=['','## 协议和数据边界','',
        '三支来自第6b步：State 12条/6次更新、Action 8条/4次更新、Mixed 20条/10次更新，各完整训练一轮。所有任务从初始环境开始，没有注入Codex动作或重放旧学生响应。', '',
        'temperature=0、seed=100、最大32,000上下文、每次最多3,000输出tokens、每题最多50步、无reasoning parser、相同simplified ReAct运行器和官方evaluator。两个独立GPU并行跑State和Action，先空闲的卡接着跑Mixed；分支内部逐题单进程运行。', '',
        '来源60题与检查30题及其任务族划分保持冻结。每支隔离目录的train.txt仅包含同一30题；原数据文件保持不变。原epoch5的180个证据文件、模型权重、提示词和运行器已重新核验；新轨迹的第一次模型输入逐字匹配同题基线。', '',
        '沿用旧第7步已经验证的日志序列化修复：只在保存API日志时将Python Ellipsis写成类型标记，不改变动作、环境返回或评分。本次未启用任何前缀重放；实际触发记录见summary.json。首次后台监督程序在任何分支启动之前退出，相关状态保存在startup_supervisor_abort；未产生模型调用或任务重试。', '',
        '## 逐题变化（相对原epoch5）','']
    for name in BRANCHES:
        r=comparisons[name]
        lines.append(f"- **{name}-1epoch**：新增成功 `{', '.join(r['gained_task_ids']) or '无'}`；退步 `{', '.join(r['regressed_task_ids']) or '无'}`。")
    lines+=['','## 难度、任务族与运行成本','', '| 模型 | 难度1 | 难度2 | 难度3 | 全部成功任务族 | 上下文超限题数 | 模型调用数 | 输入tokens | 输出tokens |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in ['baseline']+BRANCHES:
        x=summaries[name];cells=[str(x['difficulty'][str(k)]['success'])+'/'+str(x['difficulty'][str(k)]['total']) for k in [1,2,3]]
        lines.append('| '+('原epoch5（复用）' if name=='baseline' else name+'-1epoch')+' | '+' | '.join(cells)+f" | {x['successful_family_count']}/10 | {len(x['context_error_task_ids'])} | {x['model_calls']} | {x['input_tokens']:,} | {x['output_tokens']:,} |")
    lines+=['','## 如何解释','']
    for name in BRANCHES:
        r=comparisons[name];v=vs_previous[name]
        lines.append(f"- {name}-1epoch：相对旧版成功数变化{v['net_change']:+d}题；相对原epoch5新增成功{r['gained_success_count']}题、退步{r['regression_count']}题，净变化{r['net_gain']:+d}题。")
    lines+=['','先区分“比旧版更好”和“超过原epoch5”两件事。最终选择按后者的新增成功减退步执行；所有分支及全部任务均报告，不挑选有利结果。', '',
        '这轮保持评测协议，只把训练改为每条样本学一次。样本数、监督tokens和更新次数因此不同，专项组与Mixed的差异不能单独证明能力分类合理。检查30题曾参与最初train90 SFT，且本次方案是在看到旧检查结果后提出；这里只能作为开发实验，不能当作未见任务泛化或单独锁定退步原因的证据。', '',
        '## 产物','',
        '- task_comparison.csv：原epoch5与三个1epoch分支的逐题结果。',
        '- task_comparison_with_previous.csv / comparison_vs_previous.csv：加入旧版分支的逐题及汇总对照。',
        '- family_comparison.csv：10个任务族结果。',
        '- summary.json / selection.json：完整指标与冻结规则的候选判断。',
        '- 各分支trajectory_index.jsonl、task_results.csv及成功/失败/新增成功/退步清单：逐题索引；experiments/outputs/.../tasks/保留完整交互和官方评分。',
        f"- validation.json：{len(checks)}项核验全部通过，覆盖90条新轨迹、实际请求协议及{len(guard['files_sha256'])}个既有保护文件未变化。",
        '- baseline_reuse_validation.json / evidence_sha256.json / artifact_sha256.json：基线复用与归档证据。','']
    (OUT/'README.md').write_text('\n'.join(lines)+'\n')
    m.update(status='completed',validated_at_utc=summary['completed_at_utc'],selected_candidate=selection['selected_candidate'],branches={b:read(OUT/b/'manifest.json') for b in BRANCHES},runtime_handling=runtime_handling);dump(OUT/'manifest.json',m)
    outputs=['manifest.json','summary.json','selection.json','validation.json','evidence_sha256.json','baseline_reuse_validation.json','README.md','task_comparison.csv','task_comparison_with_previous.csv','comparison_vs_previous.csv','family_comparison.csv','check_task_ids.txt','task_split.json','prepare.py','run.py','finalize.py','resilient_entry.py','old_results_guard.json']
    dump(OUT/'artifact_sha256.json',{name:sha(OUT/name) for name in outputs})
    print(json.dumps(dict(models={n:s['success_count'] for n,s in summaries.items()},comparisons=comparisons,previous_comparisons=vs_previous,selection=selection,checks=len(checks)),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
