# ZeroFail3、Random、Net3同状态机制实验报告

**实验结果报告。** 本文依据保存的同状态动作、真实执行、盲评和固定接手续跑生成；不新增训练。详细逐项数据与案例均可回查。

正式状态129个，全部九模型共同可比较128个；首步生成1161个、有效评分1152行（671种不同证据）。续跑完成540/540分支，严格共同状态20/20，其中核心18/18、发现复查2/2。仅使用物理GPU1。

## 1. 这次具体在做什么

旧实验已经比较了三种评分选步策略训练后的自然整题表现。本次把某一步之前的历史消息、Python会话、数据库、文件、时间/随机状态及反馈固定下来，让九个已有模型分别决定下一步。相同训练seed配对，但三个seed是三个已训练权重，不是给同一个权重随机采样三次。状态来源同时包括三策略各43个；每个状态由全部九模型作答。

例如：历史已经拿到某个分页接口的规格，第一批对象也已读到。我们不再比较各模型自己碰巧走到的不同历史，而是让三组看同一段历史，观察它们重复查规格、继续取数据、合理使用已知对象还是直接提交。随后把这些首步分别交给同样三种固定接手策略，检验差异能否影响后续检查。

比较的是完整首步响应包（文本、代码、反馈及副作用），不是单独替换数据库或一行代码。接手策略固定为三组seed20261015；每种策略接手所有首步，不能让每组仅由自己续跑。

## 2. 状态、评价与校准

57个题目覆盖参照与A/B/C各24个定向状态分开报告，不把129状态混成新的DEV成功率。A检验缺必要规格时的信息获取；B检验资料和实际输入足够时的行动；C检验必要范围覆盖。仅用行动前公开证据冻结适用性卡片；机械候选不一定真的满足语义机会，no/uncertain不换样。

校准完成138状态逐token核验、9状态18次独立重放、只读/写入/写后异常三种隔离快照探针、27个校准动作和9个短续跑分支。写入探针证明快照运输和异常副作用保留，不代表测试通过数必须变化。评分使用用户明确授权的OpenAI GPT-6.1-sol/high，工具关闭，凭证等值脱敏；隐藏测试、未来原动作和模型组/seed不出站。校准语义审阅是研究助手审阅，不是独立人工金标准。

| 面板 | 共同可比较yes | 全部no | 全部uncertain | yes家族 | 来源R/N/Z的yes数 | 覆盖门槛通过 |
| --- | --- | --- | --- | --- | --- | --- |
| focus_A | 24 | 0 | 0 | 19 | 8/8/8 | True |
| focus_B | 16 | 8 | 0 | 13 | 6/4/6 | True |
| focus_C | 17 | 4 | 3 | 11 | 7/5/5 | True |

门槛为yes≥12、每来源≥3、家族≥6；这是预定报告门槛，不是功效保证。覆盖不足时只能作描述，不能把该场景没有测清楚解释成模型没有能力。

## 3. 三个主要行为指标

| 场景 | 组别 | 可确认正例/共同机会行 | unknown | 来源/题目等权正例率 | 含unknown上界 |
| --- | --- | --- | --- | --- | --- |
| focus_A | random | 25/72 | 0 | 34.72% | 34.72% |
| focus_A | net3 | 29/72 | 0 | 40.28% | 40.28% |
| focus_A | zerofail3 | 39/72 | 0 | 54.17% | 54.17% |
| focus_B | random | 10/48 | 0 | 18.52% | 18.52% |
| focus_B | net3 | 6/48 | 0 | 11.11% | 11.11% |
| focus_B | zerofail3 | 10/48 | 0 | 18.52% | 18.52% |
| focus_C | random | 6/51 | 0 | 13.33% | 13.33% |
| focus_C | net3 | 8/51 | 0 | 16.51% | 16.51% |
| focus_C | zerofail3 | 8/51 | 0 | 16.51% | 16.51% |

unknown保留在分母。正例率表示公开证据足以确认的行为事件；不把未知强行判FAIL。来源、题目和三个训练seed等权；相同完整前缀不会重复增加样本量。

