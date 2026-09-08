# EI 校验规则与五项聚合指标

> 实现范围：EI 排程与物料推演
> 评分合同：`simulation.ei`，schema revision `2`
> 原子规则包：ruleset release `4.13.0`，18 项当前生效规则和 5 项聚合指标
> 公开结果类型：`run-score`

## 1. 文档定位与当前版本

### 1.1 文档目的与事实来源

本文件是 `evaluation/src/simulation/ei/` 的统一规则说明，定义当前 18 项校验规则、5 项聚合指标、结果格式和报告口径。本文只描述当前生效实现，不记录历史规则演进。

需求与实现的追溯顺序为：

```text
题目规范 Prompt
  -> 题目可执行合同（正式题 evalsets/simulation/<question>/validator.yaml；
                    变种题 datasets/<question>/validator.yaml）
  -> ruleset.yaml（规则 ID 与聚合策略）
  -> adapter / rule / aggregation / report / tests
```

题目 Prompt 是业务需求第一事实源；题目可执行合同负责选择适用规则、指定输入归属、字段映射和参数。规则说明与实现不一致时，应以 Prompt、当前机器配置和当前代码共同核定，并在同一变更中修正文档、实现和测试。

### 1.2 范围与边界

- 本文件覆盖排程、有效交付、物料推演和利旧核算规则，以及由规则结果产生的五项聚合指标；
- 规则只消费 adapter 已发现并标准化的输入，不扫描运行目录，不读取 GroundTruth，不根据历史得分反推目标；
- 聚合模块只消费同次评分生成的规则结果，不重新读取候选业务文件；
- 报告模块只消费规范 `score.json`，不重新执行规则或聚合公式；
- 五项聚合指标分别表达不同业务视角，彼此之间不再计算二次总分。

### 1.3 当前版本

| 对象 | 当前版本 | 说明 |
|---|---|---|
| EI 文档结构 | contract `simulation.ei`、schema revision `2` | 由唯一的 `contracts/ei-contract.schema.json` 定义 |
| 原子规则包 | ruleset release `4.13.0` | 同时冻结 adapter、resolver、18 项规则和聚合策略 |
| 题目 profile | 依赖 ruleset release `4.13.0` | 不单独编号；评分结果记录题目根目录与实际使用的来源路径 |
| 内部组件结果 | document type `component-result` | 兼容与测试使用，不是公开落盘文件 |
| 单运行公开结果 | document type `run-score` | 写入 `scores/<score_id>/score.json`，记录 release、题目来源路径和评分证据 |

## 2. 评价对象与标准化证据

### 2.1 评价对象

EI 评分依次处理四层对象：

1. **题目权威输入**：规定应处理的站点、动作、批次、主计划、物料需求、替代关系和业务参数；
2. **被评分交付物**：站点计划、最终物料、推演明细、仓库流水和利旧汇总；
3. **标准化证据**：adapter 将不同文件和字段映射为稳定角色、标识、数量和时间坐标；
4. **规则与聚合结果**：每项规则独立生成 `CheckResult`，聚合模块再生成五项指标。

题目可执行合同决定每个角色来自题目权威输入还是被评分交付物，以及该角色是否必需。本文件不维护逐题启用关系。

### 2.2 标准化数据角色

| 角色 | 业务用途 |
|---|---|
| `scope_input` | 权威站点、动作和原始 BOM 范围 |
| `batch_input` | 权威 Region—站点到 Cluster/MOCN 批次的映射与顺序 |
| `master_plan` | 权威月度交付容量或曲线 |
| `prepared_master_plan` | 被评分方按 Region、动作、自然月汇总的候选主计划；仅在题面要求编制主计划时启用 |
| `substitution_source` | 权威替代关系和合法物料组合 |
| `initial_inventory_source` | 初始库存或允许入仓料号来源 |
| `site_plan` | 站点、Region、动作、业务周、绝对周、交付年月和批次信息 |
| `final_material` | 最终 BOM、原始 BOM、实际料号、数量和动作时间 |
| `material_substitution` | 被评分结果提交的替代关系 |
| `recovered_supply` | 已恢复物料、数量和成熟周 |
| `site_material_timeline`、`gap` | 物料需求、供给、缺口和时序推演 |
| `site_rollout` | 由正式 SitePlan 派生的逐周站点流转宽表 |
| `reuse_warehouse`、`new_warehouse`、`initial_warehouse` | 利旧、新料和初始库存流水 |
| `reuse_by_region` | Region/物料级数量汇总与利用率 |

### 2.3 当前规则清单

`ruleset.yaml` 冻结以下稳定规则 ID。规则增删、评分语义、adapter/resolver 行为或聚合策略发生变化时，必须整体发布新的 ruleset release；规则和聚合不再维护独立 revision。

| 规则组 | 完整规则 ID | 规范名称 |
|---|---|---|
| 排程 | `scheduling.C1` | 站点覆盖 |
| 排程 | `scheduling.C2` | 站点—动作集合一致性 |
| 排程 | `scheduling.C3` | 月度安装容量 |
| 排程 | `scheduling.C4` | 主计划有效月份覆盖 |
| 排程 | `scheduling.C5` | Drop 分池安装数量一致性 |
| 排程 | `scheduling.C6a` | 安装—拆除批次/站点间隔 |
| 排程 | `scheduling.C6b` | 批次交付顺序 |
| 排程节奏 | `scheduling-pacing.O1` | 月度排程曲线一致性 |
| 有效交付 | `effective-delivery.O2` | 有效站点交付曲线一致性 |
| 物料推演 | `simulation.S1` | 替代关系建模与应用 |
| 物料推演 | `simulation.S2` | 可复用物料成熟供给 |
| 物料推演 | `simulation.S3` | 利旧仓守恒 |
| 物料推演 | `simulation.S4` | 新料仓守恒 |
| 物料推演 | `simulation.S5` | 原始 BOM 需求覆盖 |
| 物料推演 | `simulation.S6` | 最终 BOM 与排程时间一致性 |
| 利旧核算 | `reuse-accounting.R3` | 虚拟目标料交付合规 |
| 利旧核算 | `reuse-accounting.R5` | 区域汇总与仓库出库对账 |
| 利旧核算 | `reuse-accounting.R6` | 物料级利用率坐标准确性 |

### 2.4 证据与执行边界

- Region、站点、动作、物料和集合键由 adapter 与规则公共函数标准化；各规则章节明确其实际身份粒度；
- 题目同时提供 `scope_input` 与 `batch_input` 时，O2 及依赖两者的排程规则在读取候选产物前按站点身份校验 Region 一致性；重叠站点 Region 不一致返回 `UNSCORABLE / EVALUATOR_ERROR`，证据前缀为 `QUESTION_DATA_CONFLICT`，不得通过跨区 fallback 转成候选扣分。题目 profile 可用 `scope_input.schema_options.included_years` 冻结 Year 白名单；空字符串是合法白名单值，表示未分年度的配套物料。
- 题目可在 artifact `schema_options.region_aliases` 中声明区域展示别名；adapter 在 schema 与业务标准化前同时改写 Region 字段值及区域动态列名，并在非计分 `resolution_diagnostics` 中保留原值、规范值与命中位置。具体区域名称不得进入共享 rule；
- candidate artifact 优先选择完整可读的题面 canonical 路径；canonical 缺失或结构不完整时允许在受限 artifact roots 内降级搜索。fallback 只允许使用可读性、角色最小识别字段覆盖、规范文件名、目录接近度和稳定路径顺序选择，并记录非计分 `ARTIFACT_PATH_MISMATCH`；
- 数量必须有限，并满足相应规则的整数、符号和精度要求；
- `schedule_week`、ISO `calendar_week` 和 `delivery_period` 是不同时间身份，只有明确规定的规则可以转换；
- `site_plan.status=unscheduled` 且所有时间字段为空时，是题面允许的未排入诊断动作：C1/C2 仍把该动作视为已提交，时间、容量、批次顺序和装拆间隔规则不把它当作已排动作；`unscheduled` 携带任一时间值记录 `UNSCHEDULED_TIME_NOT_BLANK`，其他 status 记录 `INVALID_STATUS`；
- 每项规则独立执行并生成 `id`、`name`、`score`、`status`、`reason_code`、`explanation`、`evidence` 和 `prompt_refs`；
- `evidence` 的子字段由各规则定义，不承诺实现未输出的逐行或逐单元明细；
- 一项规则失败或不可评分不得改变其他规则的输入、执行顺序或结果。

## 3. 排程与节奏校验规则

### 3.1 C1 站点覆盖

- **规则 ID**：`scheduling.C1`。
- **业务含义**：评价应排 Region—站点身份是否出现在被评分站点计划中。
- **输入**：权威 `scope_input`、被评分 `site_plan`，以及题目合同规定的 `site_scope`；使用 batch intersection 范围或声明固定种子 `drop_selection_contract` 时还需要 `batch_input`。固定种子合同与 C5/O2 使用同一受信任 Drop 编译器。
- **最小计分单元**：规范化 `site_key=(region, site)`；同一站点编码位于错误 Region 时不算覆盖。
- **计算公式**：设 Drop 前权威身份集合为 `E0`，计划所有行出现的身份集合为 `A`；未声明固定种子时 `E=E0`，声明时先从 `E0` 移除编译器选中的全部 Drop 站点身份得到 `E`：

```text
rate_C1 = |E ∩ A| / |E|
score_C1 = round(100 * clamp(rate_C1, 0, 1), 6)
```

