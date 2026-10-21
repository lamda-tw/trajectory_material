"""Render auditable results and real contrasting cases from completed artifacts, no external calls."""
from experiment import *
from statistics_protocol import GROUPS,SEEDS
from public_payload import sanitize
from collections import defaultdict,Counter
import statistics as st
O=R/'analysis'

def csvread(name):
 with (O/name).open() as f:return list(csv.DictReader(f))
def number(value):return None if value in ('',None) else float(value)
def fmt(value,percent=True):
 v=number(value);return 'NA' if v is None else f'{v*100:.2f}%' if percent else f'{v:.2f}'
def diff(value):
 v=number(value);return 'NA' if v is None else f'{v*100:+.2f} pp'
def cell(value):return str(value).replace('|','/').replace('\n',' ')
def table(headers,values):return ['| '+' | '.join(headers)+' |','| '+' | '.join('---' for _ in headers)+' |']+['| '+' | '.join(cell(x) for x in r)+' |' for r in values]

def cases():
 selected={x['state_id']:x for x in rows('continuation_states.csv')};data_rows=csvread('continuation_common_rows.csv');scores=defaultdict(lambda:defaultdict(list))
 for x in data_rows:
  if x['panel']=='core' and x['horizon']=='12':scores[x['state_id']][x['group']].append(float(x['pass_fraction']))
 deltas={sid:st.mean(g['zerofail3'])-st.mean(g['random']) for sid,g in scores.items() if all(g[k] for k in GROUPS)}
 chosen=[]
 if deltas:
  for reason,sid in [('最大正向配对差',max(deltas,key=lambda s:(deltas[s],s))),('最小/负向配对差',min(deltas,key=lambda s:(deltas[s],s)))]:
   if sid not in [x[1] for x in chosen]:chosen.append((reason,sid))
 for sid,row in selected.items():
  if row['continuation_panel']=='discovery_bridge' and any(x['state_id']==sid for x in data_rows):chosen.append(('旧发现复查（单独解释）',sid));break
 atomic_json(O/'case_manifest.json',{'selection':'Descriptive cases selected AFTER outcomes: maximum/minimum core h12 ZeroFail3-Random difference, plus first frozen discovery bridge. Not representative evidence or new sampling.','states':[{'reason':reason,'state_id':sid,'core_difference':deltas.get(sid)} for reason,sid in chosen]})
 text=['# 同状态真实案例','', '案例按公开的事后选例规则挑出，用于解释统计，不代替全部状态。以下单步展示固定seed20261015；后续表按三个首步seed平均，三种接手策略分别列出。','']
 for reason,sid in chosen:
  row=selected[sid];d=data(row);public,_=sanitize({'task':d['public_task'],'history':d['history']});text+=['## '+reason,'',f"研究者状态ID：`{sid}`；在原轨迹第{row['before_step']}步之前分叉。",'', '公开任务：'+public['task']['instruction'],'']
  if public['history']:
   last=public['history'][-1];text+=['最近一步已执行代码：','```python',last['code'][:1800],'```','最近一步反馈摘录：','```text',last['observation'][:2200],'```']
  card=read(R/'judge_runs/cards'/key(sid)/'judgement.json');text+=['','固定前缀机会：'+ '；'.join(k+'='+card[k]['label']+'（'+card[k]['reason']+'）' for k in ['A_opportunity','B_opportunity','C_opportunity']), '']
  links={(x['model'],x['state_id']):x for x in read(O/'judgement_index.json')}
  for group in GROUPS:
   name=f'{group}__seed_20261015';ex=read(R/'results/executions'/name/f'{key(sid)}.json');clean,_=sanitize({'task':d['public_task'],'candidate':ex['candidate']});cand=clean['candidate'];j=read(links[name,sid]['judgement']);text+=['### '+group+' 的首步','','```python',cand['code'][:2400] or '# 无可执行Python代码','```','实际反馈摘录：','```text',cand['observation'][:1600],'```','行为判断：'+'；'.join(k+'='+j[k]['label']+'：'+j[k]['reason'] for k in ['relevant_gap_reduced','grounded_application','coverage_progress']),'']
  values=[]
  for receiver in [f'{g}__seed_20261015' for g in GROUPS]:
   vals=[]
   for group in GROUPS:
    yy=[float(x['pass_fraction']) for x in data_rows if x['state_id']==sid and x['horizon']=='12' and x['receiver']==receiver and x['group']==group];vals.append(fmt(st.mean(yy) if yy else None))
   values.append([receiver]+vals)
  text+=table(['共同接手策略','Random首步','Net3首步','ZeroFail3首步'],values)+['','表中是有限12步内、该状态上的官方检查通过比例，并非整题自然rollout成功率。代码/反馈长时只展示摘录，完整证据见results与analysis。','']
 (O/'CASES.md').write_text('\n'.join(text))

