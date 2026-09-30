# Dynamic CFST 实验

<!-- STATE_DEV57_DIAGNOSTIC_START -->
**2026-09-29四模型Dev57评测已齐：** State-1epoch在Dev57成功25/57（43.9%），evaluator条件通过179/291（61.51%）。相对原epoch5的23/57，新增成功9题、退步7题、净变化+2题；此前Action为31/57、Mixed为21/57。保持既有Action选择及接受记录；本次没有训练、教师答案或来源60题刷新。详见 [第7e步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/README.md) · [State的57题evaluator明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/EVALUATOR_DETAILS.md) · [四模型逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/four_model_per_task.csv)。
<!-- STATE_DEV57_DIAGNOSTIC_END -->

<!-- MIXED_DEV57_DIAGNOSTIC_START -->
**2026-09-29补充诊断已完成：** Mixed-1epoch在Dev57成功21/57（36.8%），evaluator条件通过184/291（63.23%）。相对原epoch5的23/57，本次净变化-2题（新增成功10、退步12）；此前Action为31/57。这次完整Dev57评测用于核查Mixed的表现，保留原第7b步选择和第7c步Action接受记录，不训练、不生成教师答案、不刷新来源60题。详见 [第7d步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/README.md) · [57题evaluator明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/EVALUATOR_DETAILS.md)。
<!-- MIXED_DEV57_DIAGNOSTIC_END -->

本目录统一保存各步骤的执行产物，各步骤使用并列子目录。

**当前：第7c步Dev57评测已完成。Action-1epoch在Dev57上成功31/57（54.4%），测试条件通过215/291（73.88%）。通过既有接受门槛，可在后续第8步使用该候选；本次未启动来源60题刷新。**

**此前进展：** 第6b步各包1epoch训练已完成，三个独立adapter及报告保存在 [第6b步训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md)。State/Action/Mixed分别使用12/8/20条、更新6/4/10次；282项核验通过，每条恰好训练一次。旧第6、7步结果保留；第7b步检查30题也已完成，State 17/30、Action 19/30、Mixed 15/30。按冻结规则选择CFST-Action-1epoch作为Dev57候选，第7b步结束时尚未执行Dev57；后续第7c步现已完成并通过接受门槛。见 [第7b步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07b_check30_one_epoch/README.md)。

| 步骤 | 目录 | 状态 |
| --- | --- | --- |
| 第一步：train90 学生轨迹 | step01_train90_student_rollouts/ | 已完成，90/90，成功46题、失败44题 |
| 第二步：错误审查 | step02_error_analysis/ | 已完成离线分析：冻结60/30，审查10例，首选3例、备选2例 |
| 第三步：实际修复验证 | step03_repair_validation/ | 已完成：3次尝试全部官方成功，门槛通过 |
| 第四A步：扩大成功修复集合 | step04a_expanded_repairs/ | 已完成：20题中13题官方成功；累计状态8、参数7、恢复1 |
| 第四B步：上下文失败前修复 | step04b_context_repairs/ | 已完成：8题中4题官方成功；累计旧标签为状态12、参数7、恢复1 |
| 第五步：三个最小训练包 | step05_training_packages/ | 已完成：State 12、Action 8、Mixed 20；472项核验通过 |
| 第六步：三个独立LoRA分支 | step06_lora_branches/ | 已完成：三支训练成功；73项核验与真实重载通过 |
| 第七步7.1：检查30题 | step07_check30_evaluation/ | 已完成：基线17/30；CFST-state 13/30、CFST-Action 14/30、CFST-Mixed 14/30 |
| 第六b步：各包1epoch重训 | step06b_lora_one_epoch/ | 已完成：6/4/10次更新，282项核验和真实重载通过；评测见第7b步 |

| 第七b步：1epoch检查30题 | step07b_check30_one_epoch/ | 已完成：基线17/30；1epoch为17/19/15题成功，90条新轨迹核验通过 |

| 第七c步：Action-1epoch Dev57 | step07c_dev57_action_one_epoch/ | 已完成：Action 31/57；evaluator 73.88%；基线23/57复用 |

## 第一步结果

使用已有 Qwen3-8B + train90 LoRA epoch5，按原 LoRA 评测协议完成 train90。官方成功率51.1%，完整场景成功9/30；运行耗时43.8分钟。90题轨迹与官方评分核验通过，基础设施和评分器错误为0。失败题中9题出现32000上下文限制，保持原协议，没有扩窗重试。

- [第一步报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/REPORT.md)
- [逐题结果表](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/task_results.csv)
- [成功清单](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/success_task_ids.txt)
- [失败清单](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/failed_task_ids.txt)
- [轨迹索引](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/trajectory_index.jsonl)
- [完整性核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/metrics/final_validation.json)

## 第二步结果