- **得分与状态**：`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。`E` 为空时得 0；计划缺失或不可解析为候选侧 0 分，权威范围无法编译为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：同一安装站被 Drop 后，该 Region—站点的全部权威动作都不再构成 C1 应排身份；纯拆除站不参加 Drop。`A` 包含计划所有行，不要求 action 或 week 合法；额外身份不增加得分，也不在 C1 中扣分，其动作差异由 C2/C5/O2 评价。
- **核心证据**：`expected`、`matched`、`site_scope`、`source_actions`、`excluded_outside_batch_scope`、`pre_drop_expected`、`dropped_expected_sites`、`drop_selection`。

### 3.2 C2 站点—动作集合一致性

- **规则 ID**：`scheduling.C2`。
- **业务含义**：评价权威要求与被评分计划中的站点动作是否完整一致。
- **输入**：权威 `scope_input` 与被评分 `site_plan`；使用 batch intersection 范围或声明固定种子 `drop_selection_contract` 时还需要 `batch_input`。固定种子合同复用与 C1/C5/O2 相同的已编译 Drop 结果。
- **最小计分单元**：规范化 `action_key=(region, site, action)`。
- **计算公式**：设 Drop 前权威动作集合为 `E0`、计划动作集合为 `A`；未声明固定种子时 `E=E0`，声明时从 `E0` 移除每个被选中 Drop 站点的全部动作得到 `E`：

```text
rate_C2 = |E ∩ A| / |E ∪ A|
score_C2 = round(100 * clamp(rate_C2, 0, 1), 6)
```

- **得分与状态**：并集为空时得 0；`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。计划缺失或不可解析为候选侧 0 分，权威范围无法编译为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：被 Drop 的安装站即使还有拆除权威行，也必须从正式动作全集整体移除；纯拆除站保留。缺失、额外和未知动作均形成集合差异；重复行经集合化后折叠，因此 C2 不检查行唯一性。
- **核心证据**：`expected`、`actual`、`pre_drop_expected`、`dropped_expected_actions`、`drop_selection`。

### 3.3 C3 月度安装容量

- **规则 ID**：`scheduling.C3`。
- **业务含义**：评价被评分安装计划是否超过权威月度容量。
- **输入**：被评分 `site_plan`、权威 `master_plan`，以及 `capacity_factor`、周到月映射参数。`master_format=site-action-weekly-install` 时消费 adapter 从题目侧站点动作表 install 行派生的 Region—自然月曲线，不读取候选 `prepared_master_plan`。
- **最小计分单元**：候选 install 行；超量在 `(region, integer_month)` 容量单元内计算。
- **计算公式**：容量优先使用相同 Region，缺少时回退 `ALL`：

```text
cap_g,m = floor(master_cap_g,m * capacity_factor)
excess  = Σ_g,m max(candidate_install_g,m - cap_g,m, 0)
rate_C3 = 1 - excess / candidate_install_row_count
score_C3 = round(100 * clamp(rate_C3, 0, 1), 6)
```

- **得分与状态**：没有 install 行时得 0；`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。计划缺失/非法为候选侧 0 分，主计划或时间映射无法编译为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：月份键不保留自然年；月份不可解析的 install 行进入总分母但不进入 `excess`；重复行逐行计数，少排不罚。
- **核心证据**：`install_sites`、`excess_sites`、`capacity_factor`。

### 3.4 C4 主计划有效月份覆盖

- **规则 ID**：`scheduling.C4`。
- **业务含义**：评价每条候选安装是否位于权威主计划允许交付的月份。
- **输入**：被评分 `site_plan`、权威 `master_plan` 和周到月映射参数；站点动作格式与 C3 共用同一题目侧 adapter 派生 install 曲线。
- **最小计分单元**：一条候选 install 行。
- **计算公式**：对应 `(region,month)` 键不存在时才回退 `ALL`；Region 键存在但容量为 0 时不回退。只有最终取得的整数月份容量大于 0 才有效：

```text
rate_C4 = valid_install_rows / candidate_install_rows
score_C4 = round(100 * clamp(rate_C4, 0, 1), 6)
```

- **得分与状态**：没有 install 行时得 0；月份为空或不可解析的行失败。`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`；候选计划错误与权威输入错误分别归为候选侧 0 分和 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：月份键不保留自然年；重复行逐行进入分母；dismantle 与 `capacity_factor` 不参与 C4。
- **核心证据**：`install_sites`、`valid`。

### 3.5 C5 Drop 分池安装数量一致性

- **规则 ID**：`scheduling.C5`。
- **业务含义**：评价题目指定 Drop 分池在应用 skip 比例后的已排安装站点是否正确；纯拆除站不进入 Drop 分母。题面只冻结比例时比较分池数量；题面同时冻结随机种子时复现并比较具体保留/删除身份。
- **输入**：权威 `scope_input`、`batch_input`，被评分 `site_plan`，以及 `batch_kind`、`skip_rate`、`skip_pool_scope`；固定种子题还必须声明 `drop_selection_contract={mode: seeded-random, seed: integer}`。
- **最小计分单元**：`skip_pool_scope=batch` 时为跨 Region 的一个规范批次，`region-batch` 时为一个 Region—规范批次，`region` 时为一个 Region；分池内按唯一 Region—站点安装身份计数。
- **计算公式**：

```text
target_p = round_half_up(authoritative_install_site_count_p * (1 - skip_rate))
error    = Σ_p |actual_scheduled_install_site_count_p - target_p|
rate_C5  = 1 - error / Σ_p target_p
score_C5 = round(100 * clamp(rate_C5, 0, 1), 6)
```

固定种子合同下，先按 `batch_input` 源行序构造每个分池的安装候选列表，按冻结的分池顺序遍历，并在所有分池间复用同一个 `random.Random(seed)`；每池删除数固定为向下取整：

```text
drop_count_p = floor(authoritative_install_site_count_p * skip_rate)
dropped_p    = rng.sample(source_ordered_install_sites_p, drop_count_p)
retained     = authoritative_install_sites - union_p dropped_p
error        = |retained - actual_authority_installs|
             + |actual_authority_installs ∩ dropped|
rate_C5      = 1 - error / |retained|
```

`batch` 分池按规范批次排序后调用 RNG，池内不按站点名重排；同一安装站被选中后，其同站拆除动作也不属于正式排程，但 C5 的身份比较只消费候选 install，完整动作影响由 O2/C2 负责。

- **得分与状态**：目标总数为 0 时得 0；`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。候选计划错误为候选侧 0 分，权威范围或批次映射错误为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：只有时间可解析且无周问题的候选 install 计入 actual；Drop 行、纯拆除站和无效周不计入实际交付。无固定种子合同时沿用 half-up 数量口径；固定种子合同时使用 floor 删除数且必须匹配具体身份。数量模式下偏差只遍历权威分池；身份模式下候选计划外站点仍不进入本规则的身份差，由 C1/C2 负责。
- **核心证据**：`batch_kind`、`skip_pool_scope`、`skip_rate`、安装池总数、目标总数 `expected`、实际数、`absolute_deviation` 和逐池 `pool_targets`；固定种子模式还冻结算法、seed、权威顺序、单 RNG 作用域、保留/删除集合摘要、逐池删除身份、缺失保留身份和违规删除身份。

### 3.6 C6a 安装—拆除批次/站点间隔

- **规则 ID**：`scheduling.C6a`。
- **业务含义**：评价题目指定批次或同站安装完成周与拆除开始周是否满足最小或精确间隔。
- **输入**：权威 `batch_input`，被评分 `site_plan`，以及 `batch_kind` 和 `c6a_contract={scope,direction,relation,lag_weeks}`；`scope` 为 `batch|site`，`direction` 当前固定为 `install_then_dismantle`。该规则不消费 `scope_input`。
- **最小计分单元**：候选中同时存在已映射 install 与 dismantle 行的规范批次或 Region—站点；两种 scope 都先使用 `batch_input` 排除未映射动作。
- **计算公式**：

```text
install_finish_u  = max(project_week of install rows in unit u)
dismantle_start_u = min(project_week of dismantle rows in unit u)
lag_u             = dismantle_start_u - install_finish_u

valid_u = (lag_u >= lag_weeks)      when relation = minimum
valid_u = (lag_u == lag_weeks)      when relation = exact
rate_C6a = valid_unit_count / comparable_unit_count
score_C6a = round(100 * clamp(rate_C6a, 0, 1), 6)
```

