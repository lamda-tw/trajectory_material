# taowen 工作区

本工作区主要研究 Qwen3-8B 在 AppWorld 上的轨迹学习，包括成功轨迹 SFT、单步修复训练、rubric 评分和策略优化；另保留早期高 O2 数据及 SWE-bench 实验。

以下按时间从早到晚记录已完成的主要实验，说明**我们做了什么、结果如何、详细报告在哪里**。实验记录截至 **2026-10-13**。

## 2026-09-08—09：高 O2 轨迹数据整理与 LoRA 训练

- 从 7 条高 O2 轨迹整理出 1,627 个决策级 SFT 样本，按任务家族划分 5-fold，去除 source thinking，采用 completion-only 监督。
- 使用 fold05 的 952 条训练样本和 675 条验证样本，完成双卡 LoRA smoke 及一轮正式训练（476 次更新），验证训练、保存和重载流程；尚未进行端到端 O2 效果评测。
- [数据说明](data/2026-09-08/README.md) · [一轮训练报告](experiments/2026-09-09_full_qwen3-8b_lora_2gpu_fold05_epoch1/REPORT.md)

## 2026-09-10：原始 Qwen3-8B 的 AppWorld Dev 基线

- 使用原始 Qwen3-8B、官方 ReAct one-shot 提示词，完成全部 Dev57 任务的推理和官方评测。
- 设置为 temperature 0、seed 100、每题最多 50 步、每次最多生成 3,000 token、上下文 32,000；使用默认 thinking 与 `deepseek_r1` reasoning parser。
- 成功 **5/57（TGC 8.8%）**，SGC 0，建立后续训练实验的历史基线。
- [完整 Dev 报告](experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/FULL_DEV_RUN_REPORT.md)

## 2026-09-14：SWE-bench 补丁生成与 50 题对照

- 在前期三题 smoke 基础上接入 mini-SWE-agent，固定 SWE-bench Verified 的 50 题，比较两套推理配置。
- v1 使用 4 并行、最多 40 次调用、32,768 上下文；v2 使用 2 并行、最多 60 次调用、40,960 上下文。

| 配置 | 非空补丁 | 可应用补丁 |
| --- | ---: | ---: |
| v1 | 10/50 | 10/50 |
| v2 | 11/50 | 10/50 |

只完成补丁生成与应用检查，未运行官方 Docker evaluator，因此这些数字不是问题解决率。

[v1 报告](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_verified_50task_baseline_4parallel/report.md) · [v2 报告](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_verified_50task_baseline_v2_2parallel/report.md)

## 2026-09-15：67 条 AppWorld 教师轨迹的 LoRA / 全参数 SFT

- 从前一天的 90 任务教师采集中，获得 67 条通过官方评测和干净重放的轨迹，转换成 640 个决策级训练样本；输入保留行动前历史，仅监督当前 assistant 动作。
- 分别完成 LoRA 与全参数 SFT，均训练 5 epoch / 1,600 次更新，并评测 LoRA 第 5 轮、全参数第 2/5 轮。

| 模型 | Dev57 成功数 |
| --- | ---: |
| 67 轨迹 LoRA，第 5 轮 | 5/57 |
| 67 轨迹全参数，第 2 轮 | 0/57 |
| 67 轨迹全参数，第 5 轮 | 0/57 |

训练 loss 下降，但未获得超过原始模型历史基线的 Dev 任务收益。

[数据说明](data/2026-09-15_appworld_qwen3-8b_react_sft_67/README.md) · [LoRA 训练](experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/REPORT.md) · [全参数训练](experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/REPORT.md) · [LoRA Dev](experiments/2026-09-15_174500_appworld_qwen3-8b_react_lora_aligned_full_dev/REPORT.md) · [全参数第 2 轮 Dev](experiments/2026-09-15_220731_appworld_qwen3-8b_react_full_sft_epoch2_aligned_full_dev/REPORT.md) · [全参数第 5 轮 Dev](experiments/2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev/REPORT.md)

## 2026-09-16：训练集内 15 题四模型诊断

选取训练集内 15 题，对齐比较原始模型、67 轨迹 LoRA、全参数第 2/5 轮模型，分别成功 **1、4、0、0 题**。这次检查用于判断模型在已见任务上的表现，不作为泛化成绩。

[Train-15 四模型报告](experiments/2026-09-16_154629_appworld_train15_four_models_aligned/artifacts/REPORT.md)

## 2026-09-18：原始 Qwen3-8B 的 test_normal 全量评测

- 沿用 9 月 10 日 Dev 基线的推理协议，完成 test_normal 全部 168 题；运行于 9 月 17 日启动。
- 成功 **12/168（TGC 7.1%）**，SGC 0，官方条件通过 386/1,077；23 题达到 50 步上限。
- [test_normal 报告](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/REPORT.md)

## 2026-09-20—21：Codex RFT train90 采集、LoRA 训练与评测

