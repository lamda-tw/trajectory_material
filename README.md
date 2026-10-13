# taowen 工作区

本仓库记录工具型智能体的轨迹数据、训练代码、评估工具和实验结论。主线是在 **Qwen3-8B / AppWorld** 上研究：成功轨迹 SFT、能力边界上的单步修复（CFST）、轨迹级 rubric GRPO，以及步骤级 rubric 筛选与局部 SFT。另保留早期高 O2 数据处理、通用轨迹评估和 SWE-bench 探索。

**更新至 2026-10-13。** 本页是工作区总览；具体配置、逐题结果和复现证据以各实验目录中的冻结方案、配置、报告及机器可读摘要为准。

## 1. 当前进展与主要结论

| 研究阶段 | 已完成的工作 | 当前证据 |
| --- | --- | --- |
| 数据与运行链路 | 高 O2 数据转换、AppWorld 教师轨迹采集、SFT、隔离推理和官方评测 | 已覆盖数据校验、模型保存/重载、逐任务结果与训练记录 |
| 成功轨迹 SFT | 67 条与 90 条教师轨迹；LoRA / 全参数、不同轮数对照 | train90 LoRA 的历史 Dev57 为 **23/57**，test_normal168 为 **51/168**；已测全参数方案低于该对照 |
| Dynamic CFST | 学生失败状态上的教师单动作修复；State / Action / Mixed 对照 | Action 一轮在 Dev57 为 **31/57**；尚未完成新一轮数据刷新与迭代 |
| 静态轨迹 rubric GRPO | SFT LoRA 的 540 条轨迹、21 项评分、一次全量策略更新 | 更新后 Dev57 **16/57**、test_normal168 **37/168**，均低于历史 SFT LoRA 对照 |
| 步骤 rubric | R1–R8、P/F/U/N；v1–v5 迭代、v5 全量评分、英文 v6 pilot 与全量评分 | 原始模型的 **540 条 / 11,254 步 / 90,032 标签**已完成两套配置评分；没有独立金标总体准确率 |
| 局部 SFT | 用 v5 筛选学生原动作；匹配监督 token 的 uniform 对照；另一配方五轮训练 | 原配方 Dev57：base **3/57**、uniform **6/57**、rubric **4/57**；新配方第 1/3/5 轮为 **13/57、10/57、8/57** |
| 下一阶段 | 从较强的 train90 SFT LoRA 出发，结合局部 SFT 与在线官方结果 RL | **计划阶段，尚未执行**；需要先给该 LoRA 自己的 540 条轨迹做步骤评分 |

这些结果属于不同数据来源和推理协议，不能直接合成一个模型排行榜。尤其要区分原始模型、train90 SFT LoRA 和从原始模型重新初始化的局部 SFT；训练 loss、rubric 标签质量与官方任务成功率也不是同一个指标。

## 2. 从哪里看

| 内容 | 入口 |
| --- | --- |
| 数据版本与转换说明 | [高 O2 数据](data/2026-09-08/README.md) · [AppWorld 67 轨迹](data/2026-09-15_appworld_qwen3-8b_react_sft_67/README.md) · [Codex RFT train90](data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/README.md) |
| 通用评估工具 | [统一评分 CLI](evaluation/README.md) · [HTML 轨迹评估](evaluation/src/eval4trajectory/README.md) |
| 共用训练与采样脚本 | [scripts](scripts/) · [教师轨迹采集说明](scripts/appworld_train_codex_trajectories/README.md) |
| CFST | [实验总览](experiments/2026-09-28_dynamic_cfst/README.md) · [研究方案](plans/2026-09-28_capability_frontier/README.md) |
| 轨迹级 rubric / GRPO | [SFT LoRA 完整阶段报告](experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md) · [研究计划](plans/2026-10-08_rubric_research/README.md) |
| 步骤级 rubric | [规范与版本](plans/2026-10-12_appworld_step_rubric/README.md) · [v5 全量报告](experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md) · [英文 v6 全量报告](experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol/REPORT.md) |
| 局部 SFT | [rubric / uniform 对照](experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/REPORT.md) · [五轮及第 1/3/5 轮验证](experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/REPORT.md) |
| 待执行方案 | [SFT 初始化 + 局部 SFT + 在线 RL](plans/2026-10-13_appworld_sft_init_local_sft_online_rl/PLAN.md) |