- **得分与状态**：无可比较单元时返回 `NOT_APPLICABLE`、score 0；周冲突或不可解析的行仍使所在单元进入分母并失败。其他结果中，`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。`site_plan` 缺失或不可解析为候选侧 0 分；权威批次错误为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：batch scope 的批次不按 Region 拆分；site scope 只比较同一 Region—站点的两阶段。规则不验证权威完整性；同一单元的重复动作由 C2 评价，C6a 仍按最晚安装与最早拆除计算。`failures` 保留全部失败单元，单个 `INVALID_WEEK` 单元的 `invalid_time_rows` 最多保留 20 行。
- **核心证据**：`scope`、`direction`、候选/可比较/不可比较单元数、未映射动作、周问题和失败单元；实际与期望间隔只在 `INTERVAL_VIOLATION` 中输出，并为 batch scope 保留历史批次字段别名。

### 3.7 C6b 批次交付顺序

- **规则 ID**：`scheduling.C6b`。
- **业务含义**：评价候选批次首次安装周是否遵循权威批次顺序。
- **输入**：权威 `batch_input`、被评分 `site_plan`，以及 `order_mode`、`scope`、固定事件 `first_install_week`。
- **最小计分单元**：权威序列中的相邻批次对；候选事件是每个 scope/batch 的最早合法 install 周。
- **计算公式**：权威序列按数值升序或来源顺序构造，scope 为 Region 或全局。先过滤出候选有事件周的批次，再比较过滤后子序列的相邻对：

```text
authoritative_pairs = Σ_scope max(authoritative_batch_count_scope - 1, 0)
passed_pairs        = count(left_first_install_week <= right_first_install_week)
rate_C6b            = passed_pairs / authoritative_pairs
score_C6b           = round(100 * clamp(rate_C6b, 0, 1), 6)
```

- **得分与状态**：无权威相邻对时得 0；`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。`site_plan` 缺失或不可解析为候选侧 0 分；没有候选相邻对时以 `WEEK_CONFLICT`、`UNPARSEABLE_WEEK`、`UNMAPPED_BATCH` 或 `INSUFFICIENT_ORDER_EVIDENCE` 说明原因；权威序列错误为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：分母始终是完整权威相邻对数；候选缺批次降低覆盖率，但过滤后跨过缺失批次形成的新相邻对仍参与分子判断。数值模式只决定排序，不合并文本批次 `1` 与 `1.0`。
- **核心证据**：权威/候选 batch 与 pair 数、`order_accuracy`、`pair_coverage`、周问题、未映射行和候选 pair 明细。

### 3.8 O1 月度排程曲线一致性

- **规则 ID**：`scheduling-pacing.O1`。
- **业务含义**：评价候选安装节奏与权威主计划月度曲线的形状一致性，不评价总规模。
- **输入**：被评分 `site_plan`、权威 `master_plan` 和时间映射参数；站点动作格式与 C3/C4 共用同一题目侧 adapter 派生 install 曲线，候选 `prepared_master_plan` 不得成为节奏权威。
- **最小计分单元**：两条归一化曲线共同时间轴上的自然年月坐标 `delivery_period=YYYYMM`。
- **计算公式**：候选 install 先按 `site_key` 去重，权威主计划和候选计划均跨 Region 汇总：

```text
candidate_share_p = candidate_p / Σ_p candidate_p
master_share_p    = master_p / Σ_p master_p
rate_O1           = 1 - 0.5 * Σ_p |candidate_share_p - master_share_p|
score_O1          = round(100 * clamp(rate_O1, 0, 1), 6)
```

- **得分与状态**：任一侧总量不为正时得 0；`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。候选计划缺失/非法为候选侧 0 分，主计划错误为 `UNSCORABLE / EVALUATOR_ERROR`。
- **确定边界**：跨年时保留自然年，不把不同年份的同月合并；只比较全局 `YYYYMM` 曲线，不保留 Region，也不重复评价站点覆盖、skip 或容量。
- **核心证据**：`master_total`、`actual_total`、`periods`、`master_curve`、`actual_curve`。

## 4. 有效交付成效规则

### 4.1 O2 基本定义

- **规则 ID**：`effective-delivery.O2`。
- **规范名称**：有效站点交付曲线一致性。
- **业务含义**：评价满足题目所选动作、时间、物料来源和严格物料合同的有效目标安装站点，是否按权威 Region—交付目标落地。候选计划题可选择逐月分布或截止期完成口径；需要拆除时还要求题目指定的 batch-finish 或同站 install→dismantle 间隔合规。
- **输入**：两种计划模式都使用权威 `scope_input`、相应来源的 `site_plan` 和被评分 `final_material`。`candidate-scheduled` 模式还使用权威 `batch_input`、`master_plan`、`o2_skip_pool_scope`、显式 `o2_monthly_capacity_mode` 和间隔合同；月度容量是题面硬上限时声明 `hard-limit`，并用 `o2_capacity_factor` 冻结与 C3 相同的倍率。候选批次字段未列入 `o2_site_plan_required_fields` 时，O2 不读取候选 `site_plan` 的 Cluster/MOCN 值，而是在解析 Region—站点身份后从权威 `batch_input` 补齐批次；列入时仍按候选必填字段校验。固定种子 Drop 题增加 `o2_drop_selection_contract={mode: seeded-random, seed: integer}`。仅安装题可增加 `o2_install_only_contract={forbidden_actions: [dismantle]}`。题面同时要求从站点动作计划编制月度主计划时，权威 `master_plan` 保持为题目侧站点动作事实源，候选月度汇总使用独立的 `prepared_master_plan` 角色并由 `o2_prepared_master_plan_role` 引用；候选文件不得反向充当 O2/C3/C4/O1 的权威曲线。`fixed-authority` 模式不读取 Drop 项或月度容量参数。物料模式不是 `identity-only` 时才使用权威 `substitution_source`。
- **最小计分对象**：先以目标站点为有效性判定对象，再以 `(region, delivery_period)` 网格单元比较有效站点数与目标站点数；截止期模式把 Region 内全部覆盖月份折叠为一个 completion bucket。

### 4.2 时间身份

| 时间身份 | 格式 | 用途 |
|---|---|---|
| `schedule_week` | 正整数业务周 | 动作顺序、批次完成/同站安装锚点和拆装间隔 |
| `calendar_week` | `YYYYWW` | 唯一 ISO 周身份、跨年排序、计划与最终 BOM 对齐 |
| `delivery_period` | `YYYYMM` | Region—月份目标网格和有效交付网格 |

ISO 周必须通过等价于 `date.fromisocalendar(year, week, 1)` 的校验，不存在的 WK53 无效。

#### 4.2.1 单年度短周补年

只有题目合同明确绝对周轴完全位于同一 ISO 年、`planning_year` 唯一、`week_num` 与 `WK<n>` 一致且无其他权威字段冲突时，才允许：

```text
calendar_week = planning_year * 100 + week_num
```

显式 `YYYYWK<n>` 仍必须与该单年度合同一致；冲突行无效。

#### 4.2.2 跨年题不得推断

跨年度场景必须由显式 `YYYYWK<n>` 或题目授权的绝对日期确定年份。不得从相邻行、文件顺序、周号回绕、主计划月份、候选多数年份或最高可能得分推断年份。候选时间歧义使相关站点无效；权威计划时间歧义属于 `UNSCORABLE / EVALUATOR_ERROR`。

最终 BOM 的 `WK<n>` 只能继承同一 Region、站点、动作下唯一且已解析的计划绝对周，并校验周号一致。`delivery_period` 必须保留年份；连续项目周映射月份时允许跨自然年。

当题目使用 `delivery_month_source=schedule-week` 且冻结单一 `planning_year` 时，候选 `site_plan` 与 `final_material` 当前 action 周允许两种等价表示：短标签 `WK<n>` 继承 `planning_year`，显式标签 `YYYYWK<n>` 保留其提交年份。两种表示都必须与数值周字段一致并构成该规划年的合法 ISO 周；显式年份不等于 `planning_year`、周号冲突或非法 ISO 周都会使对应计划行或最终 BOM 行无效。最终 BOM 的月份展示字段只用于追溯和格式诊断，不参与 O2；O2 的 `delivery_period` 由已校验的 `site_plan` 周身份派生。非当前 action 的冗余时间字段同样不参与该动作的 O2 时间身份，其跨产物一致性由 S6 独立评价。

### 4.3 动作范围、目标网格 B 与分母 N

题目可用 `o2_authority_actions` 显式冻结 O2 动作范围，只允许 `[install]` 或 `[install, dismantle]`，且必须包含 install。未声明该参数的存量 profile 沿用安装与拆除的历史范围。权威 material facts 在构造站点/动作期望宇宙前按该范围过滤；候选中被明确排除的另一种合法动作行默认只形成 out-of-scope 证据，不作为额外动作或畸形行扣分，未知动作仍为候选错误。只有题面明确“仅安装且不得拆除”时，才能在 `[install]` 权威范围上声明 `o2_install_only_contract`；此时 `site_plan` 或 `final_material` 出现任一 dismantle 行都触发 O2 硬门槛并得 0，缺失或非法产物仍沿用 O2 的候选侧失败语义。

在候选计划模式下，令 `U_g,b` 为 Region `g`、规范批次 `b` 中同时属于权威范围和批次、且权威动作包含 install 的站点集合，skip 比例为 `r`。题目合同通过 `o2_skip_pool_scope` 冻结取整分池：

```text
when o2_skip_pool_scope = region-batch:
    T_g,b = round_half_up(|U_g,b| * (1 - r))
    N_g   = Σ_b T_g,b

when o2_skip_pool_scope = region:
    U_g   = union_b U_g,b
    N_g   = round_half_up(|U_g| * (1 - r))