| 场景 | 对比 | 均值差 | seed15 / 16 / 17 | 家族bootstrap描述区间 |
| --- | --- | --- | --- | --- |
| focus_A | zerofail3 - random | +19.44 pp | +0.00 pp / +25.00 pp / +33.33 pp | +8.31 pp 至 +31.11 pp |
| focus_A | zerofail3 - net3 | +13.89 pp | +4.17 pp / +8.33 pp / +29.17 pp | +4.94 pp 至 +24.34 pp |
| focus_B | zerofail3 - random | +0.00 pp | -5.56 pp / +5.56 pp / +0.00 pp | -4.76 pp 至 +3.70 pp |
| focus_B | zerofail3 - net3 | +7.41 pp | +5.56 pp / +5.56 pp / +11.11 pp | +0.00 pp 至 +15.61 pp |
| focus_C | zerofail3 - random | +3.17 pp | +4.76 pp / +4.76 pp / +0.00 pp | +0.00 pp 至 +9.88 pp |
| focus_C | zerofail3 - net3 | +0.00 pp | +0.00 pp / +4.76 pp / -4.76 pp | +0.00 pp 至 +0.00 pp |

家族聚类bootstrap固定训练seed；仅保留所有预定来源/场景格非空的重采样，具体尝试/有效次数在CSV。DEV57已多轮分析，区间仅描述不确定性，不作多重比较确认性显著结论。

## 4. 行为收益要与代价一起看

| 57题参照指标 | random | net3 | zerofail3 |
| --- | --- | --- | --- |
| execution_error | 19.64% | 8.33% | 12.50% |
| redundant_known_information | 46.43% | 54.17% | 50.00% |
| unsupported_execution | 39.29% | 25.60% | 26.79% |
| state_contradiction | 8.33% | 7.14% | 5.36% |
| wrong_scope_action | 1.79% | 1.79% | 2.38% |
| premature_termination | 2.38% | 1.79% | 1.19% |
| generated_tokens | 82.80 | 74.56 | 73.67 |

具体状态使用矛盾与仅叙述不实分开记录；R1–R8完整P/F/U/N另表，不合成质量总分。更多文档、更多P、更少异常都不能单独解释性能；需同时看任务相关性、范围约束和后续结果。

## 5. 官方evaluator：即时效果与有限续跑

同一组官方断言在共同before、每组首步后h0、接手第4/12步或更早终态上执行。每题先算检查通过比例再平均；终态成功、完成API调用、逐项新增/丢失分别记录。只读动作即时检查不变不等于无价值。

| 额外接手步预算 | 首步来源组 | 共同状态 | 官方检查Macro | 官方goal-completion |
| --- | --- | --- | --- | --- |
| 4 | random | 18 | 30.91% | 5.56% |
| 4 | net3 | 18 | 30.60% | 5.56% |
| 4 | zerofail3 | 18 | 30.81% | 5.56% |
| 12 | random | 18 | 35.23% | 7.41% |
| 12 | net3 | 18 | 34.23% | 6.79% |
| 12 | zerofail3 | 18 | 39.16% | 10.49% |

以上仅是18个预选机制状态的条件效果，不是从头重跑DEV57的成功率。两例d4e9306发现复查不混入核心总体；12步未达成不等于继续无限步也会失败。正常模型错误、无代码和提前终止保留；基础设施缺失单列，不补零。

| 核心h12首步对比 | 检查Macro差 | 首步seed15 / 16 / 17 | 描述区间 |
| --- | --- | --- | --- |
| zerofail3 - random | +3.94 pp | +2.28 pp / +3.12 pp / +6.40 pp | +0.45 pp 至 +7.39 pp |
| zerofail3 - net3 | +4.93 pp | +4.52 pp / +5.11 pp / +5.17 pp | +0.44 pp 至 +9.46 pp |
| net3 - random | -1.00 pp | -2.24 pp / -1.99 pp / +1.23 pp | NA 至 NA |

三种固定接手策略不是三个独立随机seed。各接手策略、状态来源、A/B/C及排除d4e9306的差值见[分层表](analysis/continuation_receiver_source_stage_slices.csv)，避免只挑某一种接手策略报优势。

