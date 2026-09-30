# CFST第7d步：Mixed-1epoch的Dev57补充诊断评测

**57题全部完成。Mixed官方成功21/57（36.8%），本次低于原epoch5的23/57；净变化-2题。全部evaluator测试条件通过184/291（63.23%）。**

用户所称Mixup对应现有CFST-Mixed-1epoch：第6b步使用全部20条修复动作、每条学习一遍的adapter。“不训”对照为已经完成train90 SFT的原epoch5 adapter，即CFST追加训练之前的模型。

| 模型 | 官方成功 / TGC | 完整任务族 / SGC | evaluator全部条件通过率 | 逐题条件通过率平均值 |
| --- | ---: | ---: | ---: | ---: |
| 原epoch5（复用） | 23/57；40.4% | 4/19；21.1% | 206/291；70.79% | 71.79% |
| Action-1epoch（复用） | 31/57；54.4% | 6/19；31.6% | 215/291；73.88% | 76.08% |
| Mixed-1epoch（本次） | 21/57；36.8% | 3/19；15.8% | 184/291；63.23% | 67.22% |

总体evaluator通过率按全部通过条件数除以全部报告条件数计算；逐题平均值先算每题比例再平均。官方TGC使用整题success，部分条件通过不能替代整题成功。失败任务全部计入分母。

[57题evaluator完整明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/EVALUATOR_DETAILS.md) · [逐题对照CSV](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/evaluator_per_task_comparison.csv) · [三模型逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/three_model_per_task.csv) · [每个条件及失败trace](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/evaluator_assertions.jsonl)

## Mixed相对原epoch5的变化

新增成功10题、退步12题、净变化-2题；官方成功率变化-3.51个百分点，全部测试条件通过率变化-7.56个百分点。

- 新增成功：50e1ac9_2、4ec8de5_1、4ec8de5_3、3ab5b8b_2、df61dc5_1、23cf851_2、6bdbc26_1、6bdbc26_3、6171bbc_1、6171bbc_2。
- 退步：50e1ac9_3、fac291d_1、fac291d_2、4ec8de5_2、b119b1f_1、b119b1f_2、37a8675_1、df61dc5_3、23cf851_1、57c3486_2、57c3486_3、6c2c621_3。

相对Action-1epoch，本次Mixed新增成功4题、退步14题，净变化-10题。

## 如何解释

检查30题中Mixed为15/30，原epoch5为17/30。Dev57本次结果则为Mixed 21/57、原epoch5 23/57。两份任务集分别报告，不把检查30题上的下降预先推广到Dev57。

这是看到Action的Dev结果后按用户要求增加的诊断比较。单次固定种子结果说明本次57题上的实际表现，不能单独证明混合训练普遍更差，也不能单独把差异归因为能力分类；训练数据构成、条数与更新次数也不同。本次不重选分支，原第7b步选择和第7c步Action接受结果保持原样。

## 难度分组

| 难度 | 原epoch5 | Action-1epoch | Mixed-1epoch |
| --- | ---: | ---: | ---: |
| 1 | 14/30 | 18/30 | 16/30 |
| 2 | 9/24 | 12/24 | 5/24 |
| 3 | 0/3 | 1/3 | 0/3 |

## 协议、成本与核验

同一官方Dev57清单、运行器与配置：temperature=0、seed=100、32,000上下文、单次最多3,000输出tokens、每题最多50步、无reasoning parser、单进程逐题从初始环境运行。原epoch5结果核验后复用；Mixed权重与第6b步冻结权重一致，每题初始输入与原epoch5逐字一致。

5631项核验通过，2014个历史保护文件原哈希不变。日志兼容仅用于API日志写盘；本次无旧响应重放。Mixed模型调用1256次，输入tokens 13,257,130，输出tokens 108,780，6题触发上下文限制，耗时35.3分钟。

未训练模型、生成教师答案、调整超参数或刷新来源60题。所有失败保留逐步交互与官方报告。

## 文件

- EVALUATOR_DETAILS.md：57题任务要求、结果、所有官方条件及原始报告链接。
- evaluator_per_task_comparison.csv / three_model_per_task.csv：两模型与三模型逐题对照。
- evaluator_assertions.jsonl / official_candidate_evaluation.json：每个条件、失败trace与官方完整输出。
- summary.json / diagnostic_decision.json / validation.json：指标、诊断判断与核验证据。
- CFST-Mixed/：完整轨迹、配置、逐题评分、成功/失败清单。
- gained_task_ids.txt / regressed_task_ids.txt / family_comparison.csv：相对基线变化。