N     = Σ_g N_g
```

题面冻结 seed 时，O2 与 C5 调用同一受信任 Drop 编译器：从 Drop 前权威安装交集出发，按 `batch_input` 源行序构造池内列表，按规范分池顺序遍历，并跨池复用一个 Python seeded RNG；每池删除 `floor(|U_p|*r)` 个安装身份。`batch` scope 把同一规范批次跨 Region 合池。被选中的安装站及其同站全部权威动作先从 B、N 和严格物料权威范围移除；候选仍提交这些站点的任一动作时保留为违规 Drop 身份证据。

候选计划题通过 `o2_target_curve_mode` 冻结 B 的含义。`master-distribution` 下，主计划提供 Region 内交付曲线形状；对非负主计划数量 `M_g,p`：

```text
quota_g,p = Decimal(N_g) * M_g,p / Σ_p M_g,p
```

`B_g,p` 使用 Hamilton 最大余数法转为整数：先向下取整，再按余数降序补位；余数相同时按完整 `delivery_period` 升序。结果必须满足 `Σ_p B_g,p=N_g` 和 `Σ_g,p B_g,p=N`。原始主计划总量、候选排程数和候选有效数均不得替代 `N`。

`o2_master_format=site-action-weekly-install` 时，题目侧 `master_plan` 必须是严格的 `site_name,site_action,mos_weekly_plan,week_num,region,site_count` 站点动作表。adapter 校验站点/动作唯一、动作值、合法 ISO 周和非空 Region，只把 install 行派生为 `(region,YYYYMM,planned_count)` 权威曲线，供 C3、C4、O1 和 O2 共用；prepared-master 比对再对原表执行严格列顺序与 `site_count=1` 校验。dismantle 行不进入交付曲线，但仍保留在候选主计划完整性比对的权威动作全集中。

启用 `o2_prepared_master_plan_role` 时，候选 `prepared_master_plan` 必须严格使用 `region,action,month,master_count`，其中 `month=YYYYM<n>`、数量为非负整数，且 `(region,action,month)` 唯一。规则从题目侧站点动作表按 ISO 周所在自然月汇总完整 Region×action×YYYYMM 坐标，并与候选的 schema、动作全集、月份全集和每个数量精确比对；缺文件、缺动作/月、额外坐标、重复坐标、非法数量或任一数量不等均触发 prepared-master 硬门槛。该比对不以候选 `master_plan` 生成 O2 的 B，也不只检查文件存在。

`completion-by-deadline` 下，令 `P_g` 为权威主计划对 Region `g`（或其 `ALL` 回退曲线）实际覆盖的完整 `YYYYMM` 集合，令 `c_g=max(P_g)` 为 completion bucket：

```text
B_g,c_g = N_g
candidate install period p:
    p not in P_g -> INSTALL_OUTSIDE_DEADLINE
    p in P_g     -> A 统一归入 c_g
```

该模式只比较覆盖窗口内是否完成总量，不因窗口内月份间重分布扣分；不在 `P_g` 的年月即使早于最大年月也不视为合法。`scaled_target_grid`、覆盖年月集合和 completion bucket 均进入证据。

在权威固定计划模式下，`o2_target_curve_mode=fixed-plan`，B 直接由权威 `site_plan` 中 install 的 Region 与 `delivery_period` 构造，不执行主计划缩放。未显式声明新参数的存量 fixed-authority profile 自动推断 `fixed-plan`。

### 4.4 有效交付网格 A

一个权威目标安装站点只有同时满足以下条件才计入 A：

1. 每个 O2 作用域内的权威必需动作恰好一行，不缺失、不重复、不增加未知或作用域内额外动作；作用域外的合法 install/dismantle 行不参与 O2；
2. 必需字段、Region、站点和动作归属合法；`candidate-scheduled` 模式还要求批次归属合法；
3. 业务周、ISO 周和交付年月可唯一解析；
4. 每个必需动作的最终 BOM 满足严格物料合同；
5. 最终 BOM 动作周与同站点、同动作的计划一致；
6. 在 `candidate-scheduled` 模式且作用域包含拆除时，拆除周相对题目指定锚点满足最小或精确间隔；`anchor=batch-finish` 使用全局规范批次安装完成周，`anchor=site-install` 使用同一 Region—站点唯一合法安装周；install-only 作用域必须使用只含 `anchor=not-applicable` 的合同；`fixed-authority` 模式不执行该间隔校验。
7. `completion-by-deadline` 下，install 的 `delivery_period` 必须属于该 Region 的主计划覆盖年月集合；合法月份统一计入 Region completion bucket。
8. `candidate-scheduled + o2_monthly_capacity_mode=hard-limit` 下，每个 Region—自然年月最多接纳 `floor(master_capacity * o2_capacity_factor)` 个已通过前述校验的安装站点。超额时按规范 `site_key` 升序稳定接纳到上限，其余站点记录 `MONTHLY_CAPACITY_EXCEEDED` 并不进入 A；缺少该 Region—年月容量时上限为 0，只有权威 `ALL` 同年月可作为回退。O2 与 scheduling 同时启用时，两者容量倍率必须一致。

若某个唯一必需动作明确提交为 `status=unscheduled` 且时间字段为空，O2 只记录一次 `<ACTION>_UNSCHEDULED` 并使该站点不进入 A；不再级联记录不可解析周、动作缺失、最终 BOM 缺失或间隔锚点缺失。该语义只消除重复归因，不改变“未排入站点未有效交付”的业务结论。

在 `candidate-scheduled` 模式下，两类锚点共享同一合法安装行门槛：只保留权威范围内、恰好一条 install、时间及行合同合法且 Region/批次归属一致的目标站。`batch-finish` 再对同一规范批次取最大 `schedule_week`，锚点不按 Region 拆分；`site-install` 直接取同站 install 的 `schedule_week`，其他站或批次完成时间不得影响它。纯拆除站不进入 N、A 或 O2 分母。

严格物料合同如下：

- `identity-only` 模式直接按权威原始 BOM 编码做 identity 匹配，不读取 substitution catalog；
- 其他物料模式下，install 使用权威 substitution catalog 定义的替代 bundle；无论 target 是否在 catalog 中定义，同编码（忽略大小写）的原物料始终可以按 1:1 直接满足，不要求源关系表重复声明 identity；
- catalog 未定义的权威原料仍只有同编码 1:1 交付，不能据此推导其他替代关系；
- dismantle 逐项匹配权威原始 BOM 编码与数量，不使用安装替代关系；
- 合法 bundle 必须完整覆盖权威 BOM，候选数量必须恰好消费；空编码、非整数或零数量、题目数量模式下的错误符号、非法 Region/动作/时间以及额外动作都会使站点无效；
- 最终 BOM 数量符号由题目合同冻结：`signed-action` 要求 install 为正、dismantle 为负；`dismantle-absolute` 要求 install 为正，dismantle 可用正数绝对量或负数方向量，二者均按绝对值核算；历史兼容模式 `absolute` 对两类动作都接受正负非零整数并按绝对值核算；
- 可选 `o2_material_source_contract` 按 action 冻结非空允许值列表。`final_material.material_source` 经去除首尾空白并忽略大小写后匹配；未配置该合同的 profile 不检查来源字段；
- `o2_material_source_missing_effect` 只允许 `blocking` 或 `diagnostic`，且只能与 `o2_material_source_contract` 同时声明。未声明时默认 `blocking`：缺列或空值记录 `MISSING_MATERIAL_SOURCE` 并使该 action BOM 无效；`diagnostic` 时缺列或空值仍冻结行数和最多 50 条样例，但不加入行错误、动作失败原因或站点无效原因。非空但不在 action allowlist 的值始终记录 `INVALID_MATERIAL_SOURCE` 并阻断，不能被 diagnostic 放行；
- OUT 只表示既不属于权威原物料、也不属于任何合法 bundle 的编码；合法编码超量或未匹配不能标为 OUT；
- 计划外站点、orphan 最终 BOM 和纯拆除站仅形成 `score_effect=none` 的诊断，不重复扣分；
- `site_plan` 与 `final_material` adapter 的可读非阻断校验问题分别以精简 `site_plan_adapter_validation`、`final_material_adapter_validation` 公开，包含 issue 总数、样例以及 exact-columns 的缺失/意外列；两类证据固定 `score_effect=none`。缺少 O2 规范化必需列等阻断问题仍按候选产物非法处理。

```text
A_g,p = count(distinct valid target install sites in region g and delivery period p)
```

### 4.5 计算、状态与证据

```text
D_L1    = Σ_g,p |A_g,p - B_g,p|
Q       = |Σ_g,p A_g,p - N|
R       = (D_L1 - Q) / 2
L       = Q + R
F       = count(distinct dropped site identities submitted by candidate)
rate_O2 = clamp(1 - (L + F) / N, 0, 1)
score_O2 = round(100 * rate_O2, 6)
```

其中 `D_L1` 只保留为完整双侧偏差诊断，`Q` 是有效交付总量相对目标总量的数量差，`R=min(shortfall, overage)` 是月间重分配站点数。一个未超容量的有效站点从目标月份移到另一月份，会在 `D_L1` 中形成一缺一超，但在计分损失 `L` 中只计 1 个 `redistribution_unit`；单纯的月度节奏偏离不改变站点有效性。只有显式 `hard-limit` 容量门槛会把稳定选出的超额站点标为无效，移出 A 后由既有 `Q/R/L` 公式计一次损失，不再另加容量罚分。未声明固定种子 Drop 合同时 `F=0`。声明 `o2_install_only_contract` 且任一禁止动作行存在时，以上连续公式之后执行硬门槛 `rate_O2=0`。声明 `o2_prepared_master_plan_role` 且候选主计划未通过完整精确比对时，同样执行 `rate_O2=0 / PREPARED_MASTER_PLAN_MISMATCH`。

- `rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`；
- A 为空时 `Q=L=N`、得 0；站点跨月份移动时仍分别公开 shortfall 与 overage，但只以一个 `redistribution_unit` 进入 `L`；
- 公式不叠加第二份容量罚项、OUT 罚项或其他规则分数；`hard-limit` 只决定站点能否进入 A，超额造成的损失仍只通过统一的 `L` 计算。题面授权的固定 Drop 身份罚项、仅安装动作硬门槛与 prepared-master 完整性硬门槛属于 O2 自身合同；
- 候选计划模式下 `site_plan` 缺失/非法为候选侧 0 分；权威固定计划模式下同类错误为 `UNSCORABLE / EVALUATOR_ERROR`；
- `final_material` 缺失/非法为候选侧 0 分；`N=0`、权威曲线不可用或时间轴不唯一为 `UNSCORABLE / EVALUATOR_ERROR`。

核心证据包括计划模式、作用域动作、目标曲线模式、主计划覆盖年月、completion bucket、时间来源、短周策略、权威安装站点池、skip 分池 scope、Region/批次目标、间隔合同与锚点 scope、Hamilton quota、N、A/B 网格、`D_L1`、Q、R、L、有效/无效站点、多标签失败原因、月度容量模式/倍率/逐坐标原始上限/接纳与超额站点、作用域外合法动作、计划外/orphan 诊断、物料来源合同/effect/错误、非阻断 site-plan/final-material adapter 问题、最终 BOM 按 action 的提交符号统计、方向/绝对量归一化合同和错误归责。固定种子模式还冻结 Drop 算法/seed/源顺序/RNG 作用域、逐池身份、候选违规删除站点和 F；仅安装硬门槛冻结禁止动作合同、计划/最终 BOM 违规行及是否触发门槛；prepared-master 模式冻结两侧 schema、动作/月全集、坐标数、差异坐标和门槛状态。

## 5. 物料推演校验规则

### 5.1 S1 替代关系建模与应用

- **规则 ID**：`simulation.S1`。
- **业务含义**：同时评价替代关系模型与最终 BOM 中替代方案的实际应用。
- **输入**：权威 `substitution_source`、`scope_input`，被评分 `final_material`；题目合同需要候选关系时还使用 `material_substitution`。
- **最小计分单元**：关系因子使用关系对象 `(group, target_view, target, target_qty, priority, substitute_bundle, role)`；应用因子使用候选 install 应用单元。
- **计算公式**：

```text
F_model = |E_relation ∩ C_relation| / |E_relation ∪ C_relation|
P_apply = valid_candidate_install_units / candidate_install_units
rate_S1 = F_model * P_apply
score_S1 = round(100 * clamp(rate_S1, 0, 1), 6)
```

- **得分与状态**：不要求候选关系时 `F_model=1`；要求候选关系但 `E_relation ∪ C_relation` 为空时，Jaccard 因子同样取 1。没有候选应用单元但存在 final 行时 `P_apply=1`，两者都空时为 0。`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。
- **确定边界**：只评价 install。要求候选关系时，E 来自权威关系，C 与应用 alternatives 来自候选关系；否则 alternatives 来自权威关系。关系忠实度只评价题目/候选实际提交的替代关系行，不要求补造 identity 行；应用数量匹配器对每个原物料都增加同编码 1:1 直接满足选项。关系编译器的 `NEW_` 终端 fallback 与该 identity 常识是两项独立行为。
- **错误归责**：scope 等权威输入错误通常为 `UNSCORABLE / EVALUATOR_ERROR`；候选关系或 final 缺失/非法为候选侧 0 分。不要求候选关系时，当前 source 缺失分支会返回候选侧 `MISSING_ARTIFACT`。
- **核心证据**：model/apply 两率、关系交并差、无效 view、final 行/动作、失败应用单元和匹配缓存。