- 先完成 10 任务家族 pilot，再进行 train90 采集：使用 `gpt-5.6-sol / high`，91 次尝试获得 90 条真实环境成功轨迹，其中 89 题首次成功、1 题第二次成功。
- 将轨迹转换成 1,170 个决策样本，训练 Qwen3-8B LoRA 5 epoch，完成 Dev57 与 test_normal168 官方评测。

| 评测集 | 成功数 / TGC | SGC |
| --- | ---: | ---: |
| Dev57 | 23/57，40.4% | 4/19，21.1% |
| test_normal168 | 51/168，30.4% | 9/56，16.1% |

该 LoRA 成为后续 CFST 和静态 GRPO 的起点。本轮推理未启用 reasoning parser、未显式覆盖 `enable_thinking`，与早期原始模型的输出协议有区别，不能将两者差值全部归因于权重变化。

[采集报告](experiments/2026-09-20_103356_appworld_codex_rft_train90_unattended/REPORT_CN.md) · [数据说明](data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/README.md) · [LoRA 训练](experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/REPORT.md) · [Dev 报告](experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/REPORT.md) · [Test 报告](experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/REPORT.md)

## 2026-09-22：24 道上下文失败任务的扩窗复测

将 train90 LoRA 先前因上下文失败的 24 题单独重跑，窗口从 32,000 扩至 40,960。成功 **1/24**，上下文拒绝从 24 题降至 8 题；扩窗缓解了部分输入限制，但没有直接解决多数任务。这不是一次新的完整 Test 成绩。

[24 题复测报告](experiments/2026-09-22_101628_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal_context40960_24/REPORT.md)

## 2026-09-23：train90 全参数 SFT 五轮与两轮对照

- 使用与 train90 LoRA 相同的 90 条轨迹、1,170 个决策样本，完成全参数五轮训练（2,925 次更新），以及独立的两轮训练（1,170 次更新）。
- 两轮实验保留五轮 cosine 学习率调度的前缀，不是直接取五轮运行的中间检查点。

| 模型 | Dev57 成功数 | test_normal168 成功数 / TGC | Test SGC |
| --- | ---: | ---: | ---: |
| train90 LoRA 五轮（历史对照） | 23/57 | 51/168，30.4% | 9/56 |
| train90 全参数五轮 | 12/57 | 28/168，16.7% | 3/56 |
| train90 全参数两轮 | 未报告 | 28/168，16.7% | 5/56 |

全参数五轮的训练 loss 从约 0.590 降至 0.0168，但任务成绩低于 LoRA。两轮与五轮的 Test 成功任务只重合 17 题，各有 11 题不同；提前停止没有提高整题成功数。

[五轮训练](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/REPORT.md) · [五轮 Dev](experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md) · [五轮 Test](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/REPORT.md) · [两轮训练](experiments/2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5/REPORT.md) · [两轮 Test](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/REPORT.md)

## 2026-09-28—29：Dynamic CFST 单步修复训练

- 以 train90 SFT LoRA 为起点，先完成 train90 学生 rollout，成功 46/90；按任务族划分 source60 / check30。
- 在学生失败状态上收集并验证教师单动作修复，构建 State 12 条、Action 8 条、Mixed 20 条训练包。
- 先做约 8k 目标 token 的匹配训练，check30 成功数为 13/14/14，低于起点 17；随后改为每条修复只训练一轮，完成 check30 和 Dev57 对照。

| 一轮修复模型 | check30 成功数 | Dev57 成功数 |
| --- | ---: | ---: |
| 起点 LoRA | 17/30 | 23/57 |
| State | 17/30 | 25/57 |
| Action | 19/30 | 31/57 |
| Mixed | 15/30 | 21/57 |

Action 一轮的 Dev TGC 为 **54.4%**，相对起点新增成功 14 题、退化 6 题。不同修复类型和训练预算的效果不同；本阶段未继续刷新 source60 数据。

[CFST 总览](experiments/2026-09-28_dynamic_cfst/README.md) · [一轮训练](experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md) · [Action Dev](experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md) · [Mixed Dev](experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/README.md) · [State Dev](experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/README.md)

## 2026-10-08—09：原始模型与 SFT LoRA 的 train90 多次采样

分别从原始 Qwen3-8B 和 train90 SFT LoRA 出发，对每题采样 6 条轨迹。使用 temperature 1、显式关闭 thinking、50 步 / 3,000 生成 token / 32,000 上下文，为后续评分和训练准备数据。

| 起点 | 轨迹数 | 官方成功轨迹 | 总步骤 |
| --- | ---: | ---: | ---: |
| 原始 Qwen3-8B | 540 | 39/540 | 11,254 |
| train90 SFT LoRA | 540 | 186/540 | 9,886 |

[原始模型采样](experiments/2026-10-08_static_rubric_grpo/README.md) · [SFT LoRA 采样](experiments/2026-10-08_static_rubric_grpo_lora_init/README.md)

## 2026-10-09—11：静态轨迹 rubric 评分与一次 GRPO 更新

- 对 SFT LoRA 的 540 条轨迹进行 21 项静态 rubric 评分，共 11,340 个判断，按每题六条计算组内 advantage。
- 从初始 SFT LoRA 重新加载策略，冻结参考模型，双 GPU 累计全部 540 条轨迹的梯度，合并后执行**一个 PPO epoch、一次 optimizer step**；随后完整评测 Dev57 和 Test168。