目录分工：`data/` 保存数据版本与转换证据，`scripts/` 保存共用执行代码，`evaluation/` 保存评分工具，`experiments/` 保存每次实验的配置和结果，`plans/` 保存研究设计与版本记录。历史计划描述的是当时的安排，不等于所有阶段都已执行；最新完成情况优先看对应最终报告。

## 3. 数据与基础工具

### 3.1 三批主要 SFT 数据

| 数据版本 | 来源与规模 | 处理方式与边界 |
| --- | --- | --- |
| [2026-09-08 高 O2](data/2026-09-08/README.md) | 7 条高 `effectiveness.o2` 轨迹，1,627 个决策样本 | 按 5 个 task family 做 grouped 5-fold；fold05 为 train 952 / validation 675；去除 source thinking、规范工具调用、仅监督 completion；工具 schema 来自观测调用推断 |
| [2026-09-15 AppWorld 67](data/2026-09-15_appworld_qwen3-8b_react_sft_67/README.md) | 67 条通过官方评测及干净重放的教师轨迹，640 个决策样本 | 完整行动前历史作为 prompt、当前 assistant 动作作为 completion；32,768 长度内不截断 |
| [2026-09-21 Codex RFT train90](data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/README.md) | 90 条真实环境成功轨迹，1,170 个决策样本 | 转换设置 `enable_thinking=False`，训练长度 40,960；教师 observation 有脱敏及 24,000 字符截断；9 条成功轨迹含执行错误后的恢复，不能统称为全部干净重放验证 |

教师采集经历了三步：

- [单任务原型](experiments/2026-09-14_appworld_react_trajectory_229360a_3/)验证轨迹、tokenizer 与训练样本表示；随后[第一批 90 任务采集](experiments/2026-09-14_204850_appworld_train_codex_trajectories/artifacts/summary.json)得到 67 条 verified 轨迹，另外 12 条 rejected、11 条 failed，67 条均通过重放。
- [10 家族 pilot](experiments/2026-09-20_091734_appworld_codex_rft_10family_pilot/REPORT.md)覆盖 10 题，首次尝试 10/10 成功，共 124 步、59/59 官方条件通过。
- [train90 无人值守采集](experiments/2026-09-20_103356_appworld_codex_rft_train90_unattended/REPORT_CN.md)使用 `gpt-5.6-sol / high`、4 个 worker、每次最多 40 次环境交互；91 次尝试得到 90 条成功轨迹，89 题首次成功、1 题第二次成功。

采集链路隔离隐藏 evaluator 实现，行动反馈来自真实环境；官方结果用于验证。数据转换、输入长度和监督区间分别有清单与校验记录，不能仅凭生成脚本正常退出认定数据合格。

### 3.2 训练、运行与评估基础设施

- **LoRA 与全参数训练**：[minimal_sft_train.py](scripts/minimal_sft_train.py) 支持 LoRA / 双卡 DDP；[full_sft_train_fsdp.py](scripts/full_sft_train_fsdp.py)、[full_sft_train_fsdp_scheduled.py](scripts/full_sft_train_fsdp_scheduled.py) 和 [full_sft_runtime.py](scripts/full_sft_runtime.py) 支持全参数 FSDP、学习率调度及恢复。早期 [fold05 smoke](experiments/2026-09-09_minimal_qwen3-8b_lora_2gpu_fold05_smoke/REPORT.md) 与[完整一轮](experiments/2026-09-09_full_qwen3-8b_lora_2gpu_fold05_epoch1/REPORT.md)验证了训练、保存和重载；后者训练 952 条、验证 675 条、476 次更新，尚不是端到端 O2 效果验证。
- **AppWorld 运行链路**：从[单任务 smoke](experiments/2026-09-10_173848_appworld_qwen3-8b_react_oneshot_smoke/README.md)扩展到完整 Dev / Test；使用隔离配置与独立环境保存任务状态、官方终态结果和报告。后续支持多 worker / 双 GPU 分片及合并核对。
- **EI 评分**：[evaluation](evaluation/README.md) 提供 `eval` CLI，当前注册 `simulation/ei`，包含 18 个校验规则、O2 成效分、关键五项的三种聚合口径与全项原始分；支持单次/批量评分、selector、预览和 XLSX 报告。
- **HTML 轨迹评分**：[eval4trajectory](evaluation/src/eval4trajectory/README.md) 实现 12 项确定性 MVP 指标，原始满分 50；同时报告原始分、已评价满分、归一化分和覆盖率。缺少证据标记 `not_observed`，不自动判满分。