### 5.2 S2 可复用物料成熟供给

- **规则 ID**：`simulation.S2`。
- **业务含义**：评价拆除物料经过修复周期和复用率后形成的成熟供给，与被评分入库证据是否数量一致。
- **输入**：`gap`，或 `recovered_supply` / `site_material_timeline` 与 `reuse_warehouse`；可选 `initial_inventory_source` 作为 timeline-derived 分支的料号白名单。题面要求站点流转宽表时还消费候选 `site_rollout` 与正式候选 `site_plan`。
- **最小计分单元**：随证据模式分别为 `(region,item,week)`、`(item,week)` 或 item 汇总坐标。
- **计算公式**：对相同标准化键的非负数量：

```text
matched  = Σ_key min(expected_key, actual_key)
combined = Σ_key max(expected_key, actual_key)
rate     = matched / combined
axis_gap = matched_expected_weeks
           / (expected_weeks + extra_weeks_when_coverage_is_exact)
axis_rollout = ordered_matching_date_headers / max(expected_headers, actual_headers)
gap_zero = zero_declared_gap_units / declared_gap_units
rate_S2  = rate * axis_gap * axis_rollout * gap_zero
           # 仅在 S2 是相应辅助合同 owner 时乘入
score_S2 = round(100 * clamp(rate_S2, 0, 1), 6)
```

- **模式边界**：`gap-wide` weekly 按拆除周加 repair lead time 构造期望，并可叠加按 `(item,week)` 的仓库 overlap；aggregate gap 按 item 比较 dismantled、`totalArrive` 与仓库 inbound，最终 `rate_S2=0.5*q`；warehouse 模式优先使用 `recovered_supply`，否则从 timeline 推导。
- **周轴合同**：可选 `gap_week_contract` 的 `source=fixed` 由题目冻结首末周，`source=site-plan` 从正式候选 SitePlan 的最小、最大合法排程周生成连续期望轴；`coverage=exact` 同时处罚缺周与越界周，`coverage=contains` 只要求完整覆盖期望轴并允许推演尾周。`site_rollout_week_contract` 固定使用正式 SitePlan 的最小—最大 ISO 周生成逐周周一至周日表头（如 `2/1~2/7`），并按候选控制列后的实际表头顺序精确比较；缺文件、缺表头、越界或重排均进入得分。上述全局辅助合同只归属最先启用的 S2、S3、S4 之一，通常为 S2，禁止重复扣分。
- **安装-only 零业务合同**：`gap_zero_business_metrics` 只能声明规范 weekly 字段 `Dismantled`、`Arrive`、`DismantledSupply`、`ReuseConsumed` 和 summary 字段 `total_dismantled`、`initial_inventory`、`totalArrive`、`totalReuse`。每个 region—item block 的每个声明 weekly 单元及显式 summary 列都必须存在且为 0；缺列/缺单元不可按零补齐，非零和缺失分别输出违规/不可判定原因，并由同一辅助合同 owner 乘入得分。
- **得分与状态**：weekly/warehouse overlap 双方为空时该阶段为 1；aggregate gap 全空为 0，且该模式最多取得 50%。`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。
- **错误归责**：必需候选证据缺失或 blocking gap contract 为候选侧 0 分；timeline 分支配置的 `initial_inventory_source` 缺失返回候选侧 `MISSING_ARTIFACT`。warehouse/timeline 分支内部捕获的解析或参数异常返回候选侧 `FAIL / INVALID_ARTIFACT`；只有未被规则捕获并由 dispatcher 隔离的异常才返回 `UNSCORABLE / EVALUATOR_ERROR`。
- **核心证据**：alignment 模式、repair/reuse 参数、各阶段 `matched/combined`、gap/rollout 期望与实际轴、零业务逐字段缺失/非零单元、非法单元和 mismatch 样例。

### 5.3 S3 利旧仓守恒

- **规则 ID**：`simulation.S3`。
- **业务含义**：评价利旧仓库存流水是否满足逐期守恒、连续继承和非负约束。
- **输入**：题目合同指定的 `reuse_warehouse`、`initial_warehouse`，或 `gap-wide` 证据。
- **最小计分单元**：warehouse 模式为 `(business_dimensions..., item, week)` 库存单元，不强制要求 business dimensions 包含 Region；`gap-wide` 模式为 `(region,item,week)` 逐周单元，并为每个 `(region,item)` 增加一个 `totalReuse` 汇总单元。无法映射到上述单元的唯一结构问题作为额外失败单元。
- **计算公式**：两种模式都先执行守恒与连续性判断，但分母分别计算：

```text
closing_t = opening_t + inbound_t - outbound_t
opening_t = closing_(t-1)

balance_S3 = valid_cells / (warehouse_cells + extra_invalid_units)
             when evidence_mode = warehouse
balance_S3 = valid_units / (weekly_units + summary_units + extra_invalid_units)
             when evidence_mode = gap-wide

axis_warehouse = present_expected_item_weeks
                 / (expected_item_weeks + extra_item_weeks_when_exact)
zero_business  = all_zero_ledger_cells / configured_zero_ledger_cells
blackout       = zero_outbound_cells / submitted_cells_in_first_N_axis_weeks

