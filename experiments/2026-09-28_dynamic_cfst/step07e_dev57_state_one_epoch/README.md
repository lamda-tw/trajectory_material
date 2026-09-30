# CFST第7e步：State-1epoch的Dev57补充诊断评测

**57题全部完成。State官方成功25/57（43.9%），本次高于原epoch5的23/57；净变化+2题。全部evaluator测试条件通过179/291（61.51%）。**

本次使用第6b步的CFST-state adapter：12条状态构建修复动作各训练一遍，共6次参数更新。原模型指Qwen3-8B + train90 LoRA epoch5，即追加CFST训练之前的模型。其余三个模型的Dev结果经核验复用。

| 模型 | 检查30题成功 | Dev57成功 / TGC | 完整任务族 / SGC | evaluator全部条件通过率 | 逐题条件通过率平均值 |
| --- | ---: | ---: | ---: | ---: | ---: |
| 原epoch5 | 17/30 | 23/57；40.4% | 4/19；21.1% | 206/291；70.79% | 71.79% |
| State-1epoch | 17/30 | 25/57；43.9% | 3/19；15.8% | 179/291；61.51% | 66.03% |
| Action-1epoch | 19/30 | 31/57；54.4% | 6/19；31.6% | 215/291；73.88% | 76.08% |
| Mixed-1epoch | 15/30 | 21/57；36.8% | 3/19；15.8% | 184/291；63.23% | 67.22% |

总体evaluator通过率＝全部通过条件数÷全部报告条件数；逐题平均值先算每题比例再平均。官方TGC使用整题success，部分条件通过不能替代整题成功。失败任务全部计入分母。

[57题evaluator完整明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/EVALUATOR_DETAILS.md) · [State与原模型逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/evaluator_per_task_comparison.csv) · [四模型逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/four_model_per_task.csv) · [每个条件及失败trace](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/evaluator_assertions.jsonl)

## State相对原epoch5的变化

新增成功9题、退步7题、保留原成功16题，净变化+2题；官方成功率变化+3.51个百分点，全部测试条件通过率变化-9.28个百分点。

- 新增成功：4ec8de5_3、3ab5b8b_2、3ab5b8b_3、df61dc5_1、23cf851_2、6bdbc26_1、6bdbc26_3、6c2c621_1、6c2c621_2。
- 退步：50e1ac9_1、fac291d_2、37a8675_1、23cf851_3、57c3486_1、57c3486_3、6c2c621_3。

## 为什么整题成功增加，条件得分反而下降

| 任务组 | 题数 | 原epoch5通过条件 | State通过条件 | 通过条件变化 |
| --- | ---: | ---: | ---: | ---: |
| 两者均成功 | 16 | 72/72 | 72/72 | +0 |
| 原失败→State成功 | 9 | 26/43 | 43/43 | +17 |
| 原成功→State失败 | 7 | 30/30 | 17/30 | -13 |
| 两者均失败 | 25 | 78/146 | 47/146 | -31 |

尤其是两者都未整题成功的25题，State通过条件由78降到47，这部分变化不会体现在整题成功数里。新增成功和退步题的得失合并后，总条件通过数仍下降。因此本次应描述为：整题成功小幅增加，但条件完成程度下降，不能笼统说与原模型表现相同。

## 如何解释

检查30题中State与原epoch5都是17/30；Dev57本次State是25/57，原epoch5是23/57。是否接近应结合实际差距和逐题得失理解，不能从检查30题总分相同预先认定Dev也会相同。

本次没有预先规定“差不多”的容许范围，因此报告实际差值，不把单次结果称为统计等效。四模型结果是当前固定种子实验的观察；它不能单独证明分类有效，或把分支差异完全归于某项能力。三个包的数据内容、条数和更新次数也不同。

本次是在Action、Mixed结果完成后按用户要求追加的诊断。保留原第7b步候选选择和第7c步Action接受记录，不依据新增Dev结果改参数或重选分支。

## 难度分组

| 难度 | 原epoch5 | State-1epoch | Action-1epoch | Mixed-1epoch |
| --- | ---: | ---: | ---: | ---: |
| 1 | 14/30 | 18/30 | 18/30 | 16/30 |
| 2 | 9/24 | 7/24 | 12/24 | 5/24 |
| 3 | 0/3 | 0/3 | 1/3 | 0/3 |

## 协议、成本与核验

同一官方Dev57清单、运行器与配置：temperature=0、seed=100、32,000上下文、单次最多3,000输出tokens、每题最多50步、无reasoning parser、单进程逐题从初始环境运行。State权重与第6b步冻结权重一致，每题初始输入与原epoch5逐字一致。

5967项核验通过，2454个历史保护文件原哈希不变。日志兼容仅用于API日志写盘；本次无旧响应重放。State模型调用1145次，输入tokens 12,474,820，输出tokens 110,221，11题触发上下文限制，耗时35.2分钟。

未训练模型、生成教师答案、调整超参数或刷新来源60题。所有失败保留逐步交互与官方报告。

## 文件

- EVALUATOR_DETAILS.md：57题任务要求、结果、所有官方条件及原始报告链接。
- evaluator_per_task_comparison.csv / four_model_per_task.csv / model_comparison.csv：逐题及四模型总体对照。
- evaluator_assertions.jsonl / official_candidate_evaluation.json：每个条件、失败trace与官方完整输出。
- summary.json / diagnostic_decision.json / validation.json：指标、诊断判断与核验证据。
- score_change_decomposition.json：按成功/失败变化分组，解释任务成功与条件得分的不同方向。
- CFST-state/：完整轨迹、配置、逐题评分、成功/失败清单。
- gained_task_ids.txt / regressed_task_ids.txt / family_comparison.csv：相对原模型变化。