## 4. AppWorld 成功轨迹 SFT 与历史对照

### 4.1 原始模型与 67 条教师轨迹

| 实验 | Dev57 成功数 | 其他结果 / 说明 |
| --- | ---: | --- |
| [原始 Qwen3-8B one-shot](experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/FULL_DEV_RUN_REPORT.md) | 5/57（8.8%） | SGC 0；完成全量运行与官方评分链路 |
| [67 轨迹 LoRA，5 epoch](experiments/2026-09-15_174500_appworld_qwen3-8b_react_lora_aligned_full_dev/REPORT.md) | 5/57（8.8%） | SGC 1/19；官方条件通过 105/291 |
| [67 轨迹全参数，2 epoch](experiments/2026-09-15_220731_appworld_qwen3-8b_react_full_sft_epoch2_aligned_full_dev/REPORT.md) | 0/57 | 官方条件通过 64/291 |
| [67 轨迹全参数，5 epoch](experiments/2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev/REPORT.md) | 0/57 | 官方条件通过 86/291 |

[LoRA 训练](experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/REPORT.md)与[全参数训练](experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/REPORT.md)均完成 5 epoch / 1,600 次更新；训练 loss 下降没有转化为 Dev 任务收益。[训练集内 15 题四模型诊断](experiments/2026-09-16_154629_appworld_train15_four_models_aligned/artifacts/REPORT.md)中，原始模型、LoRA、全参数 epoch2 / epoch5 分别成功 1、4、0、0 题；这是训练集内检查，不能视为泛化结果。

[原始模型 test_normal168](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/REPORT.md)为 **12/168（7.1%）**，SGC 0，官方条件通过 386/1,077；23 题达到 50 步上限，45 题出现过 reasoning-only 的生成长度截断（共 80 次）。

### 4.2 Codex RFT train90：LoRA 与全参数

全参数分支的训练设计与资源安排见[原始方案](plans/2026-09-23_train90_full_sft/README.md)，实际完成情况如下。

| 模型 | Dev57 TGC | test_normal168 TGC | test_normal SGC |
| --- | ---: | ---: | ---: |
| [train90 LoRA，5 epoch](experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/REPORT.md) | [23/57，40.4%](experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/REPORT.md) | [51/168，30.4%](experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/REPORT.md) | 9/56，16.1% |
| [train90 全参数，5 epoch](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/REPORT.md) | [12/57，21.1%](experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md) | [28/168，16.7%](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/REPORT.md) | 3/56，5.4% |
| [train90 全参数，2 epoch / prefix5](experiments/2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5/REPORT.md) | 未报告 | [28/168，16.7%](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/REPORT.md) | 5/56，8.9% |

- train90 LoRA 是后续 CFST 和静态 GRPO 使用的较强起点。其 Dev / Test 官方条件分别通过 206/291、598/1,077。
- 全参数 5 epoch 完成 2,925 次更新，使用 bf16 计算/导出、FP32 Adam 状态；训练 loss 从约 0.590 降至 0.0168。Test 相对 LoRA 新成功 10 题、退化 33 题，不能用训练 loss 代替任务能力。
- `epoch2_prefix5` 是**重新训练两轮、保留五轮 cosine 调度前缀**的独立实验，共 1,170 次更新；不是从五轮实验直接取出的同一次运行检查点。两种全参数方案 Test 成功数相同，但成功任务只重合 17 题，各有 11 题不同，不足以断言“五轮退化仅由过拟合导致”。
- [24 题上下文诊断](experiments/2026-09-22_101628_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal_context40960_24/REPORT.md)仅重跑 LoRA 先前的上下文失败题：窗口由 32,000 扩至 40,960 后成功 1/24，上下文拒绝由 24 题降至 8 题。它不是新的完整 test_normal168 成绩。