rate_S3 = balance_S3 * axis_warehouse * zero_business * blackout
score_S3 = round(100 * clamp(rate_S3, 0, 1), 6)
```

- **得分与状态**：opening、inbound、outbound、closing 均须非负。`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。只有题目合同明确允许、且全部必需仓库角色均为纯 `MISSING` 时返回 100 / `OPTIONAL_WAREHOUSE_ABSENT_FULL_CREDIT`；未命中该策略时，任一必需角色缺失或结构不可用均为候选侧 0 分，可用空表因分母为 0 也得 0。部分提交、空表或不可解析均不能获得可选满分。
- **完整周轴**：`warehouse_week_contracts` 按仓库 role 逐项声明固定轴或 SitePlan 动态轴，以及 `exact`/`contains` 覆盖方式；每个 `(business_dimensions...,item)` 都必须提交期望轴上的零业务周，规则不得为候选填零。缺周和 exact 模式的越界周进入实际得分，不是诊断。多个 role 按 item-week 单元合并计算 axis factor。
- **禁用窗口与零业务合同**：`blackout_weeks=N` 检查利旧仓期望轴前 N 周的每个已提交单元 `outbound=0`；已迁移题应同时冻结该 role 的周轴，未迁移历史 profile 才以已提交周的稳定顺序回退。`warehouse_zero_business_roles` 指定的每个 role 必须在完整周轴上存在流水，且每个单元的 opening/inbound/outbound/closing 全为 0；缺文件、空表或省略零周不能冒充零业务。
- **模式边界**：`gap-wide` 从初始库存、成熟拆除供给与 reuse consumed 重建余额，并增加 `totalReuse` 汇总校验单元；若 S3 是 gap、site_rollout 或 gap 零业务辅助合同的最先启用 owner，再与相应 factor 相乘。gap-wide 的 blackout 使用期望 gap 轴前 N 周的 `ReuseConsumed=0`。
- **核心证据**：文件数、cell 数、有效/无效单元、逐 role 周轴期望/缺失/越界单元、blackout 违规、零业务违规、结构问题和失败单元的守恒/连续/符号信息。

### 5.4 S4 新料仓守恒

- **规则 ID**：`simulation.S4`。
- **业务含义**：评价新料仓库存流水是否满足逐期守恒和连续继承。
- **输入**：被评分 `new_warehouse`；不得使用 gap 替代。
- **最小计分单元**：标准化 `(business_dimensions..., item, week)` 库存单元，不强制要求 business dimensions 包含 Region；另计无法映射的结构问题。
- **计算公式**：

```text
closing_t = opening_t + inbound_t - outbound_t
opening_t = closing_(t-1)
balance_S4 = valid_units / (warehouse_cells + extra_invalid_units)
axis_S4    = present_expected_item_weeks
             / (expected_item_weeks + extra_item_weeks_when_exact)
rate_S4    = balance_S4 * axis_S4
score_S4 = round(100 * clamp(rate_S4, 0, 1), 6)
```

- **得分与状态**：opening/closing 固定允许负数，inbound/outbound 必须非负；不存在控制负库存的题目参数。`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。可选缺失满分只适用于题目合同明确授权且 `new_warehouse` 纯缺失；未命中该策略时，缺失或结构不可用为候选侧 0 分，可用空表因分母为 0 也得 0。空表、不可解析或部分证据均不能获得可选满分。
- **完整周轴**：`warehouse_week_contracts.new_warehouse` 与 S3 使用同一固定/SitePlan、exact/contains 合同；每个 ledger 业务键和物料必须保留期望轴上的零业务周。若 S2、S3 均未启用而 S4 成为 gap 或 site_rollout 辅助合同 owner，S4 还与对应的唯一 factor 相乘。
- **核心证据**：文件数、cell 数、有效/无效单元、期望/缺失/越界周单元、结构问题和失败单元明细。

### 5.5 S5 原始 BOM 需求覆盖

- **规则 ID**：`simulation.S5`。
- **业务含义**：评价已排程动作的最终物料是否覆盖相应权威原始 BOM 数量。
- **输入**：权威 `scope_input`、被评分 `site_plan` 与 `final_material`，以及题目合同选择的 `substitution_source` 或 `material_substitution`。
- **最小计分单元**：已排程 action key 下的权威原始 BOM 数量坐标。
- **计算公式**：

```text
rate_S5 = covered_authoritative_quantity_in_scheduled_actions
          / authoritative_quantity_in_scheduled_actions
score_S5 = round(100 * clamp(rate_S5, 0, 1), 6)
```

- **得分与状态**：全局权威需求量为 0 时返回 `NOT_APPLICABLE`、score 0；权威需求存在但已排程动作交集分母为 0 时得 0 / `NO_SCHEDULED_AUTHORITY_OVERLAP`；其他结果中，`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。
- **确定边界**：计划存在 status 列时只保留 `scheduled`，否则保留合法 install/dismantle；分母不扩展到未排程动作。关系来源选择与 S1 相同，数量匹配器对每个原物料都允许同编码 1:1 直接满足；关系解析错误记录后继续评分。最终 BOM 的 `signed-action`、`dismantle-absolute` 和 `absolute` 数量符号模式与 O2 严格物料合同一致，并由题目 profile 显式选择。
- **错误归责**：`site_plan` 或 `final_material` 缺失/不可用为候选侧 0 分；权威 `scope_input` 无法编译为 `UNSCORABLE / EVALUATOR_ERROR`。
- **核心证据**：权威数量、已覆盖数量、scope/排程动作数、无权威需求动作、缺失 final 动作、按 action 的提交符号统计、方向/绝对量归一化合同、关系解析和 traceability 信息。

### 5.6 S6 最终 BOM 与排程时间一致性

- **规则 ID**：`simulation.S6`。
- **业务含义**：评价最终 BOM 的动作时间是否与站点计划一致；不评价数量。
- **输入**：被评分 `site_plan`、`final_material`，以及 `project-week` 或 `action-week-month` 时间模式和非活动时间留空参数。
- **最小计分单元**：`(region,site,action)` 时间身份。
- **计算公式**：分母只包含计划中可解析且唯一的 reference 与 final action 的交集：

```text
rate_S6 = passed_time_units / comparable_time_units
score_S6 = round(100 * clamp(rate_S6, 0, 1), 6)
```

- **得分与状态**：无可比较单元时得 0 / `NO_COMPARABLE_TIME_UNITS`；其他结果中，`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。候选产物缺失或非法为候选侧 0 分。
- **确定边界**：`project-week` 只比较项目周；`action-week-month` 比较活动动作的周和月，并可要求非活动动作时间为空。缺失/额外 final action 和计划 reference 冲突只进入证据，不进入分母。多行 final 的时间全部一致时按一个单元。four-week-project 月份必须保留完整 `(year,month)`。
- **核心证据**：可比较/通过单元数、时间模式、计划冲突、缺失/额外动作和失败时间单元。

## 6. 利旧核算校验规则

### 6.1 R3 虚拟目标料交付合规

- **规则 ID**：`reuse-accounting.R3`。
- **业务含义**：评价虚拟目标料是否被合法实际料号替换交付。
- **输入**：权威 `scope_input`、`substitution_source`，计划 `site_plan` 和被评分 `final_material`。
- **最小计分单元**：`CONTEXTUAL` 模式为 `(action_key, original_bom)`；`LEGACY_RESIDUAL_ONLY` 模式为适用 install action。
- **计算公式**：

```text
rate_R3 = compliant_units / applicable_units
score_R3 = round(100 * clamp(rate_R3, 0, 1), 6)
```

- **模式边界**：`CONTEXTUAL` 要求实际编码非空、不同于 original、属于该 original 的权威 allowed codes，且业务键不重复；它不验证 bundle 数量。`LEGACY_RESIDUAL_ONLY` 只要求正数量 final 中不残留虚拟 target，不验证实际编码属于哪个 target。
- **得分与状态**：只检查正数量 install 行；任一 final 数量非整数时整项得 0 / `NON_INTEGER_QUANTITY`。无适用单元时返回 `NOT_APPLICABLE`、score 0；其他结果中，`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。
- **错误归责**：`final_material` 缺失/不可用为候选侧 0 分；候选计划模式下 `site_plan` 缺失也为候选侧 0 分，权威固定计划缺失为 `UNSCORABLE / EVALUATOR_ERROR`。权威替代源或范围错误为评测器错误。target/allowed-code 重叠门槛只在 legacy 模式执行。
- **核心证据**：适用/合规单元、模式、编码失败原因和数量问题。

### 6.2 R5 区域汇总与仓库出库对账

- **规则 ID**：`reuse-accounting.R5`。
- **业务含义**：评价 Region/物料汇总中的利旧与新料数量，是否与仓库实际出库一致。
- **输入**：`reuse_by_region`、`reuse_warehouse`、`new_warehouse`，以及可选 `initial_warehouse`；install-only 题可通过 `r5_zero_metrics` 声明必须无业务量的规范数量指标。
- **最小计分单元**：reuse/new 两个数量族各自使用 item 坐标；该族只有 summary 时使用全局 `__summary__` 坐标。
- **计算公式**：汇总 reuse 为 `Inter-Site Reuse` / `Reuse` 加 `Initial Stock Reuse`，new 为 `New Proposal` / `New`；仓库实际量取非负 outbound：

```text
matched_family  = Σ_key min(summary_family_key, warehouse_family_key)
combined_family = Σ_key max(summary_family_key, warehouse_family_key)

rate_R5 = (matched_reuse + matched_new)
          / (combined_reuse + combined_new)
score_R5 = round(100 * clamp(rate_R5, 0, 1), 6)
```