| 核心h12对比 | 官方细项类别 | 新增胜出 | 配对失去 | 净差 |
| --- | --- | --- | --- | --- |
| zerofail3 - random | answer_null | 10 | 6 | 4 |
| zerofail3 - random | answer_value | 1 | 0 | 1 |
| zerofail3 - random | local_content_identity | 2 | 1 | 1 |
| zerofail3 - random | model_scope | 10 | 4 | 6 |
| zerofail3 - random | preservation | 4 | 0 | 4 |
| zerofail3 - random | record_counts | 5 | 1 | 4 |
| zerofail3 - random | selection_constraints | 2 | 0 | 2 |
| zerofail3 - random | target_set_mapping | 18 | 1 | 17 |
| zerofail3 - net3 | answer_null | 12 | 2 | 10 |
| zerofail3 - net3 | answer_value | 2 | 1 | 1 |
| zerofail3 - net3 | local_content_identity | 2 | 1 | 1 |
| zerofail3 - net3 | model_scope | 10 | 2 | 8 |
| zerofail3 - net3 | preservation | 4 | 0 | 4 |
| zerofail3 - net3 | record_counts | 5 | 1 | 4 |
| zerofail3 - net3 | selection_constraints | 2 | 0 | 2 |
| zerofail3 - net3 | target_set_mapping | 19 | 0 | 19 |

八类由旧97种家族×requirement固定映射形成，答案区分期望null与实际值。断言相互相关，不能把表中的检查数当独立实验样本。完整逐项得失、h0到h12变化和不该修改的范围都保留在CSV。

## 6. 评分稳定性与真实案例

| 主要字段 | 适用复核数 | 一致率 | 测量门槛 |
| --- | --- | --- | --- |
| coverage_progress | 23 | 100.00% | passed |
| grounded_application | 32 | 100.00% | passed |
| relevant_gap_reduced | 52 | 100.00% | passed |

54条预选复核采用同一评委的新上下文，只能说明重复一致性，不能证明准确率；原判和复核判均保留，没有多数投票改原判。主字段适用复核不足12条或一致率不足80%时，不据此支持强机制结论。

详见[真实动作与后续结果案例](analysis/CASES.md)。案例包含正向、最小/负向和旧发现复查，明确事后选例规则，不用几个好例子代替总体。

## 7. 能回答与不能回答什么

可以检验：在相同历史下，三种已训练模型是否表现出不同的信息获取、已有资料使用、范围覆盖行为；这些首步响应包在固定接手策略、有限步数下是否改善了官方细项，以及收益依赖哪些状态来源、seed、接手策略和任务家族。

只有当相应机会覆盖和测量稳定性足够、行为差异与后续差异方向相容时，才可把结果作为某个行为机制的支持。如果行为评分提高而后续持平/退化，就不能说该行为已解释成功率收益；如果只在一个接手策略或发现家族成立，则结论应限定在那里。

本实验不单独识别某条rubric、R6正例数量或某类文档训练样本的因果贡献，也不估计自然整题收益中有多少比例被该机制中介。旧训练策略同时改变内容、长度和监督token分布；固定历史只消除了本次动作比较中的历史差异。新任务泛化还需要独立任务验证。

集合审计保留真实请求参数、逐次API响应、打印JSON和本地Python变量中的对象ID。正式运行前增加被动响应记录，并用27个已保存校准动作核验观测和状态完全一致。逐次返回与打印内容分开：未打印数据仅用于本地审计，不发送给模型或评委。新ID仅指当前记录分支同查询范围内的新出现，不能解释为历史从未见过或全局完整率；官方范围/对应关系细项是独立后果证据。

## 8. 复查入口

- [全部逐动作行为](analysis/behavior_rows.csv)、[固定分母指标](analysis/behavior_metrics.csv)、[同seed配对](analysis/paired_behavior_contrasts.csv)、[来源/家族/子型](analysis/behavior_source_family_subtype_slices.csv)。
- [即时逐检查](analysis/evaluator_checks.csv)、[即时配对得失](analysis/paired_evaluator_checks.csv)、[八类即时汇总](analysis/evaluator_categories.csv)、[R1–R8分布](analysis/rubric_distributions.csv)。
- [全部可用续跑](analysis/continuation_all_available_rows.csv)、[共同状态续跑](analysis/continuation_common_rows.csv)、[后续逐检查配对](analysis/paired_continuation_evaluator_checks.csv)、[八类后续得失](analysis/continuation_evaluator_categories.csv)。
- [评分一致性](analysis/judge_repeat_summary.json)、[机会与覆盖](analysis/opportunity_and_state_coverage.csv)、[请求审计](analysis/api_request_ledger.csv)、[逐次API返回与对象ID](analysis/api_response_ledger.csv)、[可观察集合审计](analysis/visible_collection_ledger.csv)。
- [运行README](README.md)、[节点日志](EVENTS.jsonl)、[校准审阅记录](calibration/SEMANTIC_REVIEW.md)、[冻结协议接受记录](config/calibration_accepted.json)。