### 4.3 推理设置应在哪里核对

详细设置看对应实验的 `REPORT.md`、`config/` 和启动脚本；训练轮数、优化器更新次数与环境交互步数分别记录，不能互换。

- 历史 AppWorld ReAct 主线通常使用 **每题最多 50 步、每次最多生成 3,000 token、上下文 32,000、temperature 0、seed 100**；达到任一上限都可能提前结束，50 是上限而不是固定运行次数。
- 原始模型 2026-09-10 Dev 和 2026-09-17 Test 使用 Qwen 默认 thinking 与 `deepseek_r1` reasoning parser。历史 train90 对照未启用该 parser、未显式覆盖 `enable_thinking`；数据转换时关闭 thinking 不等于所有推理服务也做了同样配置。
- 2026-10 的多样性采样与 10-13 局部 SFT 验证显式关闭 thinking；前者使用 temperature 1，后者使用 temperature 0。最新同协议原始模型 Dev 是 3/57，应与其局部 SFT 对照一起解读，不能替换历史 5/57。
- **vLLM 是加载模型并提供推理 API 的服务引擎**，不是另一套训练方法或模型。具体版本、reasoning parser、chat template、上下文和并发参数均属于实验设置；设置差异会影响结果。
- TGC 按任务成功计算；SGC 按 scenario 整组任务是否成功计算。通过部分官方条件、调用 `complete_task` 或执行代码无异常，都不等于任务成功。

## 5. Dynamic CFST：针对能力边界的单步修复

[完整实验](experiments/2026-09-28_dynamic_cfst/README.md)先对 train90 做学生 rollout，起点成功 **46/90**。再按任务族分成 source60 / check30，基于学生状态收集并验证教师的单动作修复，形成 **State 12 条、Action 8 条、Mixed 20 条**训练集。这里训练的是失败轨迹中的局部修复，并非重新收集完整教师轨迹。

| 阶段 | State | Action | Mixed | 对照与解释 |
| --- | ---: | ---: | ---: | --- |
| 早期约 8k 目标 token 匹配训练，check30 | 13/30 | 14/30 | 14/30 | 起点 17/30；不同组更新 27/22/25 次 |
| [每条修复一轮，check30](experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md) | 17/30 | 19/30 | 15/30 | 更新 6/4/10 次；训练预算与上一行不同 |
| 一轮修复后 Dev57 | [25/57](experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/README.md) | [31/57](experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md) | [21/57](experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/README.md) | 历史起点 23/57 |

Action 一轮的 Dev TGC 为 **54.4%**，SGC **31.6%**，官方条件通过 215/291；相对起点新增成功 14 题、退化 6 题。不同修复类型和训练预算的效果不一致，不能从这次结果推出“修复更多、训练更久就更好”。尚未完成方案中的 source60 数据刷新和后续迭代。

## 6. 静态轨迹 rubric 与一次 GRPO 更新

### 6.1 两个采样起点

| 来源 | 采样量 | 官方成功 | 全失败 / 混合 / 全成功任务组 | 总步骤 |
| --- | ---: | ---: | ---: | ---: |
| [原始 Qwen3-8B](experiments/2026-10-08_static_rubric_grpo/README.md) | train90 × 6 = 540 条 | 39/540 | 70 / 20 / 0 | 11,254 |
| [train90 SFT LoRA](experiments/2026-10-08_static_rubric_grpo_lora_init/README.md) | train90 × 6 = 540 条 | 186/540 | 23 / 63 / 4 | 9,886 |

两组均使用 temperature 1、top_p 1、top_k -1、repetition penalty 1、关闭 thinking、50 步 / 3,000 生成 token / 32,000 上下文，不截断历史。LoRA 分支修复 Ellipsis 序列化问题后保留已有 342 条、恢复完成另外 198 条；最终统计覆盖完整 540 条。

### 6.2 评分、更新与验证

对 **SFT LoRA** 的 540 条轨迹完成 21 项静态 DRACO rubric 评分，共 **11,340 个判断**，90 个任务组均有非零组内 advantage。[正式训练](experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step06_train90_two_gpu/README.md)在引擎检查后重新从初始 SFT LoRA 加载；双 GPU 各处理 45 题 / 270 条，汇总全部梯度，执行 **一次 optimizer step、一个 PPO epoch**。参考策略冻结，真实重载 logprob 对齐检查通过。原先讨论的五轮离线训练没有执行。

