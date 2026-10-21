"""Paired descriptive analysis; no new model calls and no hidden data sent to judges."""
from pathlib import Path
from collections import Counter,defaultdict
import csv,json,random,statistics as st,sys
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json
O=R/'analysis';SEEDS=[20261015,20261016,20261017];GROUPS=['full_rule_1358','drop_r1','drop_r2'];PANELS=['primary','focused_E','focused_R','focused_D','focused_S']
METRICS=['effective_feedback','grounded_progress','state_contradiction','no_information_gain','missing_required_spec','premature_termination','execution_error','no_code','truncated','generated_tokens']

def read(p):return json.loads(Path(p).read_text())
def save_csv(name,rows):
 if not rows:return
 with (O/name).open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=list(rows[0]));wr.writeheader();wr.writerows(rows)
def key(s):return s.replace(':','__')
def eligible(r,m):
 return r['feedback_opportunity']=='yes' if m=='effective_feedback' else r['state_use_opportunity']=='yes' if m in ['grounded_progress','state_contradiction'] else True

def task_equal(rows,metric):
 groups=defaultdict(list)
 for r in rows:
  if eligible(r,metric):groups[(r['seed'],r['task_id'])].append(r[metric])
 seeds=defaultdict(list)
 for (seed,task),vs in groups.items():seeds[seed].append(st.mean(vs))
 return st.mean(st.mean(v) for v in seeds.values()) if seeds else None

def metric_unknown(r,m):
 return int(r['feedback_response']=='uncertain') if m=='effective_feedback' else int(r['progress_unknown']) if m=='grounded_progress' else int(r['state_use']=='unresolved') if m=='state_contradiction' else int(r['repetition']=='uncertain') if m=='no_information_gain' else int(r['documentation']=='uncertain') if m=='missing_required_spec' else int(r['termination']=='uncertain') if m=='premature_termination' else 0

def bootstrap_pair(rows,arm,metric,iterations=2000,baseline='full_rule_1358'):
 lookup={(x['group'],x['seed'],x['state_id']):x for x in rows};tasks=defaultdict(list)
 for x in rows:
  if x['group']==arm and eligible(x,metric):tasks[x['task_id']].append(x[metric]-lookup[baseline,x['seed'],x['state_id']][metric])
 if not tasks:return None,None
 families=defaultdict(list)
 for task,vals in tasks.items():families[task.split('_')[0]].append(st.mean(vals))
 fams=sorted(families);rng=random.Random(20261019);samples=[]
 for _ in range(iterations):
  draw=[rng.choice(fams) for _ in fams];samples.append(st.mean(v for f in draw for v in families[f]))
 samples.sort();return samples[int(.025*iterations)],samples[int(.975*iterations)]