| 评测集 | 更新前历史 LoRA | 更新后 | 新成功 / 退化 |
| --- | ---: | ---: | ---: |
| Dev57 | 23/57 | 16/57 | 4 / 11 |
| test_normal168 | 51/168 | 37/168 | 7 / 21 |

更新后两项成绩均下降。训练诊断发现，280 条正 advantage 轨迹中有 122 条官方失败，统一轨迹优势可能同时强化错误步骤；该解释尚未通过因果消融验证。这一结果促使后续实验转向步骤级评分与局部训练。

[完整阶段报告](experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md) · [Dev 报告](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_dev57/REPORT.md) · [Test 报告](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/REPORT.md) · [训练诊断](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/TRAINING_DIAGNOSIS.md)

## 2026-10-12：步骤级 rubric v1–v5 设计与 pilot

- 将轨迹级整体反馈细化到逐步骤的八个维度：执行、证据、状态、逻辑、动作效果、反馈恢复、终止交付、权限与协议。
- 裁判每次读取整条轨迹，对每步输出 P（满足）、F（违反）、U（证据不足）、N（不适用）和简短依据，暂不合成单一总奖励。
- 完成 v1–v5 的规则与输出格式迭代；v5 pilot 使用 12 条轨迹、201 步、两次重复调用，检查适用性及局部/全局判断边界。
- [规范与版本](plans/2026-10-12_appworld_step_rubric/README.md) · [pilot 记录](experiments/2026-10-12_appworld_step_rubric_pilot/README.md)

## 2026-10-13：中文 v5 步骤 rubric 全量评分

- 对**原始 Qwen3-8B** 的 540 条轨迹全量评分，共 11,254 步、90,032 个标签；这批轨迹官方成功 39 条、失败 501 条。
- 使用中文 v5 prompt、`gpt-5.6-sol / high`，542 次调用得到 540 条有效结果，包含 2 次格式失败重试，耗时约 1 小时 53 分钟。
- 产出逐步标签、轨迹汇总、6,381 条候选记录及复核表，供后续筛选使用；候选记录不是已确认正确的训练动作。
- [v5 全量报告](experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md)

## 2026-10-13：rubric / uniform 局部 SFT 对照

- 使用原始模型轨迹和既有 v5 标签，比较 rubric 筛选与机械可用池内的 uniform 选样，不生成教师替换动作。
- 两组均从原始 Qwen3-8B 重新初始化 LoRA，按每题监督 token 配额匹配：rubric 2,440 步、uniform 2,239 步，各 196,608 个监督 token、48 次更新。

| 同协议 Dev57 对照 | 成功数 |
| --- | ---: |
| 原始模型 | 3/57 |
| uniform 局部 SFT | 6/57 |
| rubric 局部 SFT | 4/57 |

本轮验证显式关闭 thinking，基线与早期历史 Dev 的 5/57 应分别解读。单次实验未显示 rubric 筛选稳定优于 uniform。

[局部 SFT 对照报告](experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/REPORT.md)

## 2026-10-13：rubric 局部 SFT 五轮训练及检查点评测

- 沿用同一批 2,440 个 rubric 目标，从原始基座重新初始化 LoRA；改用历史 SFT 配方：r8 / alpha16、固定学习率 2e-4、全局每次更新 2 个步骤。
- 完成双卡连续五轮训练，共 6,100 次更新；训练结束后评测事先指定的第 1、3、5 轮检查点。

| 检查点 | Dev57 成功数 |
| --- | ---: |
| 第 1 轮 | 13/57 |
| 第 3 轮 | 10/57 |
| 第 5 轮 | 8/57 |

同一连续训练中 loss 下降，但这三个检查点的任务成功数下降。相较前一实验同时改变了训练配方，且未做同配方五轮 uniform 对照，不能把结果全部归因于轮数或 rubric 筛选。

[五轮训练与评测报告](experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/REPORT.md)

## 2026-10-13：英文 v6 pilot 与全量步骤评分

- 完成 36 条轨迹的英文 pilot，其中 12 条开发集、24 条按任务族留出；版本及重复比较共获得 84 次有效调用。
- 使用英文 v6 format prompt、`gpt-6.1-sol / high`，重新评分与中文 v5 完全相同的 540 条原始模型轨迹、11,254 步、90,032 个标签。547 次调用完成全部有效结果，耗时约 2 小时 33 分钟。
- 与 v5 相比，10,131 个标签变化，若干已知边界有所改善，但仍发现 R5 适用性错误及 R6/R7 判断争议。语言、规则和裁判模型同时变化，不能单独归因于英文；尚无独立金标总体准确率。
- v6 标签没有替换前述局部 SFT 所用的 v5 数据，其训练收益尚未验证。
- [英文 pilot](experiments/2026-10-13_appworld_step_rubric_v6_en_pilot/REPORT.md) · [v6 全量报告](experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol/REPORT.md)
