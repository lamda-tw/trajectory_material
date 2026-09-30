"""Audit Dev57, export every evaluator requirement, and apply frozen acceptance rule."""
from pathlib import Path
import collections,csv,datetime,hashlib,json,re
OUT=Path(__file__).resolve().parent
EXP=OUT.parent
ROOT=EXP.parents[1]
BASELINE=ROOT/'experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57'
SUB=Path('experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev')
CANDIDATE='CFST-Action'
CHECKS=[]
EVIDENCE={}
def read(p):return json.loads(p.read_text())
def jl(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def csvwrite(p,rows):
 with p.open('w',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
def jlwrite(p,rows):p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
def listwrite(p,ids):p.write_text(''.join(x+'\n' for x in ids))
def ck(name,passed,detail=None):
 CHECKS.append(dict(name=name,passed=bool(passed),detail=detail))
 if not passed:raise AssertionError((name,detail))
def aggregate(rows):
 families=collections.defaultdict(list);difficulty=collections.defaultdict(lambda:dict(total=0,success=0))
 for r in rows:
  families[r['scenario_id']].append(r['official_success']);difficulty[str(r['difficulty'])]['total']+=1;difficulty[str(r['difficulty'])]['success']+=int(r['official_success'])
 n=sum(r['official_success'] for r in rows);complete=sum(all(v) for v in families.values())
 passed=sum(r['passed_tests'] for r in rows);total=sum(r['num_tests'] for r in rows)
 return dict(task_count=len(rows),success_count=n,failure_count=len(rows)-n,task_goal_completion=round(100*n/len(rows),1),task_goal_completion_exact=100*n/len(rows),successful_family_count=complete,family_count=len(families),scenario_goal_completion=round(100*complete/len(families),1),difficulty=dict(difficulty),evaluator_tests=dict(passed=passed,failed=total-passed,total=total,overall_pass_percentage=100*passed/total,macro_task_pass_percentage=sum(r['test_pass_percentage'] for r in rows)/len(rows)),context_error_task_ids=[r['task_id'] for r in rows if r['context_error_count']],model_calls=sum(r['lm_calls'] for r in rows),input_tokens=sum(r['input_tokens'] for r in rows),output_tokens=sum(r['output_tokens'] for r in rows))
def audit_model(name,d,ids,manifest,baseline_first_inputs=None):
 official_path=d/SUB/'evaluations/dev.json';official=read(official_path)
 statuses=jl(d/'task_status.jsonl');status_by={r['task_id']:r for r in statuses}
 ck(name+'/full_coverage',len(statuses)==57 and [r['task_id'] for r in statuses]==ids and set(official['individual'])==set(ids))
 rows=[];first_inputs={};assertions=[]
 for tid in ids:
  task=d/SUB/'tasks'/tid;logs=task/'logs';live=status_by[tid];item=official['individual'][tid]
  for rel in ['logs/lm_calls.jsonl','logs/environment_io.md','logs/api_calls.jsonl','logs/logger.jsonl','misc/finished','evaluation/report.md']:
   p=task/rel;ck(name+'/'+tid+'/'+rel,p.is_file());EVIDENCE[str(p)]=sha(p)
  calls=jl(logs/'lm_calls.jsonl');env=(logs/'environment_io.md').read_text()
  ck(name+'/'+tid+'/nonempty_trajectory',0<len(calls)<=50 and bool(env))
  ck(name+'/'+tid+'/official_consistency',live['status'] in ['success','failed'] and (live['status']=='success')==item['success'] and live['passed_tests']==len(item['passes']) and live['failed_tests']==len(item['failures']) and live['num_tests']==item['num_tests'])
  passed=len(item['passes']);failed=len(item['failures']);total=item['num_tests']
  ck(name+'/'+tid+'/evaluator_test_count',total>0 and passed+failed==total)
  pct=100*passed/total
  ck(name+'/'+tid+'/live_evaluator_percentage',abs(live['test_pass_percentage']-pct)<=0.11,dict(live=live['test_pass_percentage'],recomputed=pct))
  first_inputs[tid]=calls[0]['input']['messages']
  if baseline_first_inputs is not None:ck(name+'/'+tid+'/initial_input_matches_baseline',first_inputs[tid]==baseline_first_inputs[tid])
  inp=out=ctx=err=empty=0;other=[]
  for i,call in enumerate(calls):
   req=call['input'];response=call['output']
   ck(f'{name}/{tid}/request_{i+1}',all(req.get(k)==v for k,v in dict(model=manifest['served_adapter_name'],temperature=0,seed=100,max_completion_tokens=3000).items()))
   usage=response.get('usage') or {};inp+=int(usage.get('prompt_tokens') or 0);out+=int(usage.get('completion_tokens') or 0)
   error=response.get('error')
   if error:
    err+=1
    if any(w in str(error).lower() for w in ['maximum context length','context length','max_tokens','max_completion_tokens','maximum model length','longer than']):ctx+=1
    else:other.append(str(error))
   msg=((response.get('choices') or [{}])[0].get('message') or {});empty+=not bool((msg.get('content') or '').strip())
  ck(name+'/'+tid+'/no_request_infrastructure_errors',not other,other)
  failed_requirements=[x['requirement'] for x in item['failures']]
  instruction=read(d/'data/tasks'/tid/'specs.json')['instruction']
  row=dict(task_id=tid,scenario_id=tid.rsplit('_',1)[0],instruction=instruction,difficulty=item['difficulty'],status=live['status'],official_success=item['success'],passed_tests=passed,failed_tests=failed,num_tests=total,test_pass_percentage=pct,reported_test_pass_percentage=live['test_pass_percentage'],lm_calls=len(calls),executed_steps=len(re.findall(r'^### Environment Interaction \d+',env,re.M)),api_calls=len(jl(logs/'api_calls.jsonl')),elapsed_seconds=live['elapsed_seconds'],input_tokens=inp,output_tokens=out,context_error_count=ctx,request_error_count=err,empty_response_count=empty,has_python_execution_error='execution failed. traceback' in env.lower(),termination_category='official_success' if item['success'] else ('context_window_limit' if ctx else ('step_limit' if len(calls)==50 else 'official_tests_failed')),failed_requirements_json=json.dumps(failed_requirements,ensure_ascii=False),trajectory_dir=str(task),lm_calls_path=str(logs/'lm_calls.jsonl'),official_report_path=str(task/'evaluation/report.md'))
  rows.append(row)
  for state,key in [('PASS','passes'),('FAIL','failures')]:
   for test in item[key]:assertions.append(dict(model=name,task_id=tid,result=state,requirement=test['requirement'],label=test.get('label'),trace=test.get('trace')))
 ck(name+'/official_aggregate',all(aggregate(rows)[key]==official['aggregate'][key] for key in ['task_goal_completion','scenario_goal_completion']))
 EVIDENCE[str(official_path)]=sha(official_path)
 return rows,official,first_inputs,assertions

def write_details(ids,baseline,candidate,base_official,candidate_official):
 b={r['task_id']:r for r in baseline};c={r['task_id']:r for r in candidate}
 headers=['# Dev57：57题逐题evaluator明细','', '每题通过百分比＝该题官方通过测试条件数÷该题实际报告的测试条件总数。任务成功/失败直接使用官方success，不能用部分通过百分比替代。下面原样列出候选模型的所有测试条件及通过/失败状态，失败追踪保存在逐题官方原始报告和evaluator_assertions.jsonl。','', '| 序号 | 任务 | 原epoch5通过/总数 | 原通过率 | Action通过/总数 | Action通过率 | Action官方成功 | 通过率变化（百分点） |', '| ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |']
 comparison=[]
 for i,tid in enumerate(ids,1):
  x=b[tid];y=c[tid];delta=y['test_pass_percentage']-x['test_pass_percentage']
  headers.append(f"| {i} | {tid} | {x['passed_tests']}/{x['num_tests']} | {x['test_pass_percentage']:.2f}% | {y['passed_tests']}/{y['num_tests']} | {y['test_pass_percentage']:.2f}% | {'成功' if y['official_success'] else '失败'} | {delta:+.2f} |")
  comparison.append(dict(task_id=tid,instruction=y['instruction'],difficulty=y['difficulty'],baseline_success=x['official_success'],candidate_success=y['official_success'],baseline_passed_tests=x['passed_tests'],baseline_failed_tests=x['failed_tests'],baseline_num_tests=x['num_tests'],baseline_evaluator_percentage=x['test_pass_percentage'],candidate_passed_tests=y['passed_tests'],candidate_failed_tests=y['failed_tests'],candidate_num_tests=y['num_tests'],candidate_evaluator_percentage=y['test_pass_percentage'],evaluator_percentage_point_change=delta,test_count_changed=x['num_tests']!=y['num_tests'],baseline_report=x['official_report_path'],candidate_report=y['official_report_path']))
 for i,tid in enumerate(ids,1):
  x=b[tid];y=c[tid];item=candidate_official['individual'][tid]
  headers += ['',f'## {i}. {tid}','',f"任务：{y['instruction']}",'',f"原epoch5：{x['passed_tests']}/{x['num_tests']}（{x['test_pass_percentage']:.2f}%），官方{'成功' if x['official_success'] else '失败'}。Action-1epoch：{y['passed_tests']}/{y['num_tests']}（{y['test_pass_percentage']:.2f}%），官方{'成功' if y['official_success'] else '失败'}。",'',f"[Action官方原始报告]({y['official_report_path']}) · [原epoch5官方原始报告]({x['official_report_path']})",'', '| 结果 | 官方测试条件（原文） | 官方标签 |','| --- | --- | --- |']
  for label,key in [('通过','passes'),('失败','failures')]:
   for test in item[key]:
    req=test['requirement'].replace('|','\\|').replace('\n','<br>');tag=str(test.get('label','')).replace('|','\\|')
    headers.append(f'| {label} | {req} | {tag} |')
 (OUT/'EVALUATOR_DETAILS.md').write_text('\n'.join(headers)+'\n')
 csvwrite(OUT/'evaluator_per_task_comparison.csv',comparison)
 return comparison

def main():
 m=read(OUT/'manifest.json');ck('run_complete',m['status'] in ['awaiting_validation','completed'])
 ids=(OUT/'dev_task_ids.txt').read_text().splitlines();ck('dev57_frozen',ids==m['dev_ids'] and len(ids)==len(set(ids))==57 and sha(OUT/'dev_task_ids.txt')==m['dev_ids_sha256'])
 for path,h in read(OUT/'old_results_guard.json')['files_sha256'].items():ck('prior_file_unchanged/'+path,sha(Path(path))==h)
 bv=read(OUT/'baseline_reuse_validation.json');ck('baseline_reuse_verified',bv['passed'])
 ck('selection_unchanged',sha(Path(m['selection_source']))==m['selection_sha256'])
 selected=read(Path(m['selection_source']));ck('same_unique_candidate',selected['selected_candidate']==CANDIDATE)
 check_summary=read(EXP/'step07b_check30_one_epoch/summary.json');ck('check30_positive_net_gain',check_summary['paired_comparisons'][CANDIDATE]['net_gain']==2)
 ck('logging_wrapper_unchanged',sha(OUT/'resilient_entry.py')==m['logging_wrapper_sha256'])
 for name,h in read(EXP/'step01_train90_student_rollouts/config/source_hashes.json').items():
  p=Path(name) if name.startswith('/') else EXP/'step01_train90_student_rollouts'/name
  ck('original_agent_source/'+name,sha(p)==h)
 bm=read(BASELINE/'manifest.json');ck('original_adapter_unchanged',sha(Path(bm['adapter'])/'adapter_model.safetensors')==bm['adapter_sha256'])
 d=OUT/CANDIDATE;cm=read(d/'manifest.json');ck('candidate_run_success',cm['exit_code']==0)
 trained=read(EXP/'step06b_lora_one_epoch/summary.json')['branches'][CANDIDATE]
 ck('candidate_weights_unchanged',cm['adapter']==trained['adapter_dir'] and sha(Path(cm['adapter'])/'adapter_model.safetensors')==cm['adapter_sha256']==trained['adapter_model_sha256'])
 ck('candidate_dev_split_exact',(d/'data/datasets/dev.txt').read_text().splitlines()==ids)
 ck('candidate_runner_identical_to_baseline',sha(d/'scripts_snapshot/appworld_run_isolated_lora_config.py')==m['baseline_runner_sha256'])
 ck('candidate_config_identical_to_baseline',sha(d/'config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev.jsonnet')==m['baseline_config_sha256'])
 events=jl(d/'logging_recovery_events.jsonl') if (d/'logging_recovery_events.jsonl').exists() else []
 ck('no_prefix_replay',cm['prefix_replay'] is False and all(e['event']=='log_only_ellipsis_encoding' for e in events),events)
 server_log=(d/SUB/'model_server.log').read_text(errors='replace')
 ck('actual_server_window_32000','max_seq_len=32000' in server_log)
 ck('actual_candidate_adapter_served',cm['adapter'] in server_log)
 ck('actual_no_reasoning_parser',"reasoning_parser='deepseek_r1'" not in server_log)
 baseline,base_official,first,base_assertions=audit_model('baseline',BASELINE,ids,bm)
 candidate,official,_,assertions=audit_model(CANDIDATE,d,ids,cm,first)
 ck('baseline_scores_match',aggregate(baseline)['success_count']==23 and aggregate(baseline)['evaluator_tests']['passed']==206 and aggregate(baseline)['evaluator_tests']['total']==291)
 models={'baseline':aggregate(baseline),CANDIDATE:aggregate(candidate)}
 models[CANDIDATE]['duration_seconds']=(datetime.datetime.fromisoformat(cm['run_finished_at'])-datetime.datetime.fromisoformat(cm['run_started_at'])).total_seconds()
 models[CANDIDATE]['adapter']=cm['adapter'];models[CANDIDATE]['adapter_sha256']=cm['adapter_sha256']
 b={r['task_id']:r for r in baseline};c={r['task_id']:r for r in candidate}
 gains=[t for t in ids if not b[t]['official_success'] and c[t]['official_success']]
 regressions=[t for t in ids if b[t]['official_success'] and not c[t]['official_success']]
 paired=dict(gained_task_ids=gains,regressed_task_ids=regressions,gained_success_count=len(gains),regression_count=len(regressions),net_gain=len(gains)-len(regressions),retained_success_count=23-len(regressions))
 ck('net_gain_consistent',paired['net_gain']==models[CANDIDATE]['success_count']-23)
 minimum=m['acceptance_rule']['dev57_success_count_at_least_baseline'];passed_gate=models[CANDIDATE]['success_count']>=minimum
 acceptance=dict(candidate='CFST-Action-1epoch',candidate_adapter=cm['adapter'],rule=m['acceptance_rule'],baseline_success_count=23,candidate_success_count=models[CANDIDATE]['success_count'],dev57_net_gain=paired['net_gain'],passed=passed_gate,decision='passes_predeclared_acceptance_gate' if passed_gate else 'reject_candidate_retain_original_epoch5',new_training=False,source60_refreshed=False,step08_started=False,note='Only the preselected candidate is accepted or rejected; no retuning or branch reselection uses Dev57. This request ends after evaluation and decision reporting.')
 comparison=write_details(ids,baseline,candidate,base_official,official)
 ck('all_57_detailed_rows_written',len(comparison)==57)
 for name,rows,tests in [('baseline',baseline,base_assertions),(CANDIDATE,candidate,assertions)]:
  target=OUT/name;target.mkdir(exist_ok=True)
  csvwrite(target/'task_results.csv',rows);jlwrite(target/'trajectory_index.jsonl',rows);jlwrite(target/'evaluator_assertions.jsonl',tests)
  dump(target/'summary.json',models[name]);listwrite(target/'success_task_ids.txt',[r['task_id'] for r in rows if r['official_success']]);listwrite(target/'failed_task_ids.txt',[r['task_id'] for r in rows if not r['official_success']])
 jlwrite(OUT/'evaluator_assertions.jsonl',assertions)
 dump(OUT/'official_candidate_evaluation.json',official)
 listwrite(OUT/'gained_task_ids.txt',gains);listwrite(OUT/'regressed_task_ids.txt',regressions)
 csvwrite(OUT/'task_comparison.csv',comparison)
 families=[]
 for fam in dict.fromkeys(t.rsplit('_',1)[0] for t in ids):
  tids=[t for t in ids if t.rsplit('_',1)[0]==fam]
  families.append(dict(family_id=fam,task_count=len(tids),baseline_success=sum(b[t]['official_success'] for t in tids),candidate_success=sum(c[t]['official_success'] for t in tids),baseline_passed_tests=sum(b[t]['passed_tests'] for t in tids),candidate_passed_tests=sum(c[t]['passed_tests'] for t in tids)))
 csvwrite(OUT/'family_comparison.csv',families)
 changed_test_counts=[t for t in ids if b[t]['num_tests']!=c[t]['num_tests']]
 summary=dict(status='completed',stage=OUT.name,candidate='CFST-Action-1epoch',baseline_reused=True,models=models,paired_comparison=paired,acceptance=acceptance,evaluator_reporting=dict(per_task_details_file=str(OUT/'EVALUATOR_DETAILS.md'),overall_test_pass_percentage_definition='100 * sum(passed_tests) / sum(num_tests); every reported evaluator condition has equal weight',macro_task_test_pass_percentage_definition='mean over 57 tasks of 100 * passed_tests / num_tests',official_TGC_definition='100 * count(official success) / 57; official result rounded to 1 decimal',official_SGC_definition='100 * count(families whose 3 tasks all succeed) / 19; official result rounded to 1 decimal',changed_test_count_task_ids=changed_test_counts),runtime_handling=dict(logging_only_ellipsis_fix=True,events=events,prefix_replay=False),teacher_calls=0,new_training=False,source60_refreshed=False,prior_protected_files_unchanged=len(read(OUT/'old_results_guard.json')['files_sha256']),completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 dump(OUT/'summary.json',summary);dump(OUT/'acceptance.json',acceptance)
 validation=dict(passed=True,checks_total=len(CHECKS),checks_passed=len(CHECKS),checks=CHECKS,new_trajectories=57,reused_baseline_trajectories=57,all_evaluator_conditions_exported=len(assertions))
 dump(OUT/'validation.json',validation);dump(OUT/'evidence_sha256.json',EVIDENCE)
 x=models['baseline'];y=models[CANDIDATE];xt=x['evaluator_tests'];yt=y['evaluator_tests']
 decision='通过预先确定的接受门槛' if passed_gate else '未通过预先确定的接受门槛，保留原epoch5'
 lines=['# CFST第7c步：Action-1epoch的Dev57官方评测','',f"**57题全部完成并通过核验。CFST-Action-1epoch官方成功{y['success_count']}/57（{y['task_goal_completion']:.1f}%），全部evaluator测试条件通过{yt['passed']}/{yt['total']}（{yt['overall_pass_percentage']:.2f}%）。**",'',
  '| 指标 | 原epoch5（核验后复用） | CFST-Action-1epoch |', '| --- | ---: | ---: |',
  f"| 官方任务成功数 / TGC | 23/57；{x['task_goal_completion']:.1f}% | {y['success_count']}/57；{y['task_goal_completion']:.1f}% |",
  f"| 官方完整成功任务族 / SGC | {x['successful_family_count']}/19；{x['scenario_goal_completion']:.1f}% | {y['successful_family_count']}/19；{y['scenario_goal_completion']:.1f}% |",
  f"| 全部evaluator测试条件通过比例 | {xt['passed']}/{xt['total']}；{xt['overall_pass_percentage']:.2f}% | {yt['passed']}/{yt['total']}；{yt['overall_pass_percentage']:.2f}% |",
  f"| 57题各自测试通过率的平均值 | {xt['macro_task_pass_percentage']:.2f}% | {yt['macro_task_pass_percentage']:.2f}% |",'',
  '**百分比口径：** 总体测试条件通过率＝全部通过条件数÷全部报告条件数；逐题平均通过率先计算每题比例再对57题平均。官方TGC要求整题成功；这些指标含义不同，部分条件通过不能当作整题成功。所有分母使用官方实际输出，不丢弃失败任务或失败条件。', '',
  f"**逐题明细：** [57题evaluator完整报告]({OUT}/EVALUATOR_DETAILS.md) · [逐题对照CSV]({OUT}/evaluator_per_task_comparison.csv) · [每条测试条件及完整失败追踪]({OUT}/evaluator_assertions.jsonl) · [官方完整JSON]({OUT}/official_candidate_evaluation.json)", '',
  '## 相对原epoch5的变化','',f"新增成功{len(gains)}题，退步{len(regressions)}题，净变化{paired['net_gain']:+d}题。",'',
  '- 新增成功：'+('、'.join(gains) or '无')+'。', '- 退步：'+('、'.join(regressions) or '无')+'。','',
  f"**冻结规则的决定：{decision}。** 检查30题净增2题已经满足第一项；Dev57要求成功数不低于23题，本次为{y['success_count']}题。测试条件通过百分比作为详细诊断报告，不替换这个接受标准。",'',
  '本次只评测此前检查30题已经选出的Action-1epoch，不使用Dev57重新选择State/Mixed、不调整参数、不训练或生成教师答案，也不自动刷新来源60题。', '',
  '## 难度分组','', '| 难度 | 原epoch5成功/总数 | Action-1epoch成功/总数 |', '| --- | ---: | ---: |']
 for difficulty in ['1','2','3']:
  z=x['difficulty'][difficulty];w=y['difficulty'][difficulty];lines.append(f"| {difficulty} | {z['success']}/{z['total']} | {w['success']}/{w['total']} |")
 lines+=['','## 协议、成本与核验','',
  '使用同一官方Dev57清单、同一运行器与配置：temperature=0、seed=100、32,000上下文、单次最多3,000输出tokens、每题最多50步、无reasoning parser、单进程逐题从初始环境运行。Action权重与第6b步冻结权重完全一致。', '',
  f"原epoch5的1,014次历史请求已核验，官方成功23/57、测试条件通过206/291；本次每题首条输入与同题基线逐字一致。{len(CHECKS)}项核验通过，{summary['prior_protected_files_unchanged']}个历史保护文件保持原哈希。日志序列化兼容只影响API日志写盘，本次无旧响应重放。", '',
  f"Action本次模型调用{y['model_calls']}次，输入tokens {y['input_tokens']:,}，输出tokens {y['output_tokens']:,}；触发上下文限制{len(y['context_error_task_ids'])}题，运行耗时{y['duration_seconds']/60:.1f}分钟。对应逐题终止原因、测试计数和失败条件均在CSV与原始轨迹中保留。", '',
  '单次固定种子的评测只用于执行本轮预先约定的接受检查；结果不单独证明能力分类合理。若今后依据这些Dev结果修订方法，应将其视为开发证据。', '',
  '## 文件','',
  '- EVALUATOR_DETAILS.md：57题对照表、任务要求、所有官方测试条件及原始报告链接。',
  '- evaluator_per_task_comparison.csv / task_comparison.csv：每题通过数、失败数、百分比、任务成功、相对基线变化。',
  '- evaluator_assertions.jsonl：候选所有测试条件的结果、原始标签和失败trace。',
  '- family_comparison.csv：19个任务族对比。',
  '- summary.json / acceptance.json / validation.json：汇总、冻结接受判断及完整核验。',
  '- CFST-Action/：完整轨迹、日志、官方评分、逐题索引、成功/失败清单。',
  '- baseline/：复用结果及逐题索引；baseline_reuse_validation.json记录复用证据。','']
 if changed_test_counts:lines+=['注意：这些题官方报告的测试条件数量与基线不同，比例均按各自实际分母计算：'+', '.join(changed_test_counts)+'。','']
 (OUT/'README.md').write_text('\n'.join(lines)+'\n')
 cm.update(status='completed');dump(d/'manifest.json',cm)
 m.update(status='completed',validated_at_utc=summary['completed_at_utc'],acceptance=acceptance,branches={CANDIDATE:cm});dump(OUT/'manifest.json',m)
 files=[p for p in OUT.iterdir() if p.is_file() and p.name not in ['artifact_sha256.json','run.lock','finalization.log']]
 dump(OUT/'artifact_sha256.json',{str(p.relative_to(OUT)):sha(p) for p in files})
 print(json.dumps(dict(status='completed',models=models,paired_comparison=paired,acceptance=acceptance,checks=len(CHECKS)),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