以种子20260928固定来源60题与检查30题，任务族不重叠；来源29成功、31失败，检查17成功、13失败。只从来源侧审查10个未超限失败，得到3个首选、2个备选；它们在第2步交付时均未验证。原始模型交互、执行代码、环境返回、数据库与官方报告保留在第一步目录。

- [第二步结果与文件说明](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/README.md)
- [10例失败审查](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/failure_review.md)
- [候选索引](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step02_error_analysis/repair_candidates.jsonl)

第2步没有重跑Qwen3-8B、调用教师、重放环境或训练模型。

## 第三步结果

5个冻结候选的干净前缀重放全部通过，共对照57个原动作。随后按固定顺序验证前三个候选：教师各提供一个动作，原LoRA学生分别继续4、3、2步，三题官方评分为5/5、8/8、7/7，均成功。达到3条门槛后停止，两个备选未运行；本步没有训练模型。

- [第三步报告与文件说明](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/README.md)
- [三条结果汇总](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/summary.json)
- [证据一致性核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/validation.json)

第3步证明了单步帮助的数据生产流程可行，尚未证明修复训练能迁移。第4A步随后穷尽来源侧未超限失败并扩大成功集合，结果见下节。

## 第四A步结果

来源侧23个未超限失败已全部处理：第3步3题，本步按冻结顺序继续20题。20条前缀共229个动作全部干净重放；本步13题官方成功、7题失败。加上第3步后冻结16条合格修复，按教师实际动作重核为状态8、参数7、恢复1，覆盖7/5/1个任务族。检查30题教师答案为0，训练为0。

状态类达到8条下界；参数差1条，恢复差7条，因此没有进入三组短训。第4B步随后检查来源侧8个上下文失败在首次超限前是否存在可验证修复；检查30题继续只做效果检查。

- [第四A步报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04a_expanded_repairs/README.md)
- [16条冻结合格样本](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04a_expanded_repairs/qualified_samples.jsonl)
- [7条排除记录](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04a_expanded_repairs/excluded_attempts.jsonl)
- [25项证据核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04a_expanded_repairs/validation.json)

## 第四B步结果

来源侧8个上下文失败已按第2步固定顺序全部处理。所有候选点都位于第一次上下文拒绝之前，且原输入连同3,000输出预算不超过32,000；8题共70个前缀动作全部干净重放。正式结果为4题成功、4题失败。成功4条按教师实际动作重核后全部是状态错误，没有新增参数或恢复样本。

累计合格集合为20条：状态12、参数7、恢复1。两个有可信无效恢复证据的候选均未通过官方评分，说明上下文失败不能直接当作恢复错误。来源60题的31个失败已经耗尽。按当时的三分类门槛，参数仍差1条、恢复仍差7条，所以第4B步先停止训练；随后计划把主能力改为“状态构建/动作落地”，现有20条因此满足最小试训规模并进入第5步。检查30题和Dev57仍没有教师答案。

- [第四B步报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04b_context_repairs/README.md)
- [8题逐案审查](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04b_context_repairs/failure_review.md)
- [20条累计合格样本](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04b_context_repairs/qualified_samples.jsonl)
- [39项证据核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step04b_context_repairs/validation.json)

## 第五步结果

最终20条按两个主能力重标并冻结成三个唯一数据包：CFST-state含12条状态构建，CFST-Action含8条动作落地，CFST-Mixed含全部20条。每条输入是修复点之前的脱敏真实历史，训练目标只有经过官方成功验证的一个教师替代动作；检查30题和Dev57答案没有进入数据。

三个包按种子20260928固定顺序。State、Action、Mixed一轮分别含1,826、1,493、3,319个监督tokens；最长样本22,193 tokens，全部低于40,960，没有截断。独立验证对40条序列化记录逐条检查聊天模板、completion-only loss mask、来源边界、集合关系与文件哈希，472项全部通过。本步没有训练模型。

- [第五步报告与文件说明](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step05_training_packages/README.md)
- [State训练包](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step05_training_packages/CFST-state/train.jsonl)
- [Action训练包](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step05_training_packages/CFST-Action/train.jsonl)
- [Mixed训练包](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step05_training_packages/CFST-Mixed/train.jsonl)
- [标签转换表](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step05_training_packages/label_conversion.csv)
- [472项一致性核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step05_training_packages/validation.json)

## 第六步结果

三个分支均从同一个Qwen3-8B + train90 LoRA第5轮adapter独立启动，继承相同模型权重，并分别建立新的相同AdamW优化器。它们只在各自CFST数据上进行一次短训，没有重跑旧train90训练，也没有串行继承其他CFST分支。