| 完整评测 | 更新前历史 SFT LoRA | 一次更新后 | 逐题变化 |
| --- | ---: | ---: | --- |
| [Dev57](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_dev57/REPORT.md) | 23/57（40.4%） | 16/57（28.1%） | 新成功 4、退化 11 |
| [test_normal168](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/REPORT.md) | 51/168（30.4%） | 37/168（22.0%） | 新成功 7、退化 21；SGC 仍为 9/56 |

[训练诊断](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/TRAINING_DIAGNOSIS.md)与[失败案例](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/CASE_STUDIES.md)指出：280 条正 advantage 轨迹中有 122 条官方失败，同时 27 条官方成功轨迹得到负 advantage；将同一轨迹 advantage 赋给整段动作，可能同时强化错误步骤。21 个退化任务中 16 个只差一个官方条件，不能简单归因于上下文耗尽。初始策略与参考策略相同时，首次更新点的 KL 值及梯度为零。

这些是单次更新的观测和机制诊断，不是因果消融；尚不能证明唯一原因是学习率，也不能把它视为完整 DRACO 复现的最终效果。由此转向更细的步骤级反馈与局部训练。

## 7. 步骤级 rubric：v1–v6 与两轮全量评分

### 7.1 定义与版本

[规范、prompt、schema 和校验代码](plans/2026-10-12_appworld_step_rubric/README.md)按整条轨迹调用裁判、逐步输出八个维度，保留短依据，不预先合成一个总奖励：

| 维度 | 评价内容 | 维度 | 评价内容 |
| --- | --- | --- | --- |
| R1 | 执行有效性 | R5 | 动作与实际效果 |
| R2 | 证据与覆盖 | R6 | 反馈与恢复 |
| R3 | 状态与数据保真 | R7 | 终止与交付 |
| R4 | 决策逻辑与计算 | R8 | 权限与交互协议 |

标签为 **P：满足、F：明确违反、U：适用但证据不足、N：不适用**。U / N 不等于失败，N 也不能当作额外通过；局部步骤合理、诚实报告失败和最终任务成功需要分别判断。

[v1–v5 pilot](experiments/2026-10-12_appworld_step_rubric_pilot/README.md)逐步修订适用性、局部/全局边界和输出形式。v5 pilot 使用 12 条轨迹、201 步、两次重复调用；开发回归及新增样例复核不是独立准确率评估。[版本记录](plans/2026-10-12_appworld_step_rubric/VERSIONS.md)保留各次改动依据。

### 7.2 v5 中文与 v6 英文全量结果

两轮使用**同一批原始 Qwen3-8B** 的 540 条轨迹：90 题、每题 6 条、11,254 步、90,032 标签；官方成功 39 条、失败 501 条。它们不是 SFT LoRA 的 540 条 / 9,886 步数据。

| 配置 | 完成情况 | 调用与耗时 | 主要产物 |
| --- | --- | --- | --- |
| [中文 v5 / gpt-5.6-sol / high](experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md) | 540/540 有效；全部重新调用 | 542 次，2 次格式失败重试；1 小时 52 分 51 秒 | 步骤标签、轨迹聚合、6,381 条候选记录及复核表；候选记录不是已确认正确的训练动作 |
| [英文 v6 format / gpt-6.1-sol / high](experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol/REPORT.md) | 540/540 有效；输入与 v5 逐字节一致 | 547 次，5 次格式失败、2 次服务容量失败；2 小时 32 分 40.6 秒 | 标签、机械检查、逐单元差异、复核与计时；10,131/90,032 个标签发生变化 |

v6 全量评分前完成了[英文 pilot](experiments/2026-10-13_appworld_step_rubric_v6_en_pilot/REPORT.md)：36 条独立轨迹，12 条开发集、24 条按任务族留出的集合，含版本/重复比较共 84 次有效调用。[语言与版本准备目录](experiments/2026-10-13_appworld_step_rubric_v6_language_prep/README.md)保留准备过程及最终全量入口。

