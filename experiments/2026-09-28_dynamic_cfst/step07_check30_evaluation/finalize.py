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
    recovery=read(OUT/'runtime_recovery.json')
    ck('recovery_wrapper_frozen',sha(OUT/'resilient_entry.py')==recovery['wrapper_sha256'])
    abort=OUT/'CFST-state/runtime_abort01'
    for rel,h in read(abort/'evidence_sha256.json').items():ck('archived_abort/'+rel,sha(abort/rel)==h)
    prior=jl(abort/'afc0fce_3/logs/lm_calls.jsonl')
    resumed=jl(OUT/'CFST-state'/SUB/'tasks/afc0fce_3/logs/lm_calls.jsonl')
    ck('recovery_exactly_four_original_responses',len(prior)==4 and len(resumed)>=4)
    for i,record in enumerate(prior):
        normalize=lambda x:{k:v for k,v in x.items() if k not in ['base_url','api_key']}
        ck(f'recovery_input_action{i+1}',normalize(record['input'])==normalize(resumed[i]['input']))
        ck(f'recovery_response_action{i+1}',record['output']['choices']==resumed[i]['output']['choices'])
    old_env=(abort/'afc0fce_3/logs/environment_io.md').read_text()
    ck('recovery_first_three_environment_outputs_identical',(OUT/'CFST-state'/SUB/'tasks/afc0fce_3/logs/environment_io.md').read_text().startswith(old_env))
    events=jl(OUT/'CFST-state/logging_recovery_events.jsonl')
    replay=[e for e in events if e['event']=='exact_student_response_replay']
    ck('recovery_four_verified_replays',[e['action_number'] for e in replay]==[1,2,3,4] and all(e['input_verified'] and not e['teacher_used'] for e in replay))
    recovery['validation_passed']=True

    for branch in BRANCHES:
        d=OUT/branch;bm=read(d/'manifest.json');assert bm['exit_code']==0
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
    summary=dict(status='completed',scope='step07 section7.1 check30',baseline_reused=True,baseline_success=17,models=summaries,paired_comparisons=comparisons,selection=selection,teacher_calls=0,new_training=False,dev57_evaluated=False,runtime_recovery=recovery,limitations=['All check30 tasks were seen by the original train90 SFT; they are held out from CFST repair collection only.','Single inference seed and one training seed; differences are exploratory.','Equal supervised target tokens do not equal compute cost or optimizer steps; sequence lengths and update counts differ.','Specialist versus Mixed comparison alone cannot prove that the capability taxonomy is optimal.'],completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
    dump(OUT/'runtime_recovery.json',recovery)
    dump(OUT/'summary.json',summary);dump(OUT/'selection.json',selection)
    dump(OUT/'baseline/summary.json',summaries['baseline']);csvwrite(OUT/'baseline/task_results.csv',baseline)
    dump(OUT/'validation.json',dict(passed=True,checks_total=len(checks),checks_passed=len(checks),checks=checks,complete_new_trajectories=90,baseline_reused_trajectories=30,baseline_evidence_files=180,new_evidence_files=len(evidence)))
    dump(OUT/'evidence_sha256.json',evidence)
    # A concise reading entry; all raw official results remain in the per-branch roots.
    table=['| 原epoch5（复用） | 17/30 | 56.7% | — | — | — |']
    for name in BRANCHES:
        r=comparisons[name];table.append(f"| {name} | {r['success_count']}/30 | {summaries[name]['task_goal_completion']}% | {r['gained_success_count']} | {r['regression_count']} | {r['net_gain']:+d} |")
    lines=['# CFST 第7步：冻结检查30题评测','',f"已完成第7步的检查30题部分：复用原epoch5的30题，三个新分支各从初始环境完成30题，共新增90条轨迹。没有调用教师、生成训练答案或更新模型。",'', '| 模型 | 官方成功 | 成功率 | 新增成功 | 退步 | 净改善 |','| --- | ---: | ---: | ---: | ---: | ---: |',*table,'',f"预设选择结果：**{selection['selected_candidate'] or '没有净改善为正的分支，保留原epoch5模型'}**。" ,'']
    if eligible:lines+=['这是进入Dev57接受检查的候选，还不能作为新的当前学生。Dev57未在本次请求中执行。','']
    else:lines+=['按原计划，本轮没有候选进入Dev57接受检查，不强行选择训练loss最低的模型。','']
    lines+=['## 评测与基线复用','', 'temperature=0、seed=100、32,000上下文、单次最多3,000输出tokens、最多50步、无reasoning parser、同一个simplified ReAct运行器和官方evaluator。State和Action分别占用独立GPU；Action先完成后，该卡运行Mixed。每个分支内部仍单进程、逐题从头运行。','', '原模型复用前已校验源adapter、提示词、agent实现和180个冻结证据文件；它在这30题上为17成功、13失败。所有新轨迹首条模型输入与同题基线逐字一致。新目录内train.txt只含冻结check30，历史train90及来源60题未改。','', '## 逐题变化','']
    for name in BRANCHES:
        r=comparisons[name];lines += [f"- **{name}**：新增成功 `{', '.join(r['gained_task_ids']) or '无'}`；退步 `{', '.join(r['regressed_task_ids']) or '无'}`。"]
    lines+=['','## 难度、任务族与上下文限制','', '| 模型 | 难度1 | 难度2 | 难度3 | 三题全部成功的任务族 | 触发上下文限制的题数 | 模型调用数 |', '| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name in ['baseline']+BRANCHES:
        x=summaries[name];cells=[str(x['difficulty'][str(k)]['success'])+'/'+str(x['difficulty'][str(k)]['total']) for k in [1,2,3]]
        lines.append('| '+('原epoch5（复用）' if name=='baseline' else name)+' | '+' | '.join(cells)+f" | {x['successful_family_count']}/10 | {len(x['context_error_task_ids'])} | {x['model_calls']} |")
    lines+=['','## 如何理解','', '三支都修好了一部分原模型的失败题，但同时损失了更多原本成功的题，因此本轮没有可接受的模型更新。Action与Mixed均为14/30，State为13/30；当前结果也没有显示专项训练在总成功数上超过Mixed。', '', '上下文超限由原模型1题增至State 4题、Action 6题、Mixed 4题，模型调用总数也从588增至748、622、814。这些是后续诊断线索，尚不能据此把退步归因于某一个训练参数或能力类别。', '', '先看新增成功和退步，训练loss不能替代任务结果。相同监督tokens仅控制目标答案曝光量，并不等于相同算力、步数或每样本重复次数。即使某专项分支更好，也只是本次设置下定向训练可能有价值的初步证据，不能单独证明分类正确。检查30题以前参加过原LoRA的SFT，不属于未见任务泛化评测。','', '## 产物','', '- `task_comparison.csv`：30题×四模型的成功矩阵。','- `family_comparison.csv`：10个任务族的变化。','- `summary.json` / `selection.json`：指标和预设规则的候选选择。','- `baseline_reuse_validation.json`：基线复用证据。','- 每个分支的 `trajectory_index.jsonl`、`task_results.csv`、成功/失败/新增成功/退步清单及 `experiments/outputs/.../tasks/`：完整逐步交互、环境记录、官方评分。',f"- `validation.json`：{len(checks)}项完整性和实际请求协议核验全部通过。",'- `startup_attempt01/`：首次在题目运行前因隔离缓存缺少AppWorld测试资源而退出的记录。', '- `RUNTIME_RECOVERY.md`：State的afc0fce_3触发日志序列化异常；原始中断证据完整保留。仅修复日志保存，精确重放原学生前4个响应并核对输入和已保存环境返回，从第5步续跑，不更换动作、不重置50步预算、不按结果重试。','']
    (OUT/'README.md').write_text('\n'.join(lines))
    m.update(status='completed',validated_at_utc=summary['completed_at_utc'],selected_candidate=selection['selected_candidate'],branches={b:read(OUT/b/'manifest.json') for b in BRANCHES},runtime_recovery=recovery);dump(OUT/'manifest.json',m)
    outputs=['manifest.json','summary.json','selection.json','validation.json','evidence_sha256.json','baseline_reuse_validation.json','README.md','task_comparison.csv','family_comparison.csv','check_task_ids.txt','task_split.json','prepare.py','run.py','finalize.py','resilient_entry.py','resume_gpu0.py','runtime_recovery.json','RUNTIME_RECOVERY.md','recovery_smoke_validation.json','scheduler_handoff.json','run_mixed_gpu1.py']
    dump(OUT/'artifact_sha256.json',{name:sha(OUT/name) for name in outputs})
    print(json.dumps(dict(models={n:s['success_count'] for n,s in summaries.items()},comparisons=comparisons,selection=selection,checks=len(checks)),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