def main():
 states={x['state_id']:x for x in csv.DictReader((R/'plan_snapshot/states_selected.csv').open())};models=read(R/'config/model_aliases_researcher_only.json');by_name={f"{m['group']}__seed_{m['training_seed']}":m for m in models};common=read(O/'common_states.json');links=read(O/'judgement_index.json');rows=[];checks=[]
 mapping={(x['family'],x['requirement']):x['category'] for x in csv.DictReader((R/'config/evaluator_type_mapping.csv').open())};assert len(mapping)==97
 data_root=Path(read(R/'config/runtime.json')['paths']['appworld_data']);null={t:read(data_root/f'tasks/{t}/ground_truth/answer.json') is None for t in {s['task_id'] for s in states.values()}}
 for link in links:
  sid=link['state_id'];s=states[sid];m=by_name[link['model']];j=read(link['judgement']);card=read(R/'judge_runs/cards'/key(sid)/'judgement.json');g=read(R/'results/generations'/link['model']/f'{key(sid)}.json');execution=read(R/'results/executions'/link['model']/f'{key(sid)}.json');c=execution['candidate'];before=read(R/'results/evaluators/reference'/f'{key(sid)}.before.json');after=read(R/'results/evaluators'/link['model']/f'{key(sid)}.after.json');assert before['checks'].keys()==after['checks'].keys()
  progress=j['meaningful_progress']['labels'];positive=bool(set(progress)&{'evidence_gain','supported_operation','supported_completion'})
  x={'group':m['group'],'seed':m['training_seed'],'state_id':sid,'task_id':s['task_id'],'family':s['family'],'panel':s['panel'],'temporal_band':s['temporal_band'],'stratum':s['stratum'],'feedback_opportunity':card['feedback_opportunity'],'state_use_opportunity':card['state_use_opportunity'],'feedback_response':j['feedback_response']['label'],'state_use':j['state_use']['label'],'meaningful_progress':','.join(progress),'effective_feedback':int(j['feedback_response']['label'] in ['resolved','necessary_new_evidence']),'grounded_progress':int(positive),'progress_unknown':int(not positive and 'uncertain' in progress),'state_contradiction':int(j['state_use']['label']=='contradicted'),'no_information_gain':int(j['repetition']['label']=='no_information_gain'),'missing_required_spec':int(j['documentation']['label']=='missing_required_spec'),'premature_termination':int(j['termination']['label']=='premature_or_wrong'),'execution_error':int(c['execution_error']),'no_code':int(c['no_code']),'truncated':int(g['finish_reason']=='length'),'generated_tokens':len(g['response_ids']),'actual_api_requests':len(c['actual_request_methods_urls']),'code_repeated':int(c['code_repeated']),'before_pass_fraction':before['num_passes']/before['num_tests'],'after_pass_fraction':after['num_passes']/after['num_tests'],'evaluator_gain':sum(not v and after['checks'][k] for k,v in before['checks'].items()),'evaluator_loss':sum(v and not after['checks'][k] for k,v in before['checks'].items()),'after_task_success':int(after['success']),'rubrics':''.join(v['label'] for v in j['rubrics']),'judgement':link['judgement']}
  x.update({field:j[field]['label'] for field in ['repetition','documentation','termination','new_execution_issue']})
  rows.append(x)
  for requirement,b in before['checks'].items():
   cat=mapping[s['family'],requirement]
   if cat=='answer':cat='answer_null' if null[s['task_id']] else 'answer_value'
   a=after['checks'][requirement];checks.append({k:x[k] for k in ['group','seed','state_id','task_id','family','panel']}|{'requirement':requirement,'category':cat,'before':int(b),'after':int(a),'gain':int(a and not b),'loss':int(b and not a)})
 assert len(rows)==len(common['state_ids'])*9
 save_csv('behavior_rows.csv',rows);save_csv('evaluator_checks.csv',checks)
 coverage=[]
 for s in states.values():coverage.append({k:s[k] for k in ['state_id','task_id','family','panel','temporal_band','stratum']}|{'common_executable':int(s['state_id'] in common['state_ids'])})
 save_csv('state_coverage.csv',coverage)
 metrics=[]
 for panel in PANELS:
  for group in GROUPS:
   for seed in SEEDS+['all']:
    xx=[r for r in rows if r['panel']==panel and r['group']==group and (seed=='all' or r['seed']==seed)]
    for metric in METRICS:
     yy=[r for r in xx if eligible(r,metric)];num=sum(r[metric] for r in yy);unk=sum(metric_unknown(r,metric) for r in yy);den=len(yy)
     metrics.append({'panel':panel,'group':group,'seed':seed,'metric':metric,'eligible_model_state_rows':den,'eligible_states':len({r['state_id'] for r in yy}),'eligible_tasks':len({r['task_id'] for r in yy}),'numerator':num,'unknown':unk,'opportunity_uncertain_states':len({r['state_id'] for r in xx if (r['feedback_opportunity'] if metric=='effective_feedback' else r['state_use_opportunity'] if metric in ['grounded_progress','state_contradiction'] else 'no')=='uncertain'}),'pooled_rate':num/den if den else None,'unknown_upper_bound':(num+unk)/den if den else None,'task_equal_rate':task_equal(xx,metric)})
 save_csv('behavior_metrics.csv',metrics)
 paired=[]
 for panel in PANELS:
  xx=[r for r in rows if r['panel']==panel]
  for arm,baseline in [('drop_r1','full_rule_1358'),('drop_r2','full_rule_1358'),('drop_r1','drop_r2')]:
   for metric in METRICS:
    rates={g:task_equal([r for r in xx if r['group']==g],metric) for g in [arm,baseline]};lo,hi=bootstrap_pair(xx,arm,metric,baseline=baseline)
    diffs=[]
    for seed in SEEDS:
     a=task_equal([r for r in xx if r['group']==arm and r['seed']==seed],metric);b=task_equal([r for r in xx if r['group']==baseline and r['seed']==seed],metric);diffs.append(None if a is None or b is None else a-b)
    paired.append({'panel':panel,'contrast':arm+' - '+baseline,'metric':metric,'task_equal_difference':None if None in rates.values() else rates[arm]-rates[baseline],'seed_20261015':diffs[0],'seed_20261016':diffs[1],'seed_20261017':diffs[2],'family_bootstrap_low':lo,'family_bootstrap_high':hi})
 save_csv('paired_behavior_contrasts.csv',paired)
 # Preserve uncertain opportunity states as explicit sensitivity populations.
 sensitivity=[]
 for panel in PANELS:
  for group in GROUPS:
   for metric,op in [('effective_feedback','feedback_opportunity'),('grounded_progress','state_use_opportunity'),('state_contradiction','state_use_opportunity')]:
    for mode in ['yes_plus_uncertain','uncertain_only']:
     allowed={'yes','uncertain'} if mode=='yes_plus_uncertain' else {'uncertain'}
     xx=[dict(x,**{op:'yes'}) for x in rows if x['panel']==panel and x['group']==group and x[op] in allowed]
     n=len(xx);num=sum(x[metric] for x in xx);unk=sum(metric_unknown(x,metric) for x in xx)
     sensitivity.append({'panel':panel,'group':group,'metric':metric,'opportunity_sensitivity':mode,'model_state_rows':n,'states':len({x['state_id'] for x in xx}),'numerator':num,'unknown':unk,'pooled_rate':num/n if n else None,'unknown_upper_bound':(num+unk)/n if n else None,'task_equal_rate':task_equal(xx,metric)})
 save_csv('opportunity_sensitivity_metrics.csv',sensitivity)
 evsummaries=[]
 for panel in PANELS:
  for group in GROUPS:
   for seed in SEEDS+['all']:
    xx=[x for x in rows if x['panel']==panel and x['group']==group and (seed=='all' or x['seed']==seed)]
    evsummaries.append({'panel':panel,'group':group,'seed':seed,'model_state_rows':len(xx),'before_macro':task_equal(xx,'before_pass_fraction'),'after_macro':task_equal(xx,'after_pass_fraction'),'after_task_success_rate':task_equal(xx,'after_task_success'),'newly_passed_requirements':sum(x['evaluator_gain'] for x in xx),'lost_requirements':sum(x['evaluator_loss'] for x in xx)})
 save_csv('evaluator_model_summary.csv',evsummaries)
 # Family slices and the full P/F/U/N distributions, without model-dependent denominator removal.
 families=[];rubrics=[]
 for family in sorted({r['family'] for r in rows}):
  for g in GROUPS:
   xx=[r for r in rows if r['family']==family and r['panel']=='primary' and r['group']==g]
   families.append({'family':family,'group':g,'model_state_rows':len(xx),**{m:task_equal(xx,m) for m in METRICS}})
 save_csv('behavior_families.csv',families)
 for panel in PANELS:
  for g in GROUPS:
   for seed in SEEDS+['all']:
    xx=[r for r in rows if r['panel']==panel and r['group']==g and (seed=='all' or r['seed']==seed)]
    for i in range(8):
     cnt=Counter(r['rubrics'][i] for r in xx);rubrics.append({'panel':panel,'group':g,'seed':seed,'rule':f'R{i+1}','denominator':len(xx),**{k:cnt[k] for k in 'PFUN'}})
 save_csv('rubric_distributions.csv',rubrics)
 # Paired requirement changes relative to full-rule action, not just terminal task counts.
 lookup={(x['group'],x['seed'],x['state_id'],x['requirement']):x for x in checks};evpairs=[]
 for x in checks:
  if x['group']=='full_rule_1358':continue
  b=lookup['full_rule_1358',x['seed'],x['state_id'],x['requirement']];assert x['before']==b['before']
  evpairs.append(x|{'full_rule_after':b['after'],'wins_vs_full':int(x['after']>b['after']),'losses_vs_full':int(x['after']<b['after'])})
 save_csv('paired_evaluator_checks.csv',evpairs)
 evtypes=[]
 for panel in PANELS:
  for g in GROUPS:
   for seed in SEEDS+['all']:
    for cat in sorted({x['category'] for x in checks}):
     xx=[x for x in checks if x['panel']==panel and x['group']==g and x['category']==cat and (seed=='all' or x['seed']==seed)]
     yy=[x for x in evpairs if x['panel']==panel and x['group']==g and x['category']==cat and (seed=='all' or x['seed']==seed)]
     evtypes.append({'panel':panel,'group':g,'seed':seed,'category':cat,'checks':len(xx),'before_pass':sum(x['before'] for x in xx),'after_pass':sum(x['after'] for x in xx),'gains_from_prefix':sum(x['gain'] for x in xx),'losses_from_prefix':sum(x['loss'] for x in xx),'wins_vs_full':sum(x['wins_vs_full'] for x in yy),'losses_vs_full':sum(x['losses_vs_full'] for x in yy)})
 save_csv('evaluator_categories.csv',evtypes)
 # Repeated judge consistency is not an independent human/second-model validation.
 linkmap={(x['model'],x['state_id']):x for x in links};reviews=[]
 for item in read(R/'config/random_review_manifest.json'):
  if not item['common_execution_valid']:continue
  link=linkmap[item['model'],item['state_id']];orig=read(link['judgement']);rep=read(R/'judge_runs/review_repeat'/link['evidence_hash']/(item['alias']+'_'+key(item['state_id']))/'judgement.json')
  for field in ['feedback_response','state_use','repetition','documentation','termination','new_execution_issue','meaningful_progress']:
   a=orig[field].get('label',orig[field].get('labels'));b=rep[field].get('label',rep[field].get('labels'))
   if isinstance(a,list):a=','.join(sorted(a));b=','.join(sorted(b))
   reviews.append({'model':item['model'],'state_id':item['state_id'],'field':field,'original':a,'repeat':b,'agree':int(a==b)})
  for i in range(8):reviews.append({'model':item['model'],'state_id':item['state_id'],'field':f'R{i+1}','original':orig['rubrics'][i]['label'],'repeat':rep['rubrics'][i]['label'],'agree':int(orig['rubrics'][i]['label']==rep['rubrics'][i]['label'])})
 save_csv('judge_repeat_consistency.csv',reviews)
 agreement={f:{'agree':sum(x['agree'] for x in reviews if x['field']==f),'n':sum(x['field']==f for x in reviews)} for f in sorted({x['field'] for x in reviews})};atomic_json(O/'judge_repeat_summary.json',agreement)
 summary={'status':'complete','formal_states':299,'common_execution_states':common['states'],'generated_actions':2691,'judged_model_state_rows':len(rows),'unique_judged_evidence':len({x['evidence_hash'] for x in links}),'judge_review':'same-model independent-context repeat consistency; not independent validation','old_zerofail_run':False,'continuation_run':False,'local_gpu':1,'uncertainty':'exploratory DEV57, three training seeds, family cluster bootstrap descriptive only'};atomic_json(O/'SUMMARY.json',summary)
 def fmt(v):return 'NA' if v is None else f'{v:.1%}'
 lines=['# 第一阶段同状态动作比较报告','',f"全规则1358、DropR1、DropR2，各3个已有训练seed；299个冻结状态，2691个动作。所有9模型共同通过执行核验的状态为 **{common['states']}/299**。只使用GPU1，未做新训练、旧ZeroFail3或可选续跑。",'', '## 比较口径','', '以下主表仅用171状态主面板的共同可执行子集；补充E/R/D/S各32状态单独见CSV，不混入总体。固定前缀机会标签决定分母；unknown不删行，事件率及unknown上界见行为指标CSV。任务等权率先按每题可用且满足机会的状态平均，再在每seed内对有机会的题平均，最后三seed等权；机会计数、原始事件/分母同时公布。机会=uncertain的状态在 opportunity_sensitivity_metrics.csv 单列，并给出纳入敏感性估计。没有机会的题不凭空记零。若有共同执行缺失，这是可恢复子集的条件估计，不能冒充完整171状态估计。','', '| 主面板指标 | 全规则1358 | DropR1 | DropR2 |','| --- | ---: | ---: | ---: |']
 names={'effective_feedback':'有效反馈响应','grounded_progress':'有依据推进','state_contradiction':'状态矛盾','no_information_gain':'无信息增量重复','missing_required_spec':'必要规格缺失','premature_termination':'错误或过早交付','execution_error':'执行异常','no_code':'无代码','truncated':'输出截断','generated_tokens':'平均输出token'}
 for metric in METRICS:
  vals=[next(x['task_equal_rate'] for x in metrics if x['panel']=='primary' and x['group']==g and x['seed']=='all' and x['metric']==metric) for g in GROUPS]
  lines.append('| '+names[metric]+' | '+' | '.join(('NA' if v is None else f'{v:.1f}') if metric=='generated_tokens' else fmt(v) for v in vals)+' |')
 lines+=['','## 同seed配对方向','', '| 对比 | 指标 | 均值差 | seed15 / 16 / 17 | 家族bootstrap描述区间 |','| --- | --- | ---: | --- | --- |']
 for x in paired:
  if x['panel']=='primary' and x['metric'] in ['effective_feedback','grounded_progress','state_contradiction']:
   lines.append(f"| {x['contrast']} | {names[x['metric']]} | {fmt(x['task_equal_difference'])} | "+' / '.join(fmt(x[f'seed_{s}']) for s in SEEDS)+f" | {fmt(x['family_bootstrap_low'])} 至 {fmt(x['family_bootstrap_high'])} |")
 lines+=['','区间按19个任务家族聚类重采样；固定三个训练seed并保留逐seed方向，不把2691动作当作独立实验，不作多指标确认性显著判断。','', '## 官方evaluator：即时新增与破坏','', '| 主面板组别 | 类型 | 检查数 | 前缀→动作新增通过 | 丢失通过 | 相对全规则赢 / 输 |','| --- | --- | ---: | ---: | ---: | ---: |']
 for x in evtypes:
  if x['panel']=='primary' and x['seed']=='all':lines.append(f"| {x['group']} | {x['category']} | {x['checks']} | {x['gains_from_prefix']} | {x['losses_from_prefix']} | {x['wins_vs_full']} / {x['losses_vs_full']} |")
 lines+=['','before来自真实前缀的部分副作用；after是各自分支。评测在独立进程和数据库副本运行并核对加载内容；隐藏答案不进入policy/评委。沿用上一阶段97种家族×requirement映射，并区分空答案与实际答案。逐条新增/丢失及对全规则的配对变化在CSV中；信息读取动作的零即时增益不代表无价值。','', '## 评分校准与可确定边界','', '先完成8状态双重重放、逐token输入核对和隔离evaluator核对，再评分校准。初版发现普通首次文档发现被泛化为恢复，以及未查文档被误标为重复文档；统一澄清适用性后重评8状态，保留旧结果。正式卡片和协议在任何正式候选生成前冻结。见 [校准说明](calibration/PROTOCOL_CHANGES.md) 与 [接受记录](config/calibration_accepted.json)。','', '主评委为gpt-6.1-sol/high，工具关闭，凭证等值脱敏。随机预选72条采用同一评委的新上下文复核，因此只能说明重复一致性，不能称独立验证；各字段一致率见 analysis/judge_repeat_summary.json。单评委、8个校准状态覆盖有限，尤其不能把稀疏R5/R7强行排名。','', '本实验能比较固定历史下三组动作的反馈响应、状态使用、推进和代价，及官方即时细项增减。它不能单独证明R6训练正例是整题收益的原因，也不能用即时零增益否定查询价值；未做固定策略续跑，不能声称已测得长期动作后果。DEV57已经参与多轮探索；跨任务泛化需要另外验证。','', '## 可复查产物','', '- [逐动作行为](analysis/behavior_rows.csv)、[固定分母指标](analysis/behavior_metrics.csv)、[配对差与逐seed方向](analysis/paired_behavior_contrasts.csv)、[家族切片](analysis/behavior_families.csv)。','- [逐条evaluator](analysis/evaluator_checks.csv)、[对全规则逐条配对](analysis/paired_evaluator_checks.csv)、[八类汇总](analysis/evaluator_categories.csv)。','- [R1–R8全部P/F/U/N分布](analysis/rubric_distributions.csv)、[共同状态覆盖](analysis/state_coverage.csv)、[盲复核一致性](analysis/judge_repeat_consistency.csv)。','- [实时节点记录](EVENTS.jsonl)、[统计摘要](analysis/SUMMARY.json)。','']
 (R/'REPORT.md').write_text('\n'.join(lines))
 print(json.dumps(summary),flush=True)
if __name__=='__main__':main()
