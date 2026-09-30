# CFST第7c步：Action-1epoch的Dev57官方评测

**57题全部完成并通过核验。CFST-Action-1epoch官方成功31/57（54.4%），全部evaluator测试条件通过215/291（73.88%）。**

| 指标 | 原epoch5（核验后复用） | CFST-Action-1epoch |
| --- | ---: | ---: |
| 官方任务成功数 / TGC | 23/57；40.4% | 31/57；54.4% |
| 官方完整成功任务族 / SGC | 4/19；21.1% | 6/19；31.6% |
| 全部evaluator测试条件通过比例 | 206/291；70.79% | 215/291；73.88% |
| 57题各自测试通过率的平均值 | 71.79% | 76.08% |

**百分比口径：** 总体测试条件通过率＝全部通过条件数÷全部报告条件数；逐题平均通过率先计算每题比例再对57题平均。官方TGC要求整题成功；这些指标含义不同，部分条件通过不能当作整题成功。所有分母使用官方实际输出，不丢弃失败任务或失败条件。

**逐题明细：** [57题evaluator完整报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/EVALUATOR_DETAILS.md) · [逐题对照CSV](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/evaluator_per_task_comparison.csv) · [每条测试条件及完整失败追踪](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/evaluator_assertions.jsonl) · [官方完整JSON](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/official_candidate_evaluation.json)

## 相对原epoch5的变化

新增成功14题，退步6题，净变化+8题。

- 新增成功：50e1ac9_2、530b157_1、4ec8de5_1、b119b1f_3、3ab5b8b_2、df61dc5_2、23cf851_2、6bdbc26_1、6bdbc26_3、6171bbc_2、6171bbc_3、6c2c621_1、6c2c621_2、4fab96f_2。
- 退步：50e1ac9_1、b119b1f_1、b119b1f_2、37a8675_1、df61dc5_3、23cf851_1。

**冻结规则的决定：通过预先确定的接受门槛。** 检查30题净增2题已经满足第一项；Dev57要求成功数不低于23题，本次为31题。测试条件通过百分比作为详细诊断报告，不替换这个接受标准。

本次只评测此前检查30题已经选出的Action-1epoch，不使用Dev57重新选择State/Mixed、不调整参数、不训练或生成教师答案，也不自动刷新来源60题。

## 难度分组

| 难度 | 原epoch5成功/总数 | Action-1epoch成功/总数 |
| --- | ---: | ---: |
| 1 | 14/30 | 18/30 |
| 2 | 9/24 | 12/24 |
| 3 | 0/3 | 1/3 |

## 协议、成本与核验

使用同一官方Dev57清单、同一运行器与配置：temperature=0、seed=100、32,000上下文、单次最多3,000输出tokens、每题最多50步、无reasoning parser、单进程逐题从初始环境运行。Action权重与第6b步冻结权重完全一致。

原epoch5的1,014次历史请求已核验，官方成功23/57、测试条件通过206/291；本次每题首条输入与同题基线逐字一致。4991项核验通过，1622个历史保护文件保持原哈希。日志序列化兼容只影响API日志写盘，本次无旧响应重放。

Action本次模型调用1012次，输入tokens 10,315,090，输出tokens 95,427；触发上下文限制9题，运行耗时31.1分钟。对应逐题终止原因、测试计数和失败条件均在CSV与原始轨迹中保留。

单次固定种子的评测只用于执行本轮预先约定的接受检查；结果不单独证明能力分类合理。若今后依据这些Dev结果修订方法，应将其视为开发证据。

## 文件

- EVALUATOR_DETAILS.md：57题对照表、任务要求、所有官方测试条件及原始报告链接。
- evaluator_per_task_comparison.csv / task_comparison.csv：每题通过数、失败数、百分比、任务成功、相对基线变化。
- evaluator_assertions.jsonl：候选所有测试条件的结果、原始标签和失败trace。
- family_comparison.csv：19个任务族对比。
- summary.json / acceptance.json / validation.json：汇总、冻结接受判断及完整核验。
- CFST-Action/：完整轨迹、日志、官方评分、逐题索引、成功/失败清单。
- baseline/：复用结果及逐题索引；baseline_reuse_validation.json记录复用证据。