v6 对若干已知边界有所改善，但仍检出 8 处 R5 适用性错误，也有 R6 恢复漏评和 R7 边界争议。R5 仅在 278/11,254 步上适用（2.47%），大量 N/N 会抬高表面一致率。复核使用有选择的既有样例，缺少独立金标，**不能宣称总体准确率达到 95%**。

中文 v5 → 英文 v6 同时改变了语言、规则版本与裁判模型，因此不是单独验证语言效果的消融。v6 标签也没有自动替换已完成局部 SFT 所用的 v5 数据；其训练收益尚待验证。

## 8. 学生原动作的局部 SFT

### 8.1 同监督 token 预算的 rubric / uniform 对照

[第一轮实验](experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/REPORT.md)仅使用原始 Qwen3-8B 的 540 条轨迹及既有 v5 标签，不新生成教师动作、不追加裁判调用。从同一原始基座重新初始化 LoRA，比较机械可用池内的 uniform 选样与 rubric 选样，保留每个动作之前的历史，仅监督既有 assistant 响应。

机械共同池为 5,234 步，rubric 语义候选池为 2,580 步。按每题监督 token 配额匹配后，rubric 使用 2,440 步、uniform 使用 2,239 步，**两组各 196,608 个监督 token、48 次更新**。LoRA 为 r16 / alpha32，学习率 5e-5，warmup + cosine，按 token 归一化 loss。

| 同一推理协议的 Dev57 | 成功数 | TGC |
| --- | ---: | ---: |
| 本轮原始模型对照 | 3/57 | 5.26% |
| uniform 局部 SFT | 6/57 | 10.53% |
| rubric 局部 SFT | 4/57 | 7.02% |

单个训练 seed 和 57 题的结果不支持 rubric 筛选具有稳定优势。被选动作中业务逻辑/效果步骤覆盖有限；“局部动作可用”仍不等于“足以教会完整任务”。

### 8.2 使用历史 SFT 配方重新训练五轮

[五轮双卡实验](experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/REPORT.md)沿用上述 **2,440 个 rubric 目标及其监督区间**，从原始基座重新初始化 LoRA；不是续训此前 48 次更新的 adapter，也不是从较强的 train90 SFT LoRA 出发。

配方改为 r8 / alpha16、固定学习率 2e-4、全局每次更新 2 个步骤、按步骤平均 completion loss。五轮共 **6,100 次更新、983,040 个监督 token**；每轮每个目标恰好出现一次，两卡 adapter 哈希一致。训练全部结束后，再验证事先指定的第 1、3、5 轮检查点。

| 检查点 | Dev57 成功数 | TGC |
| --- | ---: | ---: |
| 第 1 轮 | 13/57 | 22.81% |
| 第 3 轮 | 10/57 | 17.54% |
| 第 5 轮（原定最终） | 8/57 | 14.04% |

同一连续训练中 loss 下降，但任务成功数随这三个轮次下降；当前证据不支持继续增加相同目标的训练轮数。新旧实验同时改变了学习率、rank、batch、更新次数和 loss 归一化，不能把差异全部归因于 epoch。尚无同配方五轮 uniform 对照，也没有此分支的完整 test_normal168 验证，不能宣称 rubric 五轮优于 uniform 五轮或独立测试已确认第 1 轮最优。

## 9. SWE-bench 探索与其他工程验证

此分支用于验证代码修复推理、补丁生成与应用链路，**尚无官方 Docker evaluator 的 resolved 成绩**。

| 实验 | 已完成内容与边界 |
| --- | --- |
| [SWE-bench Lite 3 题 zero-shot](experiments/2026-09-10_qwen3-8b_swebench_lite_zeroshot_smoke/REPORT.md) | 单轮检索上下文生成补丁；仅 1 个补丁可应用，但原问题仍存在，另外存在无效果/格式问题 |
| [mini-SWE-agent Lite 3 题](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_lite_3task_patchgen/REPORT.md) | 接入 mini-SWE-agent、本地工作树及 vLLM，验证多步补丁生成流程 |
| [Verified 固定 50 题，v1 / 4 并行](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_verified_50task_baseline_4parallel/report.md) | 50 题完成，10 个非空补丁、10 个可应用；最多 40 次调用、32,768 上下文 |
| [同 50 题，v2 / 2 并行](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_verified_50task_baseline_v2_2parallel/report.md) | 11 个非空补丁、10 个可应用、39 个空补丁；最多 60 次调用、40,960 上下文；正式任务未重试 |

