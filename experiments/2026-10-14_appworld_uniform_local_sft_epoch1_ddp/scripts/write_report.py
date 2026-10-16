from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def dur(x):x=round(x);return f'{x//3600}小时{x%3600//60}分{x%60}秒'
s=read('analysis/summary.json');r=s['results'];d=s['selection'];c=s['comparisons']['rubric_epoch1'];n=r['random_epoch1']['successes'];train=s['training'];epoch=s['epoch'];delta=c['delta_tasks']
verdict=f'随机组成功{n}/57，'+('低于' if delta<0 else '高于' if delta>0 else '等于')+f'rubric组13/57，净变化{delta:+d}题。'
if delta<0:interpret='本次观察支持现有rubric数据管线在固定步骤预算下比随机抽样更有效，但只有一次抽样和训练，且token、上下文及部分响应mask未完全匹配，不能把差异解释为rubric标签的独立因果贡献。'
elif delta>0:interpret='本次没有观察到rubric筛选优于随机抽样；随机结果更高。这个结果说明需重新审视筛选是否损失了有用步骤或改变了行为分布，不能事后换随机seed来得到有利结果。'
else:interpret='本次成功题数相同，未观察到rubric筛选的净优势。应同时查看逐题获益/退化，不能把总分相同解释为两个策略在行为上相同。'
rows='\n'.join(f"| {name} | {r[key]['successes']}/57 | {100*r[key]['TGC']:.2f}% | {r[key]['steps']} |" for key,name in [('base','原始Qwen3-8B（已有同协议）'),('rubric_epoch1','rubric新配方第1轮（已有）'),('random_epoch1','本次Random第1轮')])
term='\n'.join(f"| {name} | {s['diagnostics'][key]['termination_counts'].get('no_python_code',0)} | {s['diagnostics'][key]['termination_counts'].get('step_limit',0)} | {s['diagnostics'][key]['termination_counts'].get('context_limit',0)} | {s['diagnostics'][key]['completion_api_but_failed']} |" for key,name in [('rubric_epoch1','rubric'),('random_epoch1','random')])
ci=c['task_family_bootstrap_95_interval'];refinput=sum(x['input_tokens'] for x in read('references/rubric_training_metrics.json')[:1220])
report=f"""# 随机步骤：一轮双卡LoRA与rubric第一轮对照

**{verdict}** {interpret}

## 结果

| 模型 | 官方成功题数 | TGC | 总行动步数 |
| --- | ---: | ---: | ---: |
{rows}

方向统一按random减rubric计算：random新增成功{len(c['new_successes'])}题、退化{len(c['regressions'])}题。新增：`{', '.join(c['new_successes']) or '无'}`；退化：`{', '.join(c['regressions']) or '无'}`。差值{100*c['delta_TGC']:+.2f}个百分点，任务家族bootstrap 95%区间为[{100*ci[0]:+.2f}, {100*ci[1]:+.2f}]个百分点；逐题McNemar仅作描述，p={c['descriptive_mcnemar_p']:.4f}，同家族题目不独立，不能单靠此p值宣布稳定胜出。

[逐题结果]({R/'analysis/task_comparison.csv'}) · [完整统计]({R/'analysis/summary.json'})

| 模型 | 无代码终止 | 50步上限 | 上下文上限 | 调用完成API但官方失败 |
| --- | ---: | ---: | ---: | ---: |
{term}

## 数据和公平性

从同一批540条原始Qwen3轨迹的5,234个公共候选步骤内抽样。公共过滤与rubric原实验一致：执行无异常、单个闭合Python代码块、无生成截断、长度合规、去重、排除包含完成提交的代码块；不使用rubric标签和最终官方成败选择随机步骤。成功与失败轨迹均有资格。

抽样seed=20261014，每题无放回均匀随机；90题分别匹配rubric步骤数量，共2,440步。保留参考数据每个行位置的任务身份，并复用第一轮打乱索引，实际1,220次更新的任务配对逐一匹配。与rubric重合{d['shared_selected_steps']}步，符合独立随机抽样；不刻意排除高分步骤。随机组覆盖{d['source_trajectories_represented']}条原轨迹。

| 预算 | Rubric参考组 | Random本次 |
| --- | ---: | ---: |
| 步骤 | 2,440 | 2,440 |
| 更新 | 1,220 | 1,220 |
| 监督token | 196,608 | {d['supervised_tokens']:,} |
| 训练输入token | {refinput:,} | {d['input_tokens']:,} |
| 部分监督响应 | 88 | 0 |

因此本实验匹配step和更新预算，不是等token、等上下文成本或等mask实验。Random全部监督原始完整响应；Rubric沿用既有88条配额部分响应，未为了凑token截断随机动作。任务配额本身来自rubric组，因此结论是条件于该任务分配的筛选策略比较。标签分布只在抽样后描述，见 [SELECTION_SUMMARY.json]({R/'data/SELECTION_SUMMARY.json'})。

全部2,440条输入均重建行动前历史并与保存token逐项比较；原始响应token未改写，当前/未来observation未进入输入。train90与DEV57的题目和任务家族均不重叠，无新外部模型评分或动作替换。

## 训练

从原始Qwen3-8B全新LoRA初始化，初始张量哈希与rubric组完全一致。训练seed=20260921，r8/alpha16/dropout0，注入q/k/v/o/gate/up/down，AdamW固定2e-4、wd0、无梯度裁剪；bf16/SDPA/梯度检查点。每卡一个步骤，全局两个步骤，各步骤token平均loss再取均值。每个目标恰好训练一次，未加载以前的adapter或optimizer。

最长两条实际样本预检独立完成，probe权重不进入正式训练。训练数学目标通过双进程小模型标准CE/梯度对照，最终两卡权重相同；最终adapter与epoch1检查点从磁盘加载后张量一致。发生基础设施异常时仅允许按固定配置恢复，不重采样数据。

本轮平均步骤CE={epoch['mean_step_loss']:.6f}，token加权CE={epoch['token_weighted_loss']:.6f}。不同组训练样本不同，不能把训练loss高低当作数据质量或DEV能力排名。

![一轮loss]({R/'analysis/loss_epoch1.png'})

浅蓝为每次更新loss，红线为当前及此前49次更新的滑动平均；原始尖峰完整保留。 [PDF]({R/'analysis/loss_epoch1.pdf'}) · [CSV]({R/'analysis/loss_history.csv'})

## 验证与用时

复用同一agent prompt、runtime、官方测试：thinking关闭，temperature0、seed100，最多50步、32,000上下文、每步最多3,000生成token、3个隔离worker。一轮训练结束后仅运行最终DEV57；已完成任务的正常失败不重采样，基础设施异常不填为失败。

正式训练{dur(train['training_wall_seconds'])}；DEV57 {dur(r['random_epoch1']['elapsed_current_invocation_seconds'])}。数据整理、最长样本probe和事后分析分别记录，不计入正式训练时间。完整阶段记录见 [TIMING.json]({R/'TIMING.json'})。

## 结论范围

{interpret} 本轮只运行一个抽样seed及一个训练seed；一轮是在此前DEV观察后选出的，不能作为从未使用过的独立验证。没有重训rubric组，也没有改动原v5评分。单轮对比不足以宣称所有rubric筛选都有效或无效，不能隔离R1—R8各维度的因果贡献。若需要进一步确认，应预先固定协议，在更多独立抽样/训练seed或未用于选择配置的数据上验证，而不是按本次DEV反复修改筛选条件。

[保存模型]({R/'training/uniform/epoch_01_adapter'}) · [冻结方案]({R/'PLAN.md'}) · [配置]({R/'config/training.json'}) · [完成检查]({R/'COMPLETION_CHECK.json'})
"""
(R/'REPORT.md').write_text(report);print(R/'REPORT.md')
