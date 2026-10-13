"""Render the completed experiment from audited artifacts; no inference calls."""
from pathlib import Path
import json,collections
R=Path(__file__).resolve().parents[1]
OLD=R.parents[1]/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full'
def read(p):return json.loads(p.read_text())
def pct(x):return '—' if x is None else f'{100*x:.2f}%'
def num(x):return '—' if x is None else f'{x:.3f}'
def duration(s):return f'{int(s//3600)}小时{int(s%3600//60)}分{s%60:.1f}秒'
def table(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(v).replace('|','\\|').replace('\n',' ') for v in row)+' |' for row in rows])
s=read(R/'analysis/summary.json');o=read(OLD/'analysis/summary.json');m=read(R/'analysis/report_metrics.json');v=read(R/'analysis/rubric_validity/statistics.json');c=read(R/'analysis/configuration_comparison.json');t=read(R/'TIMING.json');term=read(R/'analysis/terminal_submission_analysis.json');manual=read(R/'review/manual_review.json');conclusion=read(R/'review/report_conclusions.json')
assert s['trajectories']==540 and s['steps']==11254
lines=['# AppWorld 全量轨迹评分：英文 v6 / GPT-6.1 sol','',conclusion['summary'],'','## 实验配置与边界','',
'同一批 Qwen3-8B 原始轨迹，共 540 条、11,254 步、90,032 个 rubric 标签；90 个任务、30 个任务族，每任务 6 次运行。官方成功 39 条、失败 501 条。540 份预处理输入与中文全量实验逐字节相同；不向裁判提供官方成功标记或旧评分。每条轨迹重新调用裁判，没有复用 pilot 评分。','',
'本轮使用冻结的英文 v6 format prompt、GPT-6.1 sol、high reasoning，初始/最大并行均为 8。标签仍为 P（满足）、F（明确违反）、U（适用但证据不足）、N（不适用）。输出每步八字符标签与一条最多 60 字符的简短依据。接收首次通过 schema 的结果；仅对技术/格式失败重试，不根据标签优劣挑选结果。','',
'与旧中文 v5 / GPT-5.6 sol 相比，语言、规则版本、裁判模型同时变化。因此以下是以质量为目标的配置比较，不能将差异单独归因于英文或新模型，也不是严格的语言消融。相同英文 prompt 的 pilot 对照也只提供跨模型一致性，不能替代准确率。','',
'评分经远程 Codex 执行，没有加载本地 GPU 模型，也未修改正在训练的 LoRA、原始轨迹或旧结果。输入沿用已有预处理：有凭据等值替换，但不声称已完整匿名化。','',
'## 时间、调用与完整性','',table(['指标','本轮英文 v6 / 6.1','旧中文 v5 / 5.6'],[
['评分开始',t['scoring_started_at'],read(OLD/'TIMING.json')['scoring_started_at']],['评分结束',t['scoring_finished_at'],read(OLD/'TIMING.json')['scoring_finished_at']],['评分墙钟时间',duration(s['scoring_wall_seconds']),duration(o['scoring_wall_seconds'])],['实际调用次数',s['attempts'],o['attempts']],['首次调用有效',str(sum(x['status']=='valid' and x['attempt']==1 for x in read(R/'analysis/attempts.json')))+'/540',str(sum(x['status']=='valid' and x['attempt']==1 for x in read(OLD/'analysis/attempts.json')))+'/540'],['无效尝试',s['invalid_attempts'],o['invalid_attempts']],['有效调用平均延迟（秒）',num(s['accepted_latency_mean_seconds']),num(o['accepted_latency_mean_seconds'])],['有效调用中位延迟（秒）',num(s['accepted_latency_median_seconds']),num(o['accepted_latency_median_seconds'])],['未报告 token 的尝试',s['unreported_usage_attempts'],o['unreported_usage_attempts']]]),'',
'7次无效尝试包括5次输出格式问题和2次服务容量不足。实际并发调整如下；稳定后恢复到8，模型始终相同。','',table(['时间（+08:00）','并发上限','原因'],[[e['at'],e['limit'],e['reason']] for e in (json.loads(x) for x in (R/'logs/scoring_events.jsonl').read_text().splitlines()) if e['event']=='concurrency_changed']),'',
'墙钟时间从首次正式评分子进程启动到 540 条全部有效，包含重试、等待、校验和落盘；不含启动前的模型可用性探测、准备及评分后的分析。原始证据预读与评分并行，不另加一段串行耗时。旧实验先以 2→4→8 并行递增，本轮从 8 开始，因此耗时也不是纯模型速度比较。详细计时见 TIMING.json 与 EVALUATION_TIMING.json。','',
'本轮调用报告的 token 使用：`'+json.dumps(s['reported_token_usage'],ensure_ascii=False)+'`。包含已上报的失败尝试；cached/reasoning 通常是对应 token 项的子集，不应再相加。没有完整价格/未上报用量时不估算费用。','',
'已核查源文件与输入哈希、冻结 prompt/config/schema、完整 step 顺序、原始响应未改写、首次有效结果接收及裁判无工具调用。机器核验见 [validation.json](analysis/validation.json)。','',
'## 标签分布','', 'R1执行有效性；R2证据与覆盖；R3状态与数据保真；R4决策逻辑与计算；R5动作与实际效果；R6反馈与恢复；R7终止与交付；R8权限与交互协议。','',
'下图沿用旧图口径：分别在官方成功/失败轨迹的全部步骤内归一化 P/F/U/N；成功组 501 步，失败组 10,753 步。N 不等于失败，图中的全部步骤 P 占比也不等于适用步骤通过率。','',
'![Rubric distribution](analysis/figures/rubric_distribution.png)','',table(['规则','P','F','U','N','适用率 PFU/全部'],[[f'R{i}',*[s['label_counts'][f'R{i}'].get(x,0) for x in 'PFUN'],pct(1-s['label_counts'][f'R{i}'].get('N',0)/s['steps'])] for i in range(1,9)]),'',
'至少一项 F 的步骤 '+str(m['step_flags']['any_F'])+'；仅 R8 为 F 的步骤 '+str(m['step_flags']['only_R8_F'])+'；八项均无 F/U 的步骤 '+str(m['step_flags']['no_F_or_U'])+'。这些计数不是训练数据质量的独立验证。','',
'## 与中文历史评分的对应变化','',
'逐一对齐相同的 90,032 个单元，变化 '+str(c['changed_cells'])+' 个。下表一致率仅表示配置间稳定性，N/N 较多时会抬高全单元一致率；另列至少一方适用的单元。','',table(['规则','全部一致率','至少一方适用时一致率','跨 F/非F 边界变化'],[[k,pct(x['same']/x['cells']),pct(x['same_either_applicable']/x['either_applicable']) if x['either_applicable'] else '—',x['F_boundary_flips']] for k,x in c['by_rubric'].items()]),'',
'完整 PFUN 转移矩阵与目标案例逐项结果见 [configuration_comparison.json](analysis/configuration_comparison.json)，变化单元见 [CSV](analysis/label_changes_vs_chinese.csv)。','',
'同一英文 format prompt 的跨模型比较：','',table(['pilot 集合','对齐单元','一致率'],[[k,x['cells'],pct(x['agreement'])] for k,x in c['english_prompt_judge_comparison'].items()]),'','## 评分质量核验','',
'先冻结 prompt，再按预先固定的同一组 12 条、176 步阅读原始证据；本轮用于语义复核的有效标签在全量评分结束后才检查。复核者是本对话助手，已知历史案例，不是独立人工金标。全轨迹逐维复核与有选择的边界检查分开报告，不把命中率解释为总体准确率。','',table(['机械检查','本轮匹配','旧中文匹配'],[[k,str(x['matches'])+'/'+str(x['total']),str(o['mechanical_checks'].get(k,{}).get('matches','—'))+'/'+str(o['mechanical_checks'].get(k,{}).get('total','—'))] for k,x in s['mechanical_checks'].items()]),'',
'机械检查覆盖可直接核验的执行异常、正常执行、只读无业务修改和额外非空代码块，不是八项语义的完整金标。','',table(['预先记录的案例集','本轮匹配','旧中文匹配'],[[k,str(x['new_matches'])+'/'+str(x['n']),str(x['old_matches'])+'/'+str(x['n'])] for k,x in c['known_checks'].items()]),'',
'legacy_full_boundary_checks的48项专门取自旧版错误/争议，旧版0/48是选样构造结果，不是旧版总体表现。以上案例集有重叠，且包含争议边界，不汇总成一个准确率。旧 v5 与 v6 规则语义也有差异，最终以逐案证据复核为准。','',conclusion['manual_review'],'',table(['规则','本轮明确错误','本轮争议项','旧中文明确错误','旧中文争议项'],[[f'R{i}',sum(x['rubric']==f'R{i}' and x['kind']=='clear_error' for x in manual['findings']),sum(x['rubric']==f'R{i}' and x['kind']=='debatable' for x in manual['findings']),sum(x['rubric']==f'R{i}' and x['kind']=='clear_error' for x in read(R/'review/legacy_chinese_manual_review.json')['findings']),sum(x['rubric']==f'R{i}' and x['kind']=='debatable' for x in read(R/'review/legacy_chinese_manual_review.json')['findings'])] for i in range(1,9)]),'',
'[逐案复核记录](review/MANUAL_REVIEW.md) · [固定 12 条原始标签](review/SEMANTIC_SAMPLE_RESULTS.md) · [查看本轮标签前的原始证据笔记](review/raw_evidence_notes.json)','',
'## R5、R7 的样本量与 R8 的解释','',conclusion['sparse_and_protocol'],'',
'## 相关性与适用覆盖','',
'令 a=成功轨迹中的 P 步数，b=失败轨迹中的 P 步数，c=成功轨迹中的 F 步数，d=失败轨迹中的 F 步数，则：','',
'$$\\phi=\\frac{ad-bc}{\\sqrt{(a+b)(c+d)(a+c)(b+d)}}.$$','',
'这里只在 P/F 上计算，排除 U/N。适用率单独用 (P+F+U)/全部计算；通过率另列 P/(P+F)。步级观察相关，不能把 11,254 步当作独立样本；区间按 30 个任务族聚类 bootstrap 5,000 次，固定 seed=20261013。部分稀疏重采样可能分母为零，区间只使用有限值，并在 statistics.json 记录有效重采样次数。区间是探索性区间，没有多重检验校正。','',table(['规则','适用步骤','适用轨迹','成功P/(P+F)','失败P/(P+F)','φ','95%任务族区间'],[[x['rubric'],x['applicable_steps'],x['applicable_trajectories'],pct(x['success_pass_P_over_PF']),pct(x['failure_pass_P_over_PF']),num(x['phi_PF']),'['+', '.join(num(a) for a in x['phi_family_bootstrap_ci'])+']'] for x in v['rubrics']]),'',
'![Coverage and association](analysis/rubric_validity/coverage_association.png)','',
'另按每条轨迹 P/(P+F+U) 计算，在同一任务内比较成功/失败轨迹，再对有两类结果且规则适用的任务等权平均：','',table(['规则','匹配任务数','成功减失败','95%任务族区间'],[[x['rubric'],x['within_task_matched_tasks'],num(x['within_task_pass_difference']),'['+', '.join(num(a) for a in x['within_task_difference_ci'])+']'] for x in v['rubrics']]),'',
'相关性不验证标签本身正确，也不证明用来筛选 SFT 会提升模型。全轨迹裁判可受到后续信息影响；U 的出现可能与成败相关；成功只有 39/540 条。R5/R7 低覆盖主要与规则适用事件稀少有关，应同时看适用轨迹/任务族数和区间宽度。规则间 P/F 相关性见 statistics.json 的 pairwise。','',
'## 终止与官方成败','',table(['末步 R7','官方成功','官方失败'],[[k,x['success'],x['failure']] for k,x in s['terminal_R7']['table'].items()]),'','末步 P/F 子集与官方成败的表面一致率为 '+pct(s['terminal_R7']['PF_agreement_with_official'])+'，该子集有 '+str(s['terminal_R7']['decided_PF'])+' 条；U/N 未折算为失败。全数据一律预测失败已有 501/540=92.78%，且分母不同，不能据此宣称裁判准确率。','',
'R7 衡量交付/终止是否如实且有依据，诚实报告失败也可为 P，不能把全部 R7=P 当作任务成功预测。按末步实际 complete_task 参数分类后，声明成功且 R7=P 的 '+str(term['success_submission_R7_P']['total'])+' 条中，官方成功 '+str(term['success_submission_R7_P']['official_successes'])+' 条（'+pct(term['success_submission_R7_P']['official_success_fraction'])+'）。官方失败但 R7=P 的具体案例、诚实失败报告和未知动态参数分类见 [终止分析](analysis/terminal_submission_analysis.json)。官方只提供汇总结果，不能据此臆造隐藏断言失败的原因。','',
'旧版声明成功且R7=P为26/35（74.29%）官方成功，本轮为19/21（90.48%）；但39条官方成功中获P的覆盖由26/39降为19/39，另外20条为U。较高的条件精确率伴随更多弃权，不能单独解释成总体准确率提升。20/22条官方失败但末步R7=P是明确status=fail的诚实终止；其余2条是多点赞未来歌曲却仍判交付P的边界案例，见补充复核。','',
'## 候选步骤与对筛选的影响','', '沿用旧分析规则提取的候选记录共 '+str(m['candidates']['records'])+' 条，覆盖 '+str(m['candidates']['distinct_steps'])+' 个不同步骤；分类计数为 `'+json.dumps(m['candidates']['by_kind'],ensure_ascii=False)+'`。候选可能重叠，尚未赋训练权重。执行恢复并不抹去业务错误：恢复候选中仍有业务维度 F 的记录为 '+str(m['candidates']['recovery_with_business_F'])+' 条。完整候选保存在 analysis/step_candidates.jsonl。','',
'仅作诊断：在原 SFT 实验冻结的同一 5,234 步 common_pool 中，用新标签应用原门槛 R1=P、R2–R6∈{P,N}、R7=N，暂不约束 R8。未改动训练数据或启动新训练。','',table(['门槛','旧标签通过步骤数','新标签通过步骤数'],[[name,c['common_pool_selection']['counts']['old'][key],c['common_pool_selection']['counts']['new'][key]] for name,key in [('原门槛','base'),('原门槛 + R8=P','plus_R8P'),('原门槛 + R5=P','R5P'),('原门槛 + R5=P + R8=P','R5P_R8P')]]),'',
'逐个取消 R2–R6 门槛后的规模：`'+json.dumps(v['selection']['pool_without_one_gate'],ensure_ascii=False)+'`。不能仅因某项删除后样本变多或相关性弱就认定它无用；R5 的实际写入质量与 R7 的交付真实性仍有独立语义价值。','',
'## 结论与下一步','',conclusion['recommendation'],'',
'## 产物','',
'- [冻结英文 prompt](assets/prompt_v6_en.txt) 与 [配置](judge_config.json)\n- [全量评分 JSONL](analysis/scored_trajectories.jsonl) 与 [逐步标签 CSV](analysis/step_labels.csv)\n- [汇总](analysis/summary.json)、[相关性统计](analysis/rubric_validity/statistics.json)、[逐调用记录](analysis/attempts.json)\n- [评分计时](TIMING.json)、[评估计时](EVALUATION_TIMING.json)\n- runs/scoring/<trajectory_id>/ 保存原始输入、请求、每次尝试和首次有效响应。','']
(R/'REPORT.md').write_text('\n'.join(lines))
print('REPORT.md rendered from completed scoring, analyses and semantic review.')
