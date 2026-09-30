"""Audit Dev57, export every evaluator requirement, and compare the requested State diagnostic model."""
from pathlib import Path
import collections,csv,datetime,hashlib,json,re
OUT=Path(__file__).resolve().parent
EXP=OUT.parent
ROOT=EXP.parents[1]
BASELINE=ROOT/'experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57'
SUB=Path('experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev')
CANDIDATE='CFST-state'
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
 headers=['# Dev57：57题逐题evaluator明细','', '每题通过百分比＝该题官方通过测试条件数÷该题实际报告的测试条件总数。任务成功/失败直接使用官方success，不能用部分通过百分比替代。下面原样列出候选模型的所有测试条件及通过/失败状态，失败追踪保存在逐题官方原始报告和evaluator_assertions.jsonl。','', '| 序号 | 任务 | 原epoch5通过/总数 | 原通过率 | State通过/总数 | State通过率 | State官方成功 | 通过率变化（百分点） |', '| ---: | --- | ---: | ---: | ---: | ---: | --- | ---: |']
 comparison=[]
 for i,tid in enumerate(ids,1):
  x=b[tid];y=c[tid];delta=y['test_pass_percentage']-x['test_pass_percentage']
  headers.append(f"| {i} | {tid} | {x['passed_tests']}/{x['num_tests']} | {x['test_pass_percentage']:.2f}% | {y['passed_tests']}/{y['num_tests']} | {y['test_pass_percentage']:.2f}% | {'成功' if y['official_success'] else '失败'} | {delta:+.2f} |")
  comparison.append(dict(task_id=tid,instruction=y['instruction'],difficulty=y['difficulty'],baseline_success=x['official_success'],candidate_success=y['official_success'],baseline_passed_tests=x['passed_tests'],baseline_failed_tests=x['failed_tests'],baseline_num_tests=x['num_tests'],baseline_evaluator_percentage=x['test_pass_percentage'],candidate_passed_tests=y['passed_tests'],candidate_failed_tests=y['failed_tests'],candidate_num_tests=y['num_tests'],candidate_evaluator_percentage=y['test_pass_percentage'],evaluator_percentage_point_change=delta,test_count_changed=x['num_tests']!=y['num_tests'],baseline_report=x['official_report_path'],candidate_report=y['official_report_path']))
 for i,tid in enumerate(ids,1):
  x=b[tid];y=c[tid];item=candidate_official['individual'][tid]
  headers += ['',f'## {i}. {tid}','',f"任务：{y['instruction']}",'',f"原epoch5：{x['passed_tests']}/{x['num_tests']}（{x['test_pass_percentage']:.2f}%），官方{'成功' if x['official_success'] else '失败'}。State-1epoch：{y['passed_tests']}/{y['num_tests']}（{y['test_pass_percentage']:.2f}%），官方{'成功' if y['official_success'] else '失败'}。",'',f"[State官方原始报告]({y['official_report_path']}) · [原epoch5官方原始报告]({x['official_report_path']})",'', '| 结果 | 官方测试条件（原文） | 官方标签 |','| --- | --- | --- |']
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
 selected=read(Path(m['selection_source']));ck('previous_selection_unchanged',selected['selected_candidate']=='CFST-Action' and m['evaluation_kind']=='diagnostic' and m['evaluated_branch']==CANDIDATE)
 check_summary=read(EXP/'step07b_check30_one_epoch/summary.json');ck('check30_record_unchanged',check_summary['paired_comparisons'][CANDIDATE]['net_gain']==0)
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
 groups={}
 for key,label,selected_ids in [('both_success','两者均成功',[t for t in ids if b[t]['official_success'] and c[t]['official_success']]),('gained','原失败→State成功',gains),('regressed','原成功→State失败',regressions),('both_failed','两者均失败',[t for t in ids if not b[t]['official_success'] and not c[t]['official_success']])]:
  bp=sum(b[t]['passed_tests'] for t in selected_ids);sp=sum(c[t]['passed_tests'] for t in selected_ids)
  groups[key]=dict(label=label,task_count=len(selected_ids),task_ids=selected_ids,baseline_passed=bp,state_passed=sp,total_tests=sum(c[t]['num_tests'] for t in selected_ids),passed_condition_delta=sp-bp)
 ck('condition_decomposition_full_coverage',sum(g['task_count'] for g in groups.values())==57)
 ck('condition_decomposition_matches_scores',sum(g['state_passed'] for g in groups.values())==models[CANDIDATE]['evaluator_tests']['passed'] and sum(g['baseline_passed'] for g in groups.values())==206)
 dump(OUT/'score_change_decomposition.json',groups)
 condition_explanation=['## 为什么整题成功增加，条件得分反而下降','', '| 任务组 | 题数 | 原epoch5通过条件 | State通过条件 | 通过条件变化 |','| --- | ---: | ---: | ---: | ---: |']
 for g in groups.values():condition_explanation.append(f"| {g['label']} | {g['task_count']} | {g['baseline_passed']}/{g['total_tests']} | {g['state_passed']}/{g['total_tests']} | {g['passed_condition_delta']:+d} |")
 condition_explanation+=['',f"尤其是两者都未整题成功的{groups['both_failed']['task_count']}题，State通过条件由{groups['both_failed']['baseline_passed']}降到{groups['both_failed']['state_passed']}，这部分变化不会体现在整题成功数里。新增成功和退步题的得失合并后，总条件通过数仍下降。因此本次应描述为：整题成功小幅增加，但条件完成程度下降，不能笼统说与原模型表现相同。",'']
 references={};reference_rows={};reference_lookups={}
 for key,field,expected_success,expected_tests in [('CFST-Action','action_reference',31,215),('CFST-Mixed','mixed_reference',21,184)]:
  prior=Path(m[field]);ck(key+'/reference_validated',read(prior/'validation.json')['passed'] and read(prior/'summary.json')['status']=='completed')
  rows=jl(prior/key/'trajectory_index.jsonl');ck(key+'/same_57_ids',[r['task_id'] for r in rows]==ids)
  score=aggregate(rows);ck(key+'/reference_score',score['success_count']==expected_success and score['evaluator_tests']['passed']==expected_tests and score['evaluator_tests']['total']==291)
  prior_manifest=read(prior/'manifest.json');ck(key+'/same_protocol',prior_manifest['protocol']==m['protocol'])
  models[key]=score;reference_rows[key]=rows;reference_lookups[key]={r['task_id']:r for r in rows}
  references[key]=dict(source=str(prior),summary_sha256=sha(prior/'summary.json'),validation_sha256=sha(prior/'validation.json'))
 a=reference_lookups['CFST-Action'];mix=reference_lookups['CFST-Mixed']
 four=[]
 for tid in ids:
  row=dict(task_id=tid,difficulty=c[tid]['difficulty'],instruction=c[tid]['instruction'])
  for label,lookup in [('baseline',b),('state',c),('action',a),('mixed',mix)]:
   for key in ['official_success','passed_tests','failed_tests','num_tests','test_pass_percentage','official_report_path']:row[label+'_'+key]=lookup[tid][key]
  four.append(row)
 csvwrite(OUT/'four_model_per_task.csv',four)
 comparisons={}
 for key,lookup in reference_lookups.items():
  comparisons[key]=dict(gained_task_ids=[t for t in ids if not lookup[t]['official_success'] and c[t]['official_success']],regressed_task_ids=[t for t in ids if lookup[t]['official_success'] and not c[t]['official_success']],net_gain=models[CANDIDATE]['success_count']-models[key]['success_count'])
 x=models['baseline'];y=models[CANDIDATE];xt=x['evaluator_tests'];yt=y['evaluator_tests']
 decision='lower' if paired['net_gain']<0 else ('higher' if paired['net_gain']>0 else 'equal')
 diagnostic=dict(evaluated_model='CFST-State-1epoch',reference_model='Qwen3-8B + train90 LoRA epoch5 (before CFST)',observed_task_success_vs_baseline=decision,dev57_net_gain=paired['net_gain'],task_success_percentage_point_change=y['task_goal_completion_exact']-x['task_goal_completion_exact'],evaluator_overall_percentage_point_change=yt['overall_pass_percentage']-xt['overall_pass_percentage'],evaluator_macro_percentage_point_change=yt['macro_task_pass_percentage']-xt['macro_task_pass_percentage'],previous_selected_candidate='CFST-Action',selection_unchanged=True,action_acceptance_unchanged=True,interpretation_scope='User-requested fixed-seed diagnostic after Action and Mixed Dev57; report actual differences, no assumed equivalence or causal claim about classification.',step08_started=False,source60_refreshed=False)
 model_order=['baseline',CANDIDATE,'CFST-Action','CFST-Mixed'];labels={'baseline':'原epoch5',CANDIDATE:'State-1epoch','CFST-Action':'Action-1epoch','CFST-Mixed':'Mixed-1epoch'}
 model_table=[]
 for key in model_order:
  z=models[key];t=z['evaluator_tests'];check_n=17 if key=='baseline' else check_summary['models'][key]['success_count']
  model_table.append(dict(model=labels[key],check30_success=check_n,check30_task_count=30,dev57_success=z['success_count'],dev57_task_count=57,dev57_tgc=z['task_goal_completion_exact'],successful_families=z['successful_family_count'],families=z['family_count'],evaluator_passed=t['passed'],evaluator_total=t['total'],evaluator_overall_percentage=t['overall_pass_percentage'],evaluator_macro_percentage=t['macro_task_pass_percentage']))
 csvwrite(OUT/'model_comparison.csv',model_table)
 summary=dict(status='completed',stage=OUT.name,evaluated_model='CFST-State-1epoch',evaluation_kind='diagnostic',baseline_reused=True,action_reused=True,mixed_reused=True,references=references,models=models,paired_comparison=paired,state_vs_other_branches=comparisons,score_change_decomposition=groups,diagnostic=diagnostic,evaluator_reporting=dict(per_task_details_file=str(OUT/'EVALUATOR_DETAILS.md'),overall_test_pass_percentage_definition='100 * sum(passed_tests) / sum(num_tests)',macro_task_test_pass_percentage_definition='mean of per-task percentages across all 57 tasks',official_TGC_definition='100 * official success tasks / 57',official_SGC_definition='100 * completely successful families / 19',changed_test_count_task_ids=changed_test_counts),runtime_handling=dict(logging_only_ellipsis_fix=True,events=events,prefix_replay=False),teacher_calls=0,new_training=False,source60_refreshed=False,prior_protected_files_unchanged=len(read(OUT/'old_results_guard.json')['files_sha256']),completed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 ck('all_candidate_conditions_exported',len(assertions)==yt['total'])
 dump(OUT/'summary.json',summary);dump(OUT/'diagnostic_decision.json',diagnostic)
 validation=dict(passed=True,checks_total=len(CHECKS),checks_passed=len(CHECKS),checks=CHECKS,new_trajectories=57,reused_baseline_trajectories=57,reused_action_trajectories=57,reused_mixed_trajectories=57,all_evaluator_conditions_exported=len(assertions))
 dump(OUT/'validation.json',validation);dump(OUT/'evidence_sha256.json',EVIDENCE)
 conclusion={'lower':'低于','equal':'持平于','higher':'高于'}[decision]
 lines=['# CFST第7e步：State-1epoch的Dev57补充诊断评测','',f"**57题全部完成。State官方成功{y['success_count']}/57（{y['task_goal_completion']:.1f}%），本次{conclusion}原epoch5的23/57；净变化{paired['net_gain']:+d}题。全部evaluator测试条件通过{yt['passed']}/{yt['total']}（{yt['overall_pass_percentage']:.2f}%）。**",'',
 '本次使用第6b步的CFST-state adapter：12条状态构建修复动作各训练一遍，共6次参数更新。原模型指Qwen3-8B + train90 LoRA epoch5，即追加CFST训练之前的模型。其余三个模型的Dev结果经核验复用。', '',
 '| 模型 | 检查30题成功 | Dev57成功 / TGC | 完整任务族 / SGC | evaluator全部条件通过率 | 逐题条件通过率平均值 |','| --- | ---: | ---: | ---: | ---: | ---: |']
 for key,r in zip(model_order,model_table):
  z=models[key];t=z['evaluator_tests'];lines.append(f"| {labels[key]} | {r['check30_success']}/30 | {z['success_count']}/57；{z['task_goal_completion']:.1f}% | {z['successful_family_count']}/19；{z['scenario_goal_completion']:.1f}% | {t['passed']}/{t['total']}；{t['overall_pass_percentage']:.2f}% | {t['macro_task_pass_percentage']:.2f}% |")
 lines+=['','总体evaluator通过率＝全部通过条件数÷全部报告条件数；逐题平均值先算每题比例再平均。官方TGC使用整题success，部分条件通过不能替代整题成功。失败任务全部计入分母。','',
 f"[57题evaluator完整明细]({OUT}/EVALUATOR_DETAILS.md) · [State与原模型逐题对照]({OUT}/evaluator_per_task_comparison.csv) · [四模型逐题对照]({OUT}/four_model_per_task.csv) · [每个条件及失败trace]({OUT}/evaluator_assertions.jsonl)",'',
 '## State相对原epoch5的变化','',f"新增成功{len(gains)}题、退步{len(regressions)}题、保留原成功{paired['retained_success_count']}题，净变化{paired['net_gain']:+d}题；官方成功率变化{diagnostic['task_success_percentage_point_change']:+.2f}个百分点，全部测试条件通过率变化{diagnostic['evaluator_overall_percentage_point_change']:+.2f}个百分点。",'',
 '- 新增成功：'+('、'.join(gains) or '无')+'。','- 退步：'+('、'.join(regressions) or '无')+'。','',
 *condition_explanation,'## 如何解释','',f"检查30题中State与原epoch5都是17/30；Dev57本次State是{y['success_count']}/57，原epoch5是23/57。是否接近应结合实际差距和逐题得失理解，不能从检查30题总分相同预先认定Dev也会相同。",'',
 '本次没有预先规定“差不多”的容许范围，因此报告实际差值，不把单次结果称为统计等效。四模型结果是当前固定种子实验的观察；它不能单独证明分类有效，或把分支差异完全归于某项能力。三个包的数据内容、条数和更新次数也不同。','',
 '本次是在Action、Mixed结果完成后按用户要求追加的诊断。保留原第7b步候选选择和第7c步Action接受记录，不依据新增Dev结果改参数或重选分支。','',
 '## 难度分组','', '| 难度 | 原epoch5 | State-1epoch | Action-1epoch | Mixed-1epoch |', '| --- | ---: | ---: | ---: | ---: |']
 for diff in ['1','2','3']:
  vals=[models[k]['difficulty'][diff] for k in model_order];lines.append('| '+diff+' | '+' | '.join(f"{z['success']}/{z['total']}" for z in vals)+' |')
 lines+=['','## 协议、成本与核验','',
 '同一官方Dev57清单、运行器与配置：temperature=0、seed=100、32,000上下文、单次最多3,000输出tokens、每题最多50步、无reasoning parser、单进程逐题从初始环境运行。State权重与第6b步冻结权重一致，每题初始输入与原epoch5逐字一致。', '',
 f"{len(CHECKS)}项核验通过，{summary['prior_protected_files_unchanged']}个历史保护文件原哈希不变。日志兼容仅用于API日志写盘；本次无旧响应重放。State模型调用{y['model_calls']}次，输入tokens {y['input_tokens']:,}，输出tokens {y['output_tokens']:,}，{len(y['context_error_task_ids'])}题触发上下文限制，耗时{y['duration_seconds']/60:.1f}分钟。",'',
 '未训练模型、生成教师答案、调整超参数或刷新来源60题。所有失败保留逐步交互与官方报告。','',
 '## 文件','',
 '- EVALUATOR_DETAILS.md：57题任务要求、结果、所有官方条件及原始报告链接。',
 '- evaluator_per_task_comparison.csv / four_model_per_task.csv / model_comparison.csv：逐题及四模型总体对照。',
 '- evaluator_assertions.jsonl / official_candidate_evaluation.json：每个条件、失败trace与官方完整输出。',
 '- summary.json / diagnostic_decision.json / validation.json：指标、诊断判断与核验证据。',
 '- score_change_decomposition.json：按成功/失败变化分组，解释任务成功与条件得分的不同方向。',
 '- CFST-state/：完整轨迹、配置、逐题评分、成功/失败清单。',
 '- gained_task_ids.txt / regressed_task_ids.txt / family_comparison.csv：相对原模型变化。','']
 if changed_test_counts:lines+=['官方条件数量变化的任务（各按实际分母计算）：'+', '.join(changed_test_counts)+'。','']
 (OUT/'README.md').write_text('\n'.join(lines)+'\n')
 cm.update(status='completed');dump(d/'manifest.json',cm)
 m.update(status='completed',validated_at_utc=summary['completed_at_utc'],diagnostic=diagnostic,branches={CANDIDATE:cm});dump(OUT/'manifest.json',m)
 files=[p for p in OUT.iterdir() if p.is_file() and p.name not in ['artifact_sha256.json','run.lock','finalization.log']]
 for sub in [OUT/'baseline',d]:files.extend(p for p in sub.iterdir() if p.is_file())
 for sub in [d/'scripts_snapshot',d/'config']:files.extend(p for p in sub.rglob('*') if p.is_file())
 dump(OUT/'artifact_sha256.json',{str(p.relative_to(OUT)):sha(p) for p in files})
 print(json.dumps(dict(status='completed',models=models,paired_comparison=paired,diagnostic=diagnostic,checks=len(CHECKS)),ensure_ascii=False,indent=2))
if __name__=='__main__':main()