补丁非空或 `git apply` 成功只能证明产物/应用链路，不代表修复通过；两次 50 题结果不能据此判定能力提升。该固定评测集合应保留为 holdout，不混入训练。

## 10. 下一步方案与仍待回答的问题

[最新方案](plans/2026-10-13_appworld_sft_init_local_sft_online_rl/PLAN.md)仍为**待审查、未执行**：

1. 从已有 **train90 epoch5 SFT LoRA** 出发，使用它自己的 540 条轨迹（9,886 步，186 成功 / 354 失败），先做 R1–R8 离线评分并冻结局部 SFT 选择规则。原始模型 v5/v6 标签和已选 2,440 步不能直接套用；既有 21 项轨迹级评分也不能替代步骤评分。
2. 将固定局部好动作的 SFT 与新鲜在线 rollout 的官方 0/1 结果 RL 结合，不生成教师替换动作。计划讨论 5 个在线 pass、5 个 SFT epoch、每批一个 PPO epoch；具体预算需在该 LoRA 数据筛选完成后确定，不能误读为整场只有一次 optimizer step。
3. 先完成一条训练主线，纯 RL 消融后续再安排。当前不能把设计文档写成已运行结果。

需要进一步验证的问题包括：步骤标签在独立样本上的可靠性、业务关键动作覆盖、同预算同配方的 rubric / uniform 差异、局部 SFT 与在线结果奖励的互补性，以及跨 seed / 独立测试的稳定性。先前 static GRPO 与局部 SFT 的失败或回落结果一并保留，作为后续设计的依据。

## 11. 版本控制、磁盘与复现约定

### 11.1 Git 与本地文件的边界

共享原始数据位于 `/root/autodl-tmp/data/raw_data`，应通过固定只读路径或参数引用；不要修改、移动、删除或整体复制进本工作区。

Git 保存源代码、脚本、冻结配置、研究计划、实验报告、必要的派生标签/清单与聚合结果。既有少量已跟踪 SFT 数据按原数据版本保留；默认不新增模型权重、训练 checkpoint、原始运行记录、数据库副本、token 缓存、虚拟环境、密钥和本地环境变量文件。具体见[根目录忽略规则](.gitignore)及各实验的 `.gitignore`。

本次步骤评分与局部 SFT 目录的 `inputs/`、`runs/`、`tokens.bin` 和评测原始 `trajectories/` 等生成内容保留在本地，Git 保留脚本、配置、报告、校验、派生评分表和任务结果。报告中指向服务器绝对路径、模型、原始轨迹或运行日志的链接可能仅在本机可用；仓库克隆本身不包含所有重放所需资产。

### 11.2 已完成的磁盘清理

- 2026-09-23，全参数五轮训练结束后清理过约 **91.54 GiB** 的恢复训练状态，记录见该次[训练报告](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/REPORT.md)。
- 2026-10-12，按要求删除 `2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5` 中 `artifacts/checkpoints/epoch_1_model/` 与 `artifacts/model/` 的 **10 个 safetensors 权重分片**，释放约 **30.51 GiB**，实验目录由约 31 GiB 降至约 **39 MiB**。配置、tokenizer、日志与报告保留；该实验历史报告中的模型保存和哈希记录描述当时状态，不代表权重现在仍可加载。

### 11.3 日常工作与结果复核

本工作区默认直接在 `main` 工作，用 commit 区分版本；提交前检查 `git status` 与暂存差异，推送按用户指令执行。面向使用者的 README 使用中文，顶层只维护总览，详细结果归入对应日期目录。

复核某个实验时，依次确认 **数据/模型来源 → 冻结方案与配置 → 完整性校验 → 官方任务结果 → 对照协议与结论边界**。特别检查 train/dev/test 划分、thinking 与 parser、上下文/生成/步数上限、采样参数、初始化模型、监督 token 预算和训练轮数。不要仅根据目录名、loss 曲线或一张汇总表判断实验已经完成或方法有效。