| 分支 | 唯一样本 | 监督tokens | 更新步数 | 最终adapter哈希前缀 |
| --- | ---: | ---: | ---: | --- |
| State | 12 | 8,138 | 27 | `846bf990d1c6` |
| Action | 8 | 8,150 | 22 | `16cea6a7e5f2` |
| Mixed | 20 | 8,160 | 25 | `fe5b0676f87b` |

预算最大差22 tokens（0.275%）。三个adapter哈希互不相同，504/504个LoRA tensors均相对源adapter发生变化；三者重新加载到Qwen3-8B后的真实forward全部通过。73项训练、配置、预算、权重和重载检查全部通过。本步没有运行检查30题或Dev57，训练loss不能作为任务性能结论。

- [第六步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/README.md)
- [State adapter与报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-state/REPORT.md)
- [Action adapter与报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Action/REPORT.md)
- [Mixed adapter与报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Mixed/REPORT.md)
- [结构化汇总](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/summary.json)
- [73项核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/validation.json)

[方法总览](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/DYNAMIC_CFST_OVERVIEW.md) · [当前逐步计划](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md)

## 第七步7.1：四模型检查30题

检查30题已完成：原epoch5为17/30（复用），CFST-state 13/30、CFST-Action 14/30、CFST-Mixed 14/30。 三个分支都没有正净改善，按原计划保留原epoch5，本轮不进入Dev57或来源60题刷新。

| 模型 | 官方成功 | 新增成功 | 退步 | 净改善 |
| --- | ---: | ---: | ---: | ---: |
| 原epoch5（复用） | 17/30 | — | — | — |
| CFST-state | 13/30 | 4 | 8 | -4 |
| CFST-Action | 14/30 | 2 | 5 | -3 |
| CFST-Mixed | 14/30 | 4 | 7 | -3 |

三个新分支共90条完整轨迹及官方评分已归档；基线复用经核验的旧结果。未调用教师、未生成训练答案、未训练、未运行Dev57。日志异常的精确重放恢复及全部协议核验见[第7.1步报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07_check30_evaluation/README.md)。

## 第7b步实际结果：1epoch模型在冻结检查30题上评测（已完成）

原epoch5经核验复用，仍为17/30。三支第6b步新adapter各从初始环境完成同一30题，完整保存90条新轨迹与官方评分。没有Codex动作、没有生成训练答案、没有新训练，也没有运行Dev57。

| 1epoch模型 | 官方成功 | 新增成功 | 退步 | 净改善 | 旧版成功数 | 相对旧版变化 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| CFST-state | 17/30 | 5 | 5 | +0 | 13/30 | +4 |
| CFST-Action | 19/30 | 5 | 3 | +2 | 14/30 | +5 |
| CFST-Mixed | 15/30 | 6 | 8 | -2 | 14/30 | +1 |

新增成功、退步和净改善均相对原epoch5；最后两列与旧8,000监督tokens版本比较。**第7b步当时决定：按冻结规则选择CFST-Action-1epoch作为Dev57候选，第7b步结束时尚未执行Dev57；后续第7c步现已完成并通过接受门槛。**

评测协议与第1步、旧第7步相同：temperature=0、seed=100、32,000窗口、每次3,000输出tokens、每题50步、无reasoning parser。首条模型输入、冻结题目清单、运行器、配置、adapter哈希与官方评分一致性已核验，3496项检查通过。沿用旧版已验证的日志序列化修复，只影响日志落盘，本次没有前缀重放。完整证据见 [第7b步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07b_check30_one_epoch/README.md)。

**能说明什么：** 这次直接检验了“每条修复只学一次”的训练尝试。先看相对旧版是否改善，再看是否超过原epoch5；不能把超过旧版自动视为模型更新成功。单次结果仍不能单独证明能力分类合理或锁定退步原因。三支训练量自然不同，同一检查30题已参与这次方案修订，属于开发实验。

**第7b步的执行边界：** 按冻结规则选择CFST-Action-1epoch作为Dev57候选，第7b步结束时尚未执行Dev57；后续第7c步现已完成并通过接受门槛。 本次到检查30题结果与候选判断结束，不自动加训、更改超参数、补教师答案或启动其他任务集。


### 第7c步实际结果：Action-1epoch的Dev57接受检查（已完成）

**Action-1epoch在Dev57上成功31/57（54.4%），测试条件通过215/291（73.88%）。** 原epoch5基线成功23/57（40.4%），测试条件通过206/291（70.79%）；两者使用相同清单与评测协议。新增成功14题、退步6题，净变化+8题。

| 指标 | 原epoch5 | Action-1epoch |
| --- | ---: | ---: |
| 官方任务成功率TGC | 23/57；40.4% | 31/57；54.4% |
| 官方完整任务族成功率SGC | 4/19；21.1% | 6/19；31.6% |
| 全部测试条件通过率 | 206/291；70.79% | 215/291；73.88% |
| 57题各自测试通过率平均值 | 71.79% | 76.08% |