def main():
 phase=read(O/'PHASE1_SUMMARY.json');cont=read(O/'CONTINUATION_SUMMARY.json');metrics=csvread('behavior_metrics.csv');paired=csvread('paired_behavior_contrasts.csv');gates=csvread('mechanism_coverage_gates.csv');cpairs=csvread('paired_continuation_contrasts.csv');csumm=csvread('continuation_model_summary.csv');cats=csvread('continuation_evaluator_categories.csv');agreement=read(O/'judge_repeat_summary.json');opps=csvread('opportunity_and_state_coverage.csv')
 cases();lines=['# ZeroFail3、Random、Net3同状态机制实验报告','', '**实验结果报告。** 本文依据保存的同状态动作、真实执行、盲评和固定接手续跑生成；不新增训练。详细逐项数据与案例均可回查。','',f"正式状态129个，全部九模型共同可比较{phase['common_states']}个；首步生成{phase['generated_first_actions']}个、有效评分{phase['judged_model_state_rows']}行（{phase['unique_judged_evidence']}种不同证据）。续跑完成{cont['branches_completed']}/540分支，严格共同状态{cont['common_completed_states']}/20，其中核心{cont['core_common_states']}/18、发现复查{cont['discovery_common_states']}/2。仅使用物理GPU1。",'', '## 1. 这次具体在做什么','', '旧实验已经比较了三种评分选步策略训练后的自然整题表现。本次把某一步之前的历史消息、Python会话、数据库、文件、时间/随机状态及反馈固定下来，让九个已有模型分别决定下一步。相同训练seed配对，但三个seed是三个已训练权重，不是给同一个权重随机采样三次。状态来源同时包括三策略各43个；每个状态由全部九模型作答。','', '例如：历史已经拿到某个分页接口的规格，第一批对象也已读到。我们不再比较各模型自己碰巧走到的不同历史，而是让三组看同一段历史，观察它们重复查规格、继续取数据、合理使用已知对象还是直接提交。随后把这些首步分别交给同样三种固定接手策略，检验差异能否影响后续检查。','', '比较的是完整首步响应包（文本、代码、反馈及副作用），不是单独替换数据库或一行代码。接手策略固定为三组seed20261015；每种策略接手所有首步，不能让每组仅由自己续跑。','', '## 2. 状态、评价与校准','', '57个题目覆盖参照与A/B/C各24个定向状态分开报告，不把129状态混成新的DEV成功率。A检验缺必要规格时的信息获取；B检验资料和实际输入足够时的行动；C检验必要范围覆盖。仅用行动前公开证据冻结适用性卡片；机械候选不一定真的满足语义机会，no/uncertain不换样。','', '校准完成138状态逐token核验、9状态18次独立重放、只读/写入/写后异常三种隔离快照探针、27个校准动作和9个短续跑分支。写入探针证明快照运输和异常副作用保留，不代表测试通过数必须变化。评分使用用户明确授权的OpenAI GPT-6.1-sol/high，工具关闭，凭证等值脱敏；隐藏测试、未来原动作和模型组/seed不出站。校准语义审阅是研究助手审阅，不是独立人工金标准。','']
 gate_rows=[]
 for g in gates:
  panel=g['panel'];counts=Counter(x[panel[-1]+'_opportunity'] for x in opps if x['panel']==panel);gate_rows.append([panel,g['yes_states'],counts['no'],counts['uncertain'],g['families'],g['random_states']+'/'+g['net3_states']+'/'+g['zerofail3_states'],g['prespecified_coverage_gate']])
 lines+=table(['面板','共同可比较yes','全部no','全部uncertain','yes家族','来源R/N/Z的yes数','覆盖门槛通过'],gate_rows)+['','门槛为yes≥12、每来源≥3、家族≥6；这是预定报告门槛，不是功效保证。覆盖不足时只能作描述，不能把该场景没有测清楚解释成模型没有能力。','', '## 3. 三个主要行为指标','']
 values=[]
 for panel,metric in [('focus_A','relevant_gap_reduced'),('focus_B','grounded_application'),('focus_C','coverage_progress')]:
  for group in GROUPS:
   x=next(x for x in metrics if x['panel']==panel and x['group']==group and x['seed']=='all' and x['metric']==metric);values.append([panel,group,x['numerator']+'/'+x['eligible_rows'],x['unknown'],fmt(x['balanced_mean']),fmt(x['unknown_upper_balanced'])])
 lines+=table(['场景','组别','可确认正例/共同机会行','unknown','来源/题目等权正例率','含unknown上界'],values)+['','unknown保留在分母。正例率表示公开证据足以确认的行为事件；不把未知强行判FAIL。来源、题目和三个训练seed等权；相同完整前缀不会重复增加样本量。','']
 values=[]
 for x in paired:
  if x['metric'] in ['relevant_gap_reduced','grounded_application','coverage_progress'] and x['contrast'].startswith('zerofail3'):
   values.append([x['panel'],x['contrast'],diff(x['balanced_difference']),' / '.join(diff(x['seed_'+str(s)]) for s in SEEDS),diff(x['bootstrap_low'])+' 至 '+diff(x['bootstrap_high'])])
 lines+=table(['场景','对比','均值差','seed15 / 16 / 17','家族bootstrap描述区间'],values)+['','家族聚类bootstrap固定训练seed；仅保留所有预定来源/场景格非空的重采样，具体尝试/有效次数在CSV。DEV57已多轮分析，区间仅描述不确定性，不作多重比较确认性显著结论。','', '## 4. 行为收益要与代价一起看','']
 values=[]
 for metric in ['execution_error','redundant_known_information','unsupported_execution','state_contradiction','wrong_scope_action','premature_termination','generated_tokens']:
  vals=[next(x for x in metrics if x['panel']=='anchor' and x['group']==g and x['seed']=='all' and x['metric']==metric) for g in GROUPS];values.append([metric]+[fmt(v['balanced_mean'],percent=metric!='generated_tokens') for v in vals])
 lines+=table(['57题参照指标']+GROUPS,values)+['','具体状态使用矛盾与仅叙述不实分开记录；R1–R8完整P/F/U/N另表，不合成质量总分。更多文档、更多P、更少异常都不能单独解释性能；需同时看任务相关性、范围约束和后续结果。','', '## 5. 官方evaluator：即时效果与有限续跑','', '同一组官方断言在共同before、每组首步后h0、接手第4/12步或更早终态上执行。每题先算检查通过比例再平均；终态成功、完成API调用、逐项新增/丢失分别记录。只读动作即时检查不变不等于无价值。','']
 values=[]
 for horizon in ['4','12']:
  for group in GROUPS:
   metric=next(x for x in csumm if x['panel']=='core' and x['horizon']==horizon and x['group']==group and x['seed']=='all' and x['metric']=='pass_fraction');success=next(x for x in csumm if x['panel']=='core' and x['horizon']==horizon and x['group']==group and x['seed']=='all' and x['metric']=='task_success');values.append([horizon,group,metric['states'],fmt(metric['balanced_mean']),fmt(success['balanced_mean'])])
 lines+=table(['额外接手步预算','首步来源组','共同状态','官方检查Macro','官方goal-completion'],values)+['','以上仅是18个预选机制状态的条件效果，不是从头重跑DEV57的成功率。两例d4e9306发现复查不混入核心总体；12步未达成不等于继续无限步也会失败。正常模型错误、无代码和提前终止保留；基础设施缺失单列，不补零。','']
 values=[]
 for x in cpairs:
  if x['panel']=='core' and x['horizon']=='12' and x['metric']=='pass_fraction':values.append([x['contrast'],diff(x['balanced_difference']),' / '.join(diff(x['seed_'+str(s)]) for s in SEEDS),diff(x['bootstrap_low'])+' 至 '+diff(x['bootstrap_high'])])
 lines+=table(['核心h12首步对比','检查Macro差','首步seed15 / 16 / 17','描述区间'],values)+['','三种固定接手策略不是三个独立随机seed。各接手策略、状态来源、A/B/C及排除d4e9306的差值见[分层表](analysis/continuation_receiver_source_stage_slices.csv)，避免只挑某一种接手策略报优势。','']
 values=[[x['contrast'],x['category'],x['wins'],x['losses'],x['net']] for x in cats if x['panel']=='core' and x['horizon']=='12' and x['contrast'].startswith('zerofail3')]
 lines+=table(['核心h12对比','官方细项类别','新增胜出','配对失去','净差'],values)+['','八类由旧97种家族×requirement固定映射形成，答案区分期望null与实际值。断言相互相关，不能把表中的检查数当独立实验样本。完整逐项得失、h0到h12变化和不该修改的范围都保留在CSV。','', '## 6. 评分稳定性与真实案例','']
 lines+=table(['主要字段','适用复核数','一致率','测量门槛'],[[x['field'],x['n'],fmt(x['agreement']),x['primary_measurement_gate']] for x in agreement if x['field'] in ['relevant_gap_reduced','grounded_application','coverage_progress']])+['','54条预选复核采用同一评委的新上下文，只能说明重复一致性，不能证明准确率；原判和复核判均保留，没有多数投票改原判。主字段适用复核不足12条或一致率不足80%时，不据此支持强机制结论。','', '详见[真实动作与后续结果案例](analysis/CASES.md)。案例包含正向、最小/负向和旧发现复查，明确事后选例规则，不用几个好例子代替总体。','', '## 7. 能回答与不能回答什么','', '可以检验：在相同历史下，三种已训练模型是否表现出不同的信息获取、已有资料使用、范围覆盖行为；这些首步响应包在固定接手策略、有限步数下是否改善了官方细项，以及收益依赖哪些状态来源、seed、接手策略和任务家族。','', '只有当相应机会覆盖和测量稳定性足够、行为差异与后续差异方向相容时，才可把结果作为某个行为机制的支持。如果行为评分提高而后续持平/退化，就不能说该行为已解释成功率收益；如果只在一个接手策略或发现家族成立，则结论应限定在那里。','', '本实验不单独识别某条rubric、R6正例数量或某类文档训练样本的因果贡献，也不估计自然整题收益中有多少比例被该机制中介。旧训练策略同时改变内容、长度和监督token分布；固定历史只消除了本次动作比较中的历史差异。新任务泛化还需要独立任务验证。','', '集合审计保留真实请求参数、逐次API响应、打印JSON和本地Python变量中的对象ID。正式运行前增加被动响应记录，并用27个已保存校准动作核验观测和状态完全一致。逐次返回与打印内容分开：未打印数据仅用于本地审计，不发送给模型或评委。新ID仅指当前记录分支同查询范围内的新出现，不能解释为历史从未见过或全局完整率；官方范围/对应关系细项是独立后果证据。','', '## 8. 复查入口','', '- [全部逐动作行为](analysis/behavior_rows.csv)、[固定分母指标](analysis/behavior_metrics.csv)、[同seed配对](analysis/paired_behavior_contrasts.csv)、[来源/家族/子型](analysis/behavior_source_family_subtype_slices.csv)。','- [即时逐检查](analysis/evaluator_checks.csv)、[即时配对得失](analysis/paired_evaluator_checks.csv)、[八类即时汇总](analysis/evaluator_categories.csv)、[R1–R8分布](analysis/rubric_distributions.csv)。','- [全部可用续跑](analysis/continuation_all_available_rows.csv)、[共同状态续跑](analysis/continuation_common_rows.csv)、[后续逐检查配对](analysis/paired_continuation_evaluator_checks.csv)、[八类后续得失](analysis/continuation_evaluator_categories.csv)。','- [评分一致性](analysis/judge_repeat_summary.json)、[机会与覆盖](analysis/opportunity_and_state_coverage.csv)、[请求审计](analysis/api_request_ledger.csv)、[逐次API返回与对象ID](analysis/api_response_ledger.csv)、[可观察集合审计](analysis/visible_collection_ledger.csv)。','- [运行README](README.md)、[节点日志](EVENTS.jsonl)、[校准审阅记录](calibration/SEMANTIC_REVIEW.md)、[冻结协议接受记录](config/calibration_accepted.json)。','']
 (R/'REPORT.md').write_text('\n'.join(lines));atomic_json(O/'SUMMARY.json',{'status':'computed_report_ready','phase1':phase,'continuation':cont,'report':'REPORT.md','requires_researcher_synthesis_review':True,'physical_gpu':1})
 print('Detailed tables and contrasting cases written; researcher synthesis review still required.',flush=True)
if __name__=='__main__':main()