- **得分与状态**：总分母为 0 时得 100；其他结果中，`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。每个被检查的汇总数量行必须满足 `Total=ΣRegion`。若配置 `r5_zero_metrics`，每个指定指标必须至少出现一次，且其所有物料/summary 行的每个 Region 与 Total 都必须为整数 0；缺指标、非法值或任一非零量直接得 0 / `FORBIDDEN_REUSE_BUSINESS_QUANTITY`。除下述全缺失早返回外，`reuse_by_region` 缺失、结构非法、数量非整数或 Total 不守恒，以及必需 reuse/new warehouse 缺失或不可用，均为候选侧 0 分并输出相应原因码。
- **确定边界**：reuse 与 new 独立选择 item 或 summary 粒度；`initial_warehouse` 只并入 reuse outbound。`r5_zero_metrics` 在可选仓库全缺失策略之前执行，不能被 `full-credit` 绕过。若题目合同允许且未触发零量合同失败，`reuse_warehouse` 与 `new_warehouse` 均为纯缺失时可返回 100；部分缺失或非法仓库不适用。warehouse validation issue 可只改变 `reason_code` 而不改变公式分数。
- **核心证据**：两族的 matched/combined、汇总与仓库数量、零量指标逐行失败、缺失策略和 validation issues。

### 6.3 R6 利用率坐标准确性

- **规则 ID**：`reuse-accounting.R6`。
- **业务含义**：评价题目指定坐标范围和比率族是否由同一坐标的 Total 数量正确复算。
- **输入**：`reuse_by_region` 的数量与比率 Total 行，以及可选 `r6_contract={coordinate_scope,rate_families,zero_denominator_policy}`。默认合同保持物料级两族语义；题面只要求全国拆除重部署率时可冻结 `coordinate_scope=grand-summary-total`、`rate_families=[primary]` 和 `zero_denominator_policy=require-blank-rate`。
- **最小计分单元**：`(configured_coordinate, configured_rate_family)`；启用的 family 等权。
- **计算公式**：

```text
primary_expected   = Inter-Site Reuse / Dismantled
all_scope_expected = Inter-Site Reuse / (Inter-Site Reuse + New Proposal)

family_accuracy = correct_coordinates / expected_coordinates
rate_R6 = average(enabled family accuracies)
score_R6 = round(100 * clamp(rate_R6, 0, 1), 6)
```

- **得分与状态**：`reuse_by_region` 缺失或结构非法时为候选侧 0 分；默认物料范围只有 summary 行时得 0 / `MISSING_ITEM_RATE_EVIDENCE`，Grand Summary 范围缺少该坐标时得 0 / `MISSING_GRAND_SUMMARY_RATE_EVIDENCE`。`rate>=0.999999` 为 `PASS`，`rate<=0.000001` 为 `FAIL`，其余为 `PARTIAL`。`not-applicable` 策略下分母为 0 的坐标免校验；`require-blank-rate` 下仍要求对应 rate 行各且仅有一行且 Total 留空，否则该坐标失败。
- **确定边界**：`item-totals` 只消费非 summary 物料并忽略 summary；`grand-summary-total` 只消费规范 `Grand Summary` 并忽略物料明细，且 `Dismantled`、`Inter-Site Reuse`、`New Proposal` 三个核心数量 Total 行必须各且仅有一行、为非负整数。相关 numerator/denominator 数量行必须唯一；分母非零时 rate 行必须唯一。
- **精度合同**：候选比率只接受 `[0,1]` 小数或显式 `[0,100]%`；容差通常为展示精度半个末位并封顶 0.0001，无百分号且精度为 0 的 `0`/`1` 容差固定为 0。
- **核心证据**：坐标范围、启用比率族、零分母策略、各族 expected/correct/免校验数量、逐坐标状态，以及比率不符时的期望、实际、差值和容差。

## 7. 五项聚合指标

聚合策略内嵌在 `ruleset.yaml`，由 `aggregation/config.py`、`aggregation/methods.py` 和 `aggregation/service.py` 实现。当前 policy 为 `ei-five-metric-aggregate`；它与规则和 adapter 一起由 ruleset release `4.13.0` 原子冻结，不再拥有独立 schema 或 revision。

### 7.1 指标清单与共同公式

| 顺序 | 聚合指标 ID | 业务含义 | 输入规则 |
|---:|---|---|---|
| 1 | `effectiveness.o2` | 最终有效交付成效 | `effective-delivery.O2` |
| 2 | `key.raw` | 关键五项原始能力 | C2、C6a、O1、S1、S5 |
| 3 | `key.discrete` | 关键五项离散等级 | 同上 |
| 4 | `key.piecewise` | 关键五项连续分段表现 | 同上 |
| 5 | `all.raw` | 当前评分请求中全部非 O2 规则的原始表现 | 17 项非 O2 规则的启用子集 |

每个指标满分为 100。设输入规则分数为 `x_i`、变换为 `T_i`、权重为 `w_i`：

```text
aggregate = Σ_i w_i * T_i(x_i) / Σ_i w_i
```

当前 release 的所有权重均为 1。任何规则集合、权重、阶梯或变换变化都必须发布新的 ruleset release。五项指标之间不再求二次总分；兼容接口 `aggregate_total()` 仅返回 `key.discrete`，不能解释为五项总分。

### 7.2 `effectiveness.o2`：最终业务成效分

- **业务含义**：直接表达最终有效交付是否按目标 Region 和月份落地。
- **最小聚合对象**：`effective-delivery.O2` 的单项规则结果。
- **计算公式**：

```text
effectiveness.o2 = score(effective-delivery.O2)
```

- **聚合边界**：不加权、不离散、不分段、不补分、不叠加其他规则结果。O2 必须存在、已启用、可评分且位于 0—100；否则该指标返回错误。O2 为候选侧带原因码的 0 分时，数值保留 0，指标状态为 `INVALID_CANDIDATE`。
- **contribution**：固定 `check_id=effective-delivery.O2`、`weight=1`、`supported=true`、`filled=false`，`raw_score=transformed_score`。

### 7.3 `key.raw`：关键五项原始分

- **业务含义**：表达动作完整性、批次间隔、排程节奏、替代应用和 BOM 覆盖五项关键机制的原始表现。
- **最小聚合对象**：按固定顺序排列的 C2、C6a、O1、S1、S5 单项分数。
- **计算公式**：

```text
key.raw = (C2 + C6a + O1 + S1 + S5) / 5
```

- **缺失处理**：未在当前评分请求中启用的关键规则按 `unsupported_rule=full_credit` 补原始 100，并标记 `supported=false, filled=true`；已启用但缺少结果时返回错误。

### 7.4 `key.discrete`：关键五项离散分

- **业务含义**：把五项关键规则分别映射为固定等级，再等权汇总。
- **最小聚合对象**：单个关键规则的原始分数。
- **变换规则**：先计算扣分 `d=100-x`，再命中第一个满足 `d<=max_deduction` 的档位：

| 原始扣分 `d` | 等价原始分 `x` | 变换分 |
|---|---|---:|
| `0 <= d <= 5` | `95 <= x <= 100` | 90 |
| `5 < d <= 10` | `90 <= x < 95` | 80 |
| `10 < d <= 20` | `80 <= x < 90` | 60 |
| `20 < d <= 40` | `60 <= x < 80` | 40 |
| `40 < d <= 100` | `0 <= x < 60` | 0 |

```text
key.discrete = Σ_i ladder(x_i) / 5
```

原始 100 也映射为 90。未启用关键规则先补原始 100，因此离散贡献为 90。必须逐项变换后平均，不能先计算 `key.raw` 再做阶梯变换。

### 7.5 `key.piecewise`：关键五项分段分

- **业务含义**：连续压缩 60 分以下区间，并放大 60—100 区间的失分差异。
- **最小聚合对象**：单个关键规则的原始分数。
- **变换与公式**：

```text
T(x) = x / 3       , 0 <= x < 60
T(x) = 2x - 100    , 60 <= x <= 100