总体测试条件通过率按“总通过条件÷总条件”计算；逐题平均值先算每题比例再平均。它们用于详细解释结果，不替代官方整题成功率。

**接受判断：通过既有接受门槛，可在后续第8步使用该候选；本次未启动来源60题刷新。** 本轮始终只评估检查30题选出的Action，没有用Dev57重新选择State/Mixed、加训、调参或生成教师答案。已完成57条新轨迹和逐题官方评分；4991项核验通过。旧模型和旧实验结果保留。

产物：[第7c步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md) · [57题evaluator明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/EVALUATOR_DETAILS.md) · [逐题百分比对照CSV](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/evaluator_per_task_comparison.csv) · [冻结规则接受判断](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/acceptance.json)。


## 第7d步补充诊断：Mixed-1epoch在Dev57是否下降

Mixed-1epoch在Dev57成功21/57（36.8%），evaluator条件通过184/291（63.23%）。这里的Mixup指第6b步已有的CFST-Mixed-1epoch；对照“不训”指Qwen3-8B + train90 LoRA第5轮adapter，即尚未追加CFST修复训练的模型。

| 模型 | 官方整题成功 | 总体evaluator条件通过 |
| --- | ---: | ---: |
| 原epoch5 | 23/57；40.4% | 206/291；70.79% |
| Action-1epoch（第7c步） | 31/57；54.4% | 215/291；73.88% |
| Mixed-1epoch（本次） | 21/57；36.8% | 184/291；63.23% |

**实际变化：** 相对原epoch5，新增成功10题、退步12题，净变化-2题；官方成功率变化-3.51个百分点，全部条件通过率变化-7.56个百分点。逐题条件通过率的平均值为67.22%，与全部条件等权汇总的比例分别报告。

**怎样理解：** 检查30题中Mixed是15/30，原epoch5是17/30；Dev57现在有了独立的实际运行结果，应按上表描述，不能把检查30题的下降预先推广。本次是查看Action的Dev结果后追加的固定种子诊断，不能单独证明分类有效，或把差异完全归于混合训练；两分支的数据内容、条数和更新次数也不同。

**当前决定：** 既有Action候选选择和接受记录不变。本次57题从初始环境独立运行、使用原协议并接受官方评分；5631项核验通过，旧结果原哈希不变。未训练模型、生成教师答案或启动第8步。

产物：[第7d步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/README.md) · [57题evaluator明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/EVALUATOR_DETAILS.md) · [三模型逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/three_model_per_task.csv) · [诊断判断](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/diagnostic_decision.json)。


## 第7e步补充诊断：State-1epoch与原模型是否接近

State-1epoch在Dev57成功25/57（43.9%），evaluator条件通过179/291（61.51%）。本次使用第6b步CFST-state adapter：12条状态构建修复动作各学一遍，共6次参数更新。原模型仍指Qwen3-8B + train90 LoRA第5轮adapter。

| 模型 | 检查30题成功 | Dev57官方成功 | Dev57总体evaluator条件通过 |
| --- | ---: | ---: | ---: |
| 原epoch5 | 17/30 | 23/57；40.4% | 206/291；70.79% |
| State-1epoch | 17/30 | 25/57；43.9% | 179/291；61.51% |
| Action-1epoch | 19/30 | 31/57；54.4% | 215/291；73.88% |
| Mixed-1epoch | 15/30 | 21/57；36.8% | 184/291；63.23% |

**State实际变化：** 相对原epoch5新增成功9题、退步7题，净变化+2题。官方成功率变化+3.51个百分点，全部条件通过率变化-9.28个百分点；逐题条件通过率平均值为66.03%。总体条件通过率与逐题平均值分别计算，均包含失败任务。

**怎样理解：** 本次整题成功小幅增加，但条件通过率下降，不能笼统说与原模型表现相同。两者都失败的25题中，通过条件由78降至47；这部分退步不会体现在整题成功数中。检查30题中State与原模型总分相同，只是已有观察；Dev57应按本次实际差值与逐题变化解释。本轮没有预先规定“差不多”的容许范围，不能把接近的单次得分直接称为统计等效。四个模型的数据内容、条数和更新次数不同，结果不能单独证明能力分类的因果作用。

**当前决定：** 本次补齐四模型描述性比较；原第7b步Action选择和第7c步接受记录保持不变。57条新轨迹与官方评分完整，5967项核验通过，历史结果原哈希不变。没有训练、教师修复、调参或第8步刷新。

产物：[第7e步总报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/README.md) · [State的57题evaluator明细](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/EVALUATOR_DETAILS.md) · [四模型逐题对照](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/four_model_per_task.csv) · [总体对照CSV](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/model_comparison.csv)。