key.piecewise = Σ_i T(x_i) / 5
```

函数在 60 分处连续，`T(0)=0`、`T(60)=20`、`T(100)=100`。未启用关键规则补原始 100 后贡献 100。必须逐项变换后平均。

### 7.6 `all.raw`：全项原始分

- **业务含义**：表达当前评分请求中全部适用非 O2 规则的平均原始表现。
- **最小聚合对象**：一个已启用的非 O2 规则结果。
- **输入集合**：配置冻结 C1—C6b、O1、S1—S6、R3、R5、R6 共 17 项；计算时仅保留当前评分请求启用的子集。
- **计算公式**：

```text
all.raw = Σ score(enabled non-O2 rule) / count(enabled non-O2 rule)
```

未启用规则按 `unsupported_rule=excluded` 排除，不生成 contribution，也不进入分母。配置加载时必须证明 O2 与这 17 项规则共同精确覆盖当前 ruleset。
当题目 profile 只启用 O2、因而没有任何已启用的非 O2 规则时，`all.raw` 返回 `score=null`、`status=NOT_APPLICABLE`、空 contribution；这不是评测器错误，也不改变 O2 或三个关键分指标。

### 7.7 状态、缺失与精度

- 同一 `check_id` 出现重复结果时，五项聚合指标全部返回 `EVALUATOR_ERROR`；
- `UNSCORABLE` 或 `EVALUATOR_ERROR` 使受影响指标返回 `EVALUATOR_ERROR`；运行级 `QUESTION_CONTRACT_INCOMPLETE` 保留原状态；
- 当前实现不排除已启用规则的 `NOT_APPLICABLE`：其数值 0 进入对应分母，并因 `reason_code=NOT_APPLICABLE` 使指标状态为 `INVALID_CANDIDATE`；
- 候选侧带原因码的 0 分参与数值计算，同时使指标状态为 `INVALID_CANDIDATE`；
- 除 O2-only profile 的 `all.raw` 明确返回 `NOT_APPLICABLE` 外，无可聚合规则、分数非有限或超出 0—100 时返回评测器错误；
- 单运行聚合使用 `Decimal`，机器结果最多保留 6 位小数；XLSX 展示保留 2 位，不得用显示值反算机器结果。

## 8. 结果与证据合同

### 8.1 单项规则结果

每项已执行规则输出一个 `CheckResult`：

| 字段 | 合同 |
|---|---|
| `id` | 完整规则 ID；内存字段名为 `check_id` |
| `name` | 稳定规范名称 |
| `score` | 0—100，最多 6 位小数 |
| `status` | `PASS`、`PARTIAL`、`FAIL`、`NOT_APPLICABLE` 或 `UNSCORABLE` |
| `reason_code` | 稳定、可筛选；正常通过可为空 |
| `explanation` | 对评分口径和结果的说明 |
| `evidence` | JSON 可序列化证据；子字段由规则定义 |
| `prompt_refs` | 可定位到规范 Prompt 的依据 |

`QUESTION_CONTRACT_INCOMPLETE` 是题目合同在执行前被阻断时的运行级状态，不通过伪造单项规则结果表示。候选产物错误与评测器错误必须分别归责，不能互相转换。

### 8.2 内部组件结果与公开结果

内部组件结果使用统一 contract 的 `document_type=component-result`，包含组件元数据、标准化产物信息、规则结果和组件状态。

该格式只用于内部兼容与测试。公开 `eval` 生产链在内存中汇总组件结果，最终只写统一 contract 的 `document_type=run-score`：

```text
<run>/scores/<YYYYMMDDHHMMSS[-NN]>/score.json
```

`score.json` 记录 provider、题目、score ID、运行元数据、ruleset release、题目根目录、profile/prompt/manifest/input 的实际来源路径、产物选择状态与 `resolution_diagnostics`、五项聚合指标、contribution、全部规则结果和组件状态。候选路径按运行目录相对化，题目输入路径按仓库根目录相对化，不把本机绝对路径作为规范证据。

## 9. 使用、repeat 与报告

### 9.1 公开命令

```bash
eval score run RUN_DIR
eval score batch --task EI --model gpt5.6 --repeat latest
eval score batch --selector selectors/ei.yaml --report
eval report --task EI --skill noskill --repeat average --score-id latest
```

应用层负责运行选择、批次、score/report ID 和持久化，不理解 EI 业务公式。EI provider 固定为 `simulation.ei`。

### 9.2 repeat 与跨题汇总

repeat 分组键为 `(任务, 题目及版本, 模型, Harness, skill)`：

- `latest` 按 `(execution_date, execution_run, timestamp, run_name.casefold())` 选择每组最新运行；
- `average` 保留组内全部运行，对五项指标和逐规则 contribution 分别求算术平均；
- repeat 收敛后，跨题汇总按 question row 平均，即一题一票；同题运行次数和规则数量不改变题票权重。

报告必须为每个所选运行解析同一显式 score ID；`score_id=latest` 时分别读取各运行 score-id 路径上最新的 `score.json`，若该结果损坏则报告失败，不回退到更早的结果。规范结果缺少五项指标、provider 或题目不匹配时同样失败，不以 0、100 或空白修复损坏结果。只有聚合状态明确为 `NOT_APPLICABLE` 或 `QUESTION_CONTRACT_INCOMPLETE` 时，`score=null` 才是合法结果；其他状态的空分必须拒绝。repeat 组内同一指标不得混合数值与合法空分。

### 9.3 固定九 Sheet

每份报告生成 `selection.json`、`aggregation.json`、`EI推演打分-<report_id>.xlsx` 和 `report_manifest.json`。工作簿 Sheet 名称与顺序固定：

1. `O2目标分天梯图`；
2. `五项分段分天梯图`；
3. `五项分段分详表`；
4. `五项离散分天梯图`；
5. `五项离散分详表`；
6. `五项原始分天梯图`；
7. `五项原始分详表`；
8. `全项原始分天梯图`；
9. `全项原始分详表`。

天梯图按已有数值平均分降序、同分标签升序排列，无数值者置后。稀疏矩阵中不存在的模型—题目组合，以及状态为 `NOT_APPLICABLE` 或 `QUESTION_CONTRACT_INCOMPLETE` 的合法空分均留空；模型、题目和跨题平均值只统计数值单元格，纯空集合保持空白。JavaScript 构建器负责布局，并把 XLSX 导出与 preview 渲染作为两个隔离操作执行，避免原生预览器异常破坏已经生成的工作簿。Python report service 校验九张 preview 的集合和最终 ZIP 完整性；Windows 上 artifact-tool 原生预览进程异常退出时，允许调用本机 Excel 完成兼容性收尾，但只可写入冻结标题行和标识列所需的 Sheet 视图元数据，不得修改评分单元格、公式或聚合结果。Excel 将同一预览范围导出为单页 PDF，再由 Poppler `pdftoppm` 转为九张 PNG，避免依赖交互式剪贴板。

## 10. 实现映射与依赖边界

| 责任 | 当前实现 |
|---|---|
| release、规则 ID 与内嵌聚合策略 | `evaluation/src/simulation/ei/ruleset.yaml` |
| 所有 EI 文档结构 | `evaluation/src/simulation/ei/contracts/ei-contract.schema.json` |
| 题目输入、规则选择、参数和 Prompt 依据 | 正式题 `evalsets/simulation/*/validator.yaml`；训练变种题 `datasets/*/validator.yaml` |
| 产物发现、校验与标准化 | `evaluation/src/simulation/ei/core/adapters/` |
| 公共解析、计分和错误结果 | `evaluation/src/simulation/ei/rules/ei_standard/common.py`、`_shared.py`、`preparation.py` |
| C1—C6b、O1 | `evaluation/src/simulation/ei/rules/ei_standard/scheduling/` |
| O2 | `evaluation/src/simulation/ei/rules/ei_standard/effective_delivery/` |
| S1—S6 | `evaluation/src/simulation/ei/rules/ei_standard/simulation/` |
| R3、R5、R6 | `evaluation/src/simulation/ei/rules/ei_standard/reuse/` |
| 规则执行与异常隔离 | `evaluation/src/simulation/ei/core/engine.py`、`core/models.py` |
| 五项聚合 | `evaluation/src/simulation/ei/ruleset.yaml` 的 `aggregation`、`aggregation/` |
| EI provider 与公开 run score | `evaluation/src/simulation/ei/provider.py`、`scoring/` |
| repeat 与报告数据 | `evaluation/src/simulation/ei/reports/service.py` |
| XLSX 布局、导出与 artifact-tool 预览 | `evaluation/src/simulation/ei/reports/build_ei_score_report.mjs` |
| Windows Excel 与 Poppler 只读预览回退 | `evaluation/src/simulation/ei/reports/render_ei_report_preview.ps1` |

依赖方向固定为：

```text
adapter -> rule -> aggregation -> report
```

规则不得发现文件、读取 GroundTruth、调用其他规则结果或计算聚合分；aggregation 不读取业务产物；report 不重新计算规则或聚合公式。

## 11. 测试与验收要求

- `ruleset.yaml` 必须加载为 release `4.13.0`，18 项完整 ID 和内嵌聚合策略必须和本文件及代码一致；
- 每项规则必须覆盖通过、部分得分、零分、空集合、候选错误和评测器错误等适用边界；
- O2 必须覆盖单年度短周补年、schedule-week 短标签/正确显式年份兼容及错误显式年份阻断、跨年禁推断、非法 ISO 周、Hamilton 分配、Region—批次/Region 两种 Drop 分池、作用域动作过滤、逐月分布/截止期完成/fixed-plan 三种目标模式、全局批次/同站安装/not-applicable 三种锚点、`unscheduled+空时间` 单次未交付、题目 Region 冲突评测器归责、物料来源缺失 blocking/diagnostic 两种 effect 与非空非法值始终阻断、site-plan/final-material 非阻断 adapter 证据、同编码 1:1 直供、三种最终 BOM 数量符号模式、严格物料合同和 A/B 公式；
- S5 必须覆盖 `signed-action`、`dismantle-absolute` 和 `absolute`，并证明只允许 Dismantle 正数的窄模式不会放过负数 Install；
- 聚合必须覆盖离散阶梯边界、分段函数、未启用关键规则补位、全项排除、强制 O2、重复 ID 和五项顺序；
- 报告必须覆盖 latest/average、一题一票、稀疏空白、合法空分、意外空分拒绝、repeat 数值/空分混合拒绝、九 Sheet 顺序和真实 XLSX 完整性；
- 统一结果 schema、规则执行顺序独立性、GroundTruth 隔离和模块依赖方向必须有合同测试。

测试代码是覆盖事实源；文档中的验收要求不能替代真实断言，也不能把尚未实现的测试描述为已经通过。

## 12. 评审清单

- [ ] 当前规则数为 18，稳定 ID 与 `ruleset.yaml` 一致；
- [ ] 每项规则均明确业务含义、输入、最小计分单元、公式、状态、错误归责和证据；
- [ ] Region、站点、动作、批次、物料、数量和时间身份与实现一致；
- [ ] 空集合、空分母、重复、额外数据、可选缺失和不可评分条件逐规则明确；
- [ ] O2 的单年度补全、跨年禁推断、Drop 分池、动作范围、目标网格/截止期、间隔锚点、物料来源、有效站点和严格物料合同完整；
- [ ] 五项聚合的规则集合、补位、排除、阶梯、分段函数、状态与精度符合 ruleset release `4.13.0`；
- [ ] O2 只做原始分直通，未进入关键五项或全项分母；
- [ ] 公开落盘只使用统一 contract 的 `run-score` 文档，报告不重新评分；
- [ ] 实现遵守 `adapter -> rule -> aggregation -> report` 依赖方向；
- [ ] 文档不维护逐题配置映射、历史演进或未由当前实现支持的语义。
