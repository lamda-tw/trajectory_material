# taowen 工作区

本工作区主要研究 Qwen3-8B 在 AppWorld 上的轨迹学习，包括成功轨迹 SFT、单步修复训练、rubric 评分和策略优化；另保留早期高 O2 数据及 SWE-bench 实验。

以下按时间从早到晚记录已完成的主要实验，说明**我们做了什么、结果如何、详细报告在哪里**。实验记录截至 **2026-10-18**。

## 2026-09-08—09：高 O2 轨迹数据整理与 LoRA 训练

这一阶段先验证能否把已有高质量工具轨迹转成可训练数据，并跑通 Qwen3-8B 双卡 LoRA。

- 从 7 条高 `effectiveness.o2` 轨迹整理出 1,627 个决策级样本，同时保留完整轨迹审计表示、任务划分和转换记录。
- 按 5 个 task family 构建 grouped 5-fold，保证同一 family 不跨 train/validation；使用 fold05 时，训练集为 952 条，验证集为 675 条。一折是一场独立实验，不是一个 epoch。
- 转换时去除 source thinking，规范工具调用格式，仅对当前 assistant completion 计算 loss；工具 schema 来自观测调用推断。
- 完成双卡 LoRA smoke 和一轮正式训练（476 次更新），验证模型保存、重载与生成流程。本阶段验证的是数据和训练链路，尚未进行端到端 O2 效果评测。

[数据说明](data/2026-09-08/README.md) · [一轮训练报告](experiments/2026-09-09_full_qwen3-8b_lora_2gpu_fold05_epoch1/REPORT.md)

## 2026-09-10：原始 Qwen3-8B 的 AppWorld Dev 基线

使用未微调的 Qwen3-8B 建立 AppWorld 官方任务评测基线，为后续轨迹学习提供对照。

- 使用官方 `simplified_react_code_agent` 和固定 one-shot 提示词，按 Dev 清单运行 57 个任务、19 个 scenario；每题启动独立环境并执行官方终态测试。
- 推理设置为 temperature 0、seed 100、每题最多 50 步、单次最多生成 3,000 token、vLLM 上下文 32,000；使用默认 thinking 与 `deepseek_r1` reasoning parser。50 步是上限，并非固定交互次数。
- 全部 57 题完成运行与评分，成功 **5/57（TGC 8.8%）**，SGC **0/19**，官方条件通过 **114/291**。TGC 表示整题成功率，SGC 要求同一 scenario 的任务全部成功，部分条件通过不能替代整题成功。
- 正式运行耗时 **2 小时 21 分 48 秒**，共 688 次模型调用、4,190 次底层 API 调用，累计 4,546,793 个输入/输出 token；没有基础设施或评分链路失败。

[完整 Dev 报告](experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/FULL_DEV_RUN_REPORT.md)

## 2026-09-14：SWE-bench 补丁生成与 50 题对照

在前期三题 smoke 基础上接入 mini-SWE-agent，检查原始 Qwen3-8B 能否通过多步仓库探索和修改产生可用补丁。

- 固定 SWE-bench Verified 的同一批 50 题，分别运行两套推理配置；保存任务状态、模型交互、最终补丁及应用检查结果。
- 两版使用同一 Qwen3-8B 检查点、temperature 0.6、单次最多 2,048 输出 token。v1 使用 4 并行、最多 40 次调用、32,768 上下文；v2 使用 2 并行、最多 60 次调用、40,960 上下文。v2 正式任务未重试，没有根据补丁质量挑选运行。

| 配置 | 完成任务 | 非空补丁 | 可应用补丁 |
| --- | ---: | ---: | ---: |
| v1 | 50/50 | 10/50 | 10/50 |
| v2 | 50/50 | 11/50 | 10/50 |

两轮非空补丁对应的任务仅重合 4 题，其中只有 1 题补丁完全相同；放宽步数和窗口没有明显提高可应用补丁数。未运行官方 Docker evaluator，因此这些数字不是问题解决率，也不能据此确认 v2 的修复能力更强。该固定集合保留为评测 holdout。

[v1 报告](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_verified_50task_baseline_4parallel/report.md) · [v2 报告](experiments/2026-09-14_qwen3-8b_minisweagent_swebench_verified_50task_baseline_v2_2parallel/report.md)

## 2026-09-15：67 条 AppWorld 教师轨迹的 LoRA / 全参数 SFT

这一阶段研究如何把官方成功、可重放的教师轨迹转成监督数据，并在相同数据和训练预算下比较 LoRA 与全参数更新。

**数据与训练设置**

- 从前一天的 90 任务采集中，获得 67 条通过官方评测和干净环境重放的轨迹，转换成 **640 个决策样本**；训练仅使用 train 任务，Dev 不参与训练。
- 输入为任务上下文和行动前历史，目标为当前 assistant 的推理与 Python 动作；使用 Qwen3 chat template、`enable_thinking=False` 和 completion-only loss，32,768 长度内全部不截断。
- 两组均从原始 Qwen3-8B 出发，使用相同样本顺序和随机种子、全局 batch 2、AdamW、学习率 2e-4、BF16、SDPA 和梯度检查点，完成 **5 epoch / 1,600 次更新**。
- LoRA 使用双卡 DDP，训练 21,823,488 个参数（0.2657%）；全参数使用 FSDP FULL_SHARD，训练全部 8,190,735,360 个参数。两者都通过保存重载及生成检查。

**训练与 Dev 结果**

LoRA 的第 1/5 轮平均 loss 为 **0.650503 → 0.106259**，全参数为 **1.166161 → 0.166918**。随后用同一套 Dev57 官方 evaluator 检查各模型的任务表现：

| 模型 | Dev57 成功数 / TGC | SGC | 官方条件通过 |
| --- | ---: | ---: | ---: |
| 原始模型（历史） | 5/57，8.8% | 0/19 | 114/291 |
| 67 轨迹 LoRA，第 5 轮 | 5/57，8.8% | 1/19 | 105/291 |
| 67 轨迹全参数，第 2 轮 | 0/57 | 0/19 | 64/291 |
| 67 轨迹全参数，第 5 轮 | 0/57 | 0/19 | 86/291 |

训练 loss 下降，但未获得超过原始模型历史基线的 Dev 整题收益。两次全参数评测均未出现 `content=null`，没有证据把零成功归因于接口吞掉了输出；后续进一步检查训练集内任务。

[数据说明](data/2026-09-15_appworld_qwen3-8b_react_sft_67/README.md) · [LoRA 训练](experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/REPORT.md) · [全参数训练](experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/REPORT.md) · [LoRA Dev](experiments/2026-09-15_174500_appworld_qwen3-8b_react_lora_aligned_full_dev/REPORT.md) · [全参数第 2 轮 Dev](experiments/2026-09-15_220731_appworld_qwen3-8b_react_full_sft_epoch2_aligned_full_dev/REPORT.md) · [全参数第 5 轮 Dev](experiments/2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev/REPORT.md)

## 2026-09-16：训练集内 15 题四模型诊断

为区分“只在未见任务上表现不好”与“连已见任务也未学会”，从 `SFT67 ∩ Train90` 中固定选择 5 个完整 scenario、每个 3 题，比较四个模型。

- 各模型使用官方 ReAct 提示词、temperature 0、seed 100、每题最多 50 步，并分别沿用自己的正式 Dev 输出接口设置。

| 模型 | 成功任务 | SGC | 官方条件通过 |
| --- | ---: | ---: | ---: |
| 原始 Qwen3-8B | 1/15 | 0/5 | 32/84 |
| 67 轨迹 LoRA，第 5 轮 | 4/15 | 1/5 | 43/84 |
| 67 轨迹全参数，第 2 轮 | 0/15 | 0/5 | 15/84 |
| 67 轨迹全参数，第 5 轮 | 0/15 | 0/5 | 25/84 |

LoRA 在这些已见任务上有一定收益，而全参数模型仍未完成整题，说明问题不只出现在 Dev 泛化。本次是训练集内诊断，不能作为未见任务成绩。

[Train-15 四模型报告](experiments/2026-09-16_154629_appworld_train15_four_models_aligned/artifacts/REPORT.md)

## 2026-09-18：原始 Qwen3-8B 的 test_normal 全量评测

- 沿用 9 月 10 日 Dev 基线的 ReAct、thinking/parser 和推理预算，完成 test_normal 全部 **168 题、56 个 scenario**；运行于 9 月 17 日启动。
- 成功 **12/168（TGC 7.1%）**，SGC **0/56**，官方条件通过 **386/1,077（35.8%）**；难度 1/2/3 的 TGC 分别为 19.3%、2.1%、0%。
- 对失败任务做逐题分类，主要问题包括答案不匹配、交易/购物状态、Venmo 和 Spotify 状态不满足；23 题达到 50 步上限。
- 另外检查输出接口和长度截断：45 题出现过纯 reasoning 耗尽单次生成预算，共 80 次。这类调用尚未生成可执行动作，需要与业务决策错误分别记录，不能把全部失败归因于一种接口问题。
- 168 题的任务目录、完成状态、官方逐题报告和聚合结果均完成一致性校验，形成后续训练模型的历史 Test 对照。

[test_normal 报告](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/REPORT.md)

## 2026-09-20—21：Codex RFT train90 采集、LoRA 训练与评测

在 67 轨迹实验之后，扩大真实环境教师成功轨迹的覆盖，检查更完整的 train90 数据能否改善学生策略。

**教师采集与数据**

- 先完成 10 任务家族 pilot（10/10 首次成功），再使用 `gpt-5.6-sol / high`、4 个 worker、每次最多 40 次环境交互完成 train90 采集。
- 共 **91 次尝试得到 90 条成功轨迹**：89 题首次成功、1 题第二次成功；其中 9 条成功轨迹包含执行错误后的恢复，不能与此前全部干净重放的 67 轨迹数据混为一谈。
- 转换成 **1,170 个决策样本**，只监督当前 assistant 动作，保留教师实际看到的历史；observation 沿用采样时的 24,000 字符前后截断，转换时设置 `enable_thinking=False`。

**LoRA 训练与正式评测**

- 从原始 Qwen3-8B 开始，使用 LoRA r8 / alpha16、固定学习率 2e-4、全局 batch 2、双卡 DDP，连续训练 **5 epoch / 2,925 次更新**；训练长度上限 40,960，实际无额外 token 截断。
- 用同一最终 adapter 完成 Dev57 和 test_normal168；推理采用 temperature 0、seed 100、50 步 / 3,000 生成 token / 32,000 上下文。

| 评测集 | 成功数 / TGC | SGC | 官方条件通过 |
| --- | ---: | ---: | ---: |
| Dev57 | 23/57，40.4% | 4/19，21.1% | 206/291 |
| test_normal168 | 51/168，30.4% | 9/56，16.1% | 598/1,077 |

该 LoRA 成为后续 CFST 和静态 GRPO 的起点。本轮未启用 reasoning parser、未显式覆盖 `enable_thinking`，与早期原始模型输出协议不同，因此历史分差不是单独改变权重的因果消融。

Test 失败任务中有 24 题遇到上下文拒绝：13 题是输入加预留输出超过窗口，11 题是输入本身超限，由此开展下一天的受限扩窗诊断。

[采集报告](experiments/2026-09-20_103356_appworld_codex_rft_train90_unattended/REPORT_CN.md) · [数据说明](data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/README.md) · [LoRA 训练](experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/REPORT.md) · [Dev 报告](experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/REPORT.md) · [Test 报告](experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/REPORT.md)

## 2026-09-22：24 道上下文失败任务的扩窗复测

保持 train90 LoRA adapter、ReAct 和采样设置不变，只将上下文窗口从 **32,000 扩至 40,960**，对先前出现上下文错误的 24 题进行复测。

- 24/24 题完成，成功 **1/24**；上下文拒绝由 24 题降至 8 题。
- 官方条件通过数从 **55/213 增至 83/213**，另有 15 题虽然不再出现窗口错误，仍未完成任务。
- 扩窗缓解了一部分输入限制，但多数失败仍需从模型决策和任务执行解释。该集合按旧报错筛选，不是新的完整 Test 成绩；新旧轨迹存在分叉，也不能将每题变化都单独归因于窗口。

[24 题复测报告](experiments/2026-09-22_101628_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal_context40960_24/REPORT.md)

## 2026-09-23：train90 全参数 SFT 五轮与两轮对照

使用与 train90 LoRA 相同的 90 条轨迹、1,170 个决策样本，检验全参数更新的效果，并进一步检查训练更早停止是否能改善结果。

**训练设置**

- 五轮实验从原始 Qwen3-8B 出发，训练全部约 81.9 亿参数，使用 FSDP、FP32 主参数和 AdamW 状态、BF16 计算及导出，完成 **5 epoch / 2,925 次更新**；最长序列为 37,015 token，没有额外截断。
- 五轮平均 loss 为 **0.589548 → 0.274838 → 0.129335 → 0.053033 → 0.016795**。
- 两轮实验独立重新训练 **2 epoch / 1,170 次更新**，保留五轮的 2,925 步 cosine 计划和 88 步 warmup，只运行其前缀；两轮平均 loss 为 **0.589565 → 0.272481**。它不是直接取同一次五轮运行的中间检查点。

**完整评测与两轮/五轮对照**

| 模型 | Dev57 成功数 | test_normal168 成功数 / TGC | Test SGC | Test 官方条件通过 |
| --- | ---: | ---: | ---: | ---: |
| train90 LoRA 五轮（历史） | 23/57 | 51/168，30.4% | 9/56 | 598/1,077 |
| train90 全参数五轮 | 12/57 | 28/168，16.7% | 3/56 | 498/1,077 |
| train90 全参数两轮 | 未报告 | 28/168，16.7% | 5/56 | 444/1,077 |

- 全参数五轮的 Dev 官方条件通过 163/291；Test 相对历史 LoRA 新成功 10 题、退化 33 题，拟合训练数据更充分没有带来更好的任务表现。
- 两轮与五轮共同成功 17 题，两轮新增 11 题、丢失 11 题；虽然完整 scenario 多成功 2 个，但整题成功数未提高，条件通过数反而下降。
- 两轮模型有 44 题上下文拒绝、35 题到达 50 步；五轮对应为 29 题、19 题。重复行为和恢复问题在提前停止后仍存在，本次诊断不足以确认“五轮退化就是过拟合”。

[五轮训练](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/REPORT.md) · [五轮 Dev](experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md) · [五轮 Test](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/REPORT.md) · [两轮训练](experiments/2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5/REPORT.md) · [两轮 Test](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/REPORT.md)

## 2026-09-28—29：Dynamic CFST 单步修复训练

这一阶段把完整教师轨迹学习改为针对学生失败状态的局部修复：教师只替换一个动作，再交给学生继续执行，确认这一步帮助能否使任务成功。

- 以 train90 SFT LoRA 为起点完成 train90 rollout，成功 **46/90**；按任务族固定划分 source60 / check30，后者只用于检查，Dev 不提供教师答案。
- 在 source60 上审查失败轨迹，干净重放原动作前缀，再插入教师单动作并让学生续跑，以官方最终成功验证修复。逐步处理普通失败和上下文耗尽前的失败，最终得到 **20 条合格修复**。
- 按状态构建与动作落地分成 **State 12 条、Action 8 条、Mixed 20 条**。训练输入为修复点之前的真实历史，目标仅为验证通过的那个教师动作，不把完整教师续写混入训练。
- 先做约 8k 目标 token 的匹配训练，三组分别更新 27/22/25 次，check30 成功数为 13/14/14，均低于起点 17。
- 随后重新训练三个独立 LoRA 分支，每条修复只学一轮；State / Action / Mixed 分别更新 6/4/10 次，完成 check30 与 Dev57 对照。

| 一轮修复模型 | check30 成功数 | Dev57 成功数 / TGC | Dev 官方条件通过 |
| --- | ---: | ---: | ---: |
| 起点 LoRA | 17/30 | 23/57，40.4% | 206/291 |
| State | 17/30 | 25/57，43.9% | 179/291 |
| Action | 19/30 | 31/57，54.4% | 215/291 |
| Mixed | 15/30 | 21/57，36.8% | 184/291 |

Action 一轮的 Dev SGC 为 **31.6%**，相对起点新增成功 14 题、退化 6 题；State 新增 9、退化 7，Mixed 新增 10、退化 12。该结果支持继续研究有针对性的动作修复，也说明修复类型和训练强度会影响收益，不能简单合并更多数据或反复训练。本阶段未继续刷新 source60 数据。

[CFST 总览](experiments/2026-09-28_dynamic_cfst/README.md) · [一轮训练](experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md) · [Action Dev](experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md) · [Mixed Dev](experiments/2026-09-28_dynamic_cfst/step07d_dev57_mixed_one_epoch/README.md) · [State Dev](experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/README.md)

## 2026-10-08—09：原始模型与 SFT LoRA 的 train90 多次采样

为研究组内相对评价和 rubric 训练信号，分别从原始 Qwen3-8B 与 train90 SFT LoRA 出发，对同一批 90 题各采样 6 条轨迹。

- 两组均使用 temperature 1、top_p 1、top_k -1、repetition penalty 1，显式关闭 thinking；每题最多 50 步、每次 3,000 生成 token、32,000 上下文，不截断历史。
- 每组保留完整 **540 条**及官方终态结果，不只筛选成功轨迹。LoRA 分支修复采集中的 Ellipsis 序列化问题后，保留已有 342 条并恢复完成其余 198 条。

| 起点 | 官方成功轨迹 | 全失败 / 混合 / 全成功任务组 | 总步骤 | 生成 token |
| --- | ---: | ---: | ---: | ---: |
| 原始 Qwen3-8B | 39/540 | 70 / 20 / 0 | 11,254 | 1,366,894 |
| train90 SFT LoRA | 186/540 | 23 / 63 / 4 | 9,886 | 1,785,724 |

“混合组”表示同一道题的六条轨迹中既有成功也有失败。LoRA 组有更多可比较的成功/失败样本，用于后续轨迹级静态评分与 GRPO；原始模型组后来用于步骤 rubric 和局部 SFT。两套数据都叫 540 条，但来源、步骤数和成功分布不同。

[原始模型采样](experiments/2026-10-08_static_rubric_grpo/README.md) · [SFT LoRA 采样](experiments/2026-10-08_static_rubric_grpo_lora_init/README.md)

## 2026-10-09—11：静态轨迹 rubric 评分与一次 GRPO 更新

对 SFT LoRA 的多次采样轨迹使用固定规则评分，检验轨迹级 rubric 能否提供有效的策略更新信号。

- 完成 **540 条 × 21 项 = 11,340 个判断**，按同题六条计算 reward 和组内 advantage；90 个任务组均有非零优势。
- 正式训练从生成这批数据的初始 SFT LoRA 重新加载，不继承前期工程验证的更新；独立参考策略保持冻结。
- 双 GPU 各处理 45 题、270 条，累计梯度后求和，统一执行**一个 PPO epoch、一次 optimizer step**。全部 540 条只用于这次更新，没有第二次重采样，也未执行此前讨论的固定数据五轮方案。
- 检查策略确实更新、参考模型未变，并通过模型保存重载后的真实 token logprob 对齐；没有发现重复更新、分片覆盖或梯度合并错误。
- 随后评测同一最终 checkpoint：Dev57 顺序运行，Test 两卡各 84 题后官方聚合。使用历史 ReAct、temperature 0、seed 100、50 步 / 3,000 生成 token / 32,000 上下文，不启用 reasoning parser，也不覆盖 `enable_thinking`；与采样时显式关闭 thinking 的设置有区别。

| 评测集 | 更新前历史 LoRA | 更新后 | 新成功 / 退化 | 更新后 SGC |
| --- | ---: | ---: | ---: | ---: |
| Dev57 | 23/57，40.4% | 16/57，28.1% | 4 / 11 | 2/19，10.5% |
| test_normal168 | 51/168，30.4% | 37/168，22.0% | 7 / 21 | 9/56，16.1% |

**后续诊断**：Test 条件通过数从 598/1,077 变为 594/1,077，但整题成功数减少 14；21 个退化任务中 16 个只差一个条件，且没有退化题因上下文中断。部分条件接近不代表整体任务仍能完成。

280 条正 advantage 轨迹中有 122 条官方失败，另有 27 条官方成功轨迹得到负 advantage；统一轨迹优势可能同时强化错误步骤。首次更新点 policy 与 reference 相同，KL 值和一阶梯度均为零。这些发现提供了排查方向，尚未通过因果消融确定各因素贡献；本次也不是完整 DRACO 训练效果的复现。后续转向更细的步骤评价与局部训练。

[完整阶段报告](experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md) · [Dev 报告](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_dev57/REPORT.md) · [Test 报告](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/REPORT.md) · [训练诊断](experiments/2026-10-11_appworld_qwen3-8b_react_lora_static_grpo_train90_single_update_test_normal168/TRAINING_DIAGNOSIS.md)

## 2026-10-12：步骤级 rubric v1–v5 设计与 pilot

针对轨迹级分数难以区分局部正确与错误动作的问题，设计按步骤输出的 rubric，先检查评分能否对齐真实执行证据。

| 维度 | 评价内容 | 维度 | 评价内容 |
| --- | --- | --- | --- |
| R1 | 执行有效性 | R5 | 动作与实际效果 |
| R2 | 证据与覆盖 | R6 | 反馈与恢复 |
| R3 | 状态与数据保真 | R7 | 终止与交付 |
| R4 | 决策逻辑与计算 | R8 | 权限与交互协议 |

- 每次向裁判提交一条完整轨迹，逐步输出八项 **P（满足）、F（明确违反）、U（适用但证据不足）、N（不适用）**，并附一句简短依据；不预先合成一个总分或固定权重。
- 完成 v1–v5 的规则、输入适配、schema 和校验迭代，重点处理局部动作与全局任务、失败调用与实际状态改变、恢复行为和终止判断的边界。
- v5 pilot 使用 **12 条轨迹、201 步、两次重复调用**，同时检查开发样例回归和重复评分的一致性，并保留版本间差异及逐例复核。
- 这些检查用于开发规则，不是独立准确率评估。N 不能算失败或额外通过，局部动作可用也不能替代官方任务成功。

[规范与版本](plans/2026-10-12_appworld_step_rubric/README.md) · [pilot 记录](experiments/2026-10-12_appworld_step_rubric_pilot/README.md)

## 2026-10-13：中文 v5 步骤 rubric 全量评分

将冻结的 v5 扩展到原始 Qwen3-8B 的全部 train90 采样，为后续局部训练提供可追溯的步骤标签。

- 数据为 **540 条、11,254 步、90,032 个标签**，覆盖 90 题、30 个任务家族；官方成功 39 条、失败 501 条。使用的是原始模型组，不是 SFT LoRA 的 9,886 步数据。
- 使用中文 v5 prompt、`gpt-5.6-sol / high`；每条完整轨迹重新调用一次，不复用 pilot，不向裁判提供官方成败或隐藏答案，也不允许工具查询。
- 并发从 2 提升至 4、再到 8；**542 次调用得到 540 条有效结果**，包含 2 次相同请求的格式失败重试。评分墙钟 **1 小时 52 分 51 秒**，不含后续复核与报告时间。
- 完成源文件/输入哈希、冻结请求、步骤顺序、JSON 结构和原始响应一致性检查；另用执行反馈、代码块和保守 AST 规则做机械核对。
- 评分后复核预先固定的 **12 条轨迹、176 步、1,408 个分项**，并与 pilot 的相同样例比较重复性。复核者能看到既有评分，样例也不是全量随机抽取，因此不将复核比例当作总体准确率。

得到逐步标签、轨迹汇总、**6,381 条候选记录**和复核表。标签中既有“成功轨迹包含错误步骤”，也有“失败轨迹包含有效动作”；这支持从两类轨迹中做局部选择。候选记录并不都是已确认正确的训练动作，也没有直接转成精确 reward，下一步通过受控训练检查其实际价值。

[v5 全量报告](experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md)

## 2026-10-13：rubric / uniform 局部 SFT 对照

这次实验只回答一个问题：在相同监督预算下，用步骤 rubric 筛选学生已有动作，是否比从机械可用动作中均匀选择更有效？不追加裁判调用，也不生成教师替换动作。

**筛选与数据对齐**

- 两组先经过相同机械条件：执行未报错、单个闭合 Python 代码块、生成未截断、上下文不超限，并排除实际 `complete_task` 动作，得到 **5,234 步共同候选池**。
- rubric 组进一步要求 R1=P、R2–R6 各为 P/N、R7=N；R8 保留诊断，不作为整项硬门槛，得到 **2,580 步语义候选**。官方 train 成败不参与选择或配额。
- 按每道题的监督 token 配额匹配：rubric 选中 **2,440 步**、uniform 选中 **2,239 步**，各 **196,608 个监督 token**。为精确对齐配额，必要时只监督响应末端样本的原始 token 前缀，不改写动作。
- 输入保留真实行动前历史，当前和未来执行反馈不进入 prompt；两组初始 LoRA 张量一致，选择冻结后不根据 Dev 成绩调整规则。

**训练与 Dev57**

从原始 Qwen3-8B 新建 LoRA r16 / alpha32，使用 AdamW、最高学习率 5e-5、warmup + cosine、token 平均 completion loss；每次更新 4,096 个监督 token，共 **48 次更新**。

| 同协议 Dev57 对照 | 成功数 / TGC | 相对本轮原始模型新增 / 退化 |
| --- | ---: | ---: |
| 原始模型 | 3/57，5.26% | — |
| uniform 局部 SFT | 6/57，10.53% | 3 / 0 |
| rubric 局部 SFT | 4/57，7.02% | 2 / 1 |

本轮验证显式关闭 thinking，使用 temperature 0、seed 100、50 步 / 3,000 生成 token / 32,000 上下文；原始模型按同一协议重新评测，不能替换早期历史 Dev 的 5/57。

rubric 相对 uniform 新成功 1 题、退化 3 题，净少 2 题。进一步检查发现，rubric 选中步骤中 R4=P 或 R5=P 的并集仅 **87/2,440（约 3.6%）**，其中 R5=P 仅 19 步，复杂业务动作覆盖有限。单个 seed 的结果未显示稳定优势，也说明“通过质量筛选”不等于“具有足够学习价值”。

[局部 SFT 对照报告](experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/REPORT.md)

## 2026-10-13：rubric 局部 SFT 五轮训练及检查点评测

为检查上一轮结论是否受训练配方和更新量限制，沿用完全相同的 **2,440 个 rubric 目标与监督区间**，参考历史 train90 SFT 配方重新训练。

- 从原始基座新建 LoRA，没有续训此前的 48 次更新 adapter，也没有加载较强的 train90 SFT LoRA；不重新打分，不引入教师新动作。
- LoRA 改为 **r8 / alpha16**，固定学习率 **2e-4**，全局每次更新 **2 个步骤**，先对每个步骤的 completion token 求平均，再对步骤取平均。此前配方是按更新内全部 token 平均，两者训练目标的归一化不同。
- 双卡连续训练五轮并保留 AdamW 状态，每轮每个目标恰好出现一次：每轮 1,220 次更新、196,608 个监督 token，合计 **6,100 次更新、983,040 个监督 token**。两卡参数哈希与数据覆盖检查均通过。
- 五轮全部结束后，再评测事先指定的第 1、3、5 轮检查点；不在训练中根据 Dev 成绩提前停止或调整目标。评测沿用上一轮关闭 thinking 的相同协议。

| 检查点 | 本轮样本平均训练 loss | Dev57 成功数 / TGC |
| --- | ---: | ---: |
| 第 1 轮 | 0.166821 | 13/57，22.81% |
| 第 3 轮 | 0.133406 | 10/57，17.54% |
| 第 5 轮 | 0.096707 | 8/57，14.04% |

第 5 轮相对第 1 轮新增成功 2 题、退化 7 题，净少 5 题。第五轮仍有 24 题调用完成 API 后未通过官方测试，另有 24 题耗尽步骤或上下文，表明局部执行改善仍不足以保证完整任务推进。

同一连续训练中 loss 下降而上述检查点成功数下降，不支持继续增加同一批目标的轮数就会更好。与旧实验比较时，学习率、rank、batch 和 loss 归一化同时改变；又缺少同配方五轮 uniform 对照，不能把差异全部归因于轮数或 rubric。该分支尚无完整 test_normal168 验证。

[五轮训练与评测报告](experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/REPORT.md)

## 2026-10-13：英文 v6 pilot 与全量步骤评分

根据 v5 复核中的问题，收紧当前子目标、实际写入、错误恢复和终止/协议边界，形成英文 v6 format 配置，再检查全量评分质量。

- 先完成 **36 条轨迹**的英文 pilot，其中 12 条开发集、24 条按任务族留出；版本及重复比较共获得 **84 次有效调用**。
- 使用英文 v6 format prompt、`gpt-6.1-sol / high`，重新评分与中文 v5 **逐字节相同的 540 份预处理输入**，共 11,254 步、90,032 个标签；不向裁判提供旧评分或官方成功标记，也不复用 pilot 结果。
- **547 次调用**完成 540 条有效结果，首次有效 533/540；其余包含 5 次格式失败和 2 次服务容量失败。只为技术/格式问题重试，接受首个通过 schema 的结果，不根据标签优劣挑选。
- 评分墙钟 **2 小时 32 分 40.6 秒**，包含等待、重试和校验；并发上限从 8 因容量问题暂降为 4，稳定后恢复为 8。

与中文 v5 对齐后，**10,131/90,032 个标签发生变化**。额外非空 Python 代码块的机械检查匹配由 961/1,209 提高到 1,209/1,209；同时仍发现 8 处只读/鉴权/提交步骤的 R5 适用性误判。

对预先固定的 12 条、176 步重新逐案复核，发现 1 处明确 R6 恢复漏评和 9 处边界争议；这组样例并非独立金标，规则含义也发生变化，不能直接据此推算总体准确率提升。R5 仅在 **278/11,254 步（2.47%）**上适用，大量 N/N 会抬高全单元一致率。

本次同时改变语言、规则版本和裁判模型，不能单独归因于英文。v6 标签未替换前述局部 SFT 使用的 v5 数据，评分质量改善能否转化为训练收益仍待验证。

[英文 pilot](experiments/2026-10-13_appworld_step_rubric_v6_en_pilot/REPORT.md) · [v6 全量报告](experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol/REPORT.md)

## 2026-10-14：SFT LoRA 初始模型的英文 v6 步骤评分

将步骤评分从原始 Qwen3-8B 扩展到较强的 train90 SFT LoRA，给后续从 SFT 模型继续训练准备独立标签。

- 唯一来源是 10 月 8—9 日采集的 SFT LoRA 轨迹：**90 题 × 6 条 = 540 条、9,886 步、79,088 个 R1–R8 标签**，官方成功 186 条、失败 354 条。没有复用原始模型那批 11,254 步的标签。
- 使用冻结英文 v6 format prompt、`gpt-6.1-sol / high`，并发上限 8；先做 8 条试评，再扩展全量，同配置试评计入最终 540 条。每条只接受首个格式有效结果，不根据标签好坏重评。
- 共 **543 次尝试、3 次无效重试**，全部 540 条完成。评分阶段耗时 **151.21 分钟**，包含试评、复核等待、排队、重试及落盘；源文件与输入哈希、步骤覆盖和格式验收通过。
- 完成最初 8 条和预选 12 条样本的关键证据复核，其中 53 项检查在对应评分到达前冻结。记录到 0 项明确标签问题、1 项边界争议；这是定向复核，不能解释为全量标签准确率。
- 保存逐步标签、逐轨迹评分、官方结果关联分析和来源清单；官方成功标记仅用于研究者事后分析，不提供给裁判。此阶段只评分，没有训练或更改源模型。

[评分报告](experiments/2026-10-14_appworld_sft_init_step_rubric_v6_gpt61_sol/REPORT.md) · [数据字段说明](experiments/2026-10-14_appworld_sft_init_step_rubric_v6_gpt61_sol/analysis/DATA_DICTIONARY.md) · [来源与结构验收](experiments/2026-10-14_appworld_sft_init_step_rubric_v6_gpt61_sol/analysis/validation.json)

## 2026-10-14：匹配步骤数的一轮 Random / Rubric SFT 对照

补充 10 月 13 日新配方下的随机对照：比较相同初始化、每题步骤数、更新次数及任务配对时，rubric 选择与随机选择的效果。这与此前匹配监督 token、只更新 48 次的对照是两项实验。

**数据与训练**

- 从同一批原始 Qwen3-8B 轨迹的 **5,234 步公共候选池**内，按每题配额无放回均匀随机抽取 **2,440 步**；不使用 rubric 标签或官方成败选样。随机组覆盖 514 条轨迹，与 rubric 组重合 1,283 步，不刻意排除高分步骤。
- 复用 rubric 第一轮的样本任务位置与打乱顺序，**1,220 次更新的任务配对逐一匹配**；两组从相同 LoRA 初始张量出发。原有 rubric 模型不重训，作为历史同协议参考。
- 使用 r8 / alpha16、AdamW 固定学习率 2e-4、双卡 DDP、全局每次两个步骤；先在每步目标 token 内平均，再对步骤平均，每个目标只训练一次。

| 预算 | Rubric 第 1 轮参考 | Random 本次 |
| --- | ---: | ---: |
| 步骤 / 更新次数 | 2,440 / 1,220 | 2,440 / 1,220 |
| 监督 token | 196,608 | 220,081 |
| 训练输入 token | 13,734,737 | 18,501,155 |
| 部分监督响应 | 88 | 0 |

因此本次匹配的是步骤和更新预算，监督 token、上下文计算量和部分响应 mask 没有完全匹配。Random 保留完整原始响应，不为凑 token 预算截断动作。

**Dev57 结果**

沿用关闭 thinking、temperature 0、seed 100、50 步 / 3,000 生成 token / 32,000 上下文的评测协议：

| 模型 | 成功数 / TGC |
| --- | ---: |
| 原始模型（已有同协议） | 3/57，5.26% |
| Rubric 新配方第 1 轮（已有） | 13/57，22.81% |
| Random 第 1 轮（本次） | 5/57，8.77% |

Random 相对 Rubric 新成功 1 题、退化 9 题，净少 8 题；上下文上限终止为 27 题，对照为 8 题。正式训练耗时 **2 小时 38 分 47 秒**，Dev57 耗时 **30 分 47 秒**。本次观察支持现有 rubric 数据管线在该步骤预算下优于随机抽样，但只有一次抽样和训练，且 token 与 mask 未完全对齐，不能将差异单独归因于 rubric 标签。

[完整报告](experiments/2026-10-14_appworld_uniform_local_sft_epoch1_ddp/REPORT.md) · [逐题对照](experiments/2026-10-14_appworld_uniform_local_sft_epoch1_ddp/analysis/task_comparison.csv) · [训练配置](experiments/2026-10-14_appworld_uniform_local_sft_epoch1_ddp/config/training.json)

## 2026-10-14—16：从 SFT LoRA 出发的单池 RL + 局部 SFT 联合训练

使用 SFT LoRA 自己生成的轨迹和 v6 步骤标签，将官方任务结果的 RL 信号与固定局部动作的 SFT 联合起来，检查能否在已有成功轨迹训练基础上继续改善策略。

**数据选择与联合目标**

- 在 SFT LoRA 的 **9,886 步**上计算净分 `P−F`：P=1、F=−1、U/N=0。唯一入选条件为 **净分 ≥ 4**，选中 **2,623 步**；不额外做质量过滤或内容去重，也不按官方成败筛选 SFT 数据。
- 保留完整行动前历史和原始完整响应，仅监督目标动作；单遍共 **205,238 个目标 token**，最长完整样本 **31,814 token**。没有沿用原始模型分支的 2,440 步，也没有生成教师替代动作。
- RL 使用 SFT LoRA 原有的完整 **540 条轨迹**，每题六条成组，以官方整题成功/失败的 1/0 计算组内标准化优势；同奖励组优势为零但仍保留，不用 rubric 净分筛选 RL 轨迹。
- 继续训练已有 r8 / alpha16 LoRA，基座冻结，参考策略固定为初始 SFT 模型。RL 对每条轨迹生成 token 求平均再对轨迹平均；SFT 在每个原始步骤目标内平均再对步骤平均。两部分梯度合并后做一次更新。

**实际完成的训练范围**

- 仅使用物理 GPU1，以一个固定轨迹池单遍分成 **15 批**；每批 6 题、36 条 RL 轨迹，配合 174 或 175 个 SFT 步骤，完成 **15 次联合 optimizer 更新**。整池累计使用 540 条 RL 轨迹、1,785,724 个生成 token，以及全部 2,623 个 SFT 目标一次。
- 沿用本轮配置：PPO clip 0.2、SFT 系数 0.1、采样 token 上的 KL 正则系数 0.01；AdamW 峰值学习率 5e-6，4 次 warmup，再 cosine 衰减。停止时保留原 **75 次更新调度的前 15 次**，没有事后重排学习率。
- 完成联合 loss/梯度、数据 mask、参考概率、分片预算、恢复和权重保存检查。最终采用 `full_pool_15` 整池试跑中真实更新得到的模型，并于 **10 月 16 日 03:55** 完成最终导出与验收；没有从初始模型重复再训一轮。
- 原计划的后续四轮新轨迹采集与训练未执行，因此本次结果属于**复用固定池的一轮联合训练**，不能称为已经完成五轮在线 RL。训练过程中调查过前缀共享优化，但没有切换到优化实现或据此重跑。

模型保存后的任务能力由下一节的完整 Dev57 评测判断；预算和权重验收通过本身不代表性能提升。

[实验总览](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/README.md) · [选样与数据构建记录](plans/2026-10-13_appworld_sft_init_local_sft_online_rl/STEP_03_RESULTS.md) · [本轮实际使用配置](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/config/round1_trial_15.json) · [单池完成验收](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/ROUND_01_COMPLETE.json)

## 2026-10-16：联合训练的同历史协议 Dev57 五点对照

在联合训练结束后，对初始模型以及第 1、5、10、15 次更新后的检查点分别完成 Dev57，用同一入口观察训练过程中的能力变化。

- 逐字节复用历史 train90 LoRA 的 AppWorld launcher 与配置，保持原始 ReAct 提示、Chat Completions、代码提取和上下文处理；temperature 0、seed 100、50 步 / 3,000 生成 token / 32,000 上下文，无 reasoning parser，也不额外设置 `enable_thinking=False`。
- 五个点使用同一基座、tokenizer、数据和软件环境，仅替换 LoRA 权重；在 GPU1 串行完成 **5 × 57 = 285 次任务运行**，于 **12:29** 完成五点评测与汇总。这里的 step 指优化器更新次数，不是环境行动步数。
- 初始模型 step 0 本次复测为 **25/57**，历史为 23/57；协议检查后保留实测差异，后续收益/退化均相对本次 step 0 计算，不把基线波动计为训练收益。

| 优化器更新次数 | Dev57 成功数 / TGC | SGC | 官方条件通过 | 相对本次 step 0 新增 / 退化 |
| --- | ---: | ---: | ---: | ---: |
| 0 | 25/57，43.86% | 4/19，21.05% | 204/291 | — |
| 1 | 18/57，31.58% | 3/19，15.79% | 189/291 | 4 / 11 |
| 5 | 18/57，31.58% | 2/19，10.53% | 198/291 | 3 / 10 |
| 10 | 20/57，35.09% | 3/19，15.79% | 201/291 | 4 / 9 |
| 15 | 23/57，40.35% | 3/19，15.79% | 188/291 | 8 / 10 |

最终 step 15 相对 step 0 **净少成功 2 题、少 1 个完整 scenario、少通过 16 个官方条件**。早期更新先下降，后续部分恢复，但本次最高 TGC/SGC 均出现在初始模型，未观察到联合训练的净收益。每个检查点只评测一次，尚不能隔离 RL、SFT 或 KL 的独立贡献，也不据此声称统计显著。

此前最终模型还用另一评测入口得到 **20/57**；该入口与历史协议存在提示空白、thinking 和上下文预算差异，保留为单独记录，**不混入上述曲线**。最新五点结果以本节同协议对照为准。

[五点趋势与逐题对照](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/historical_protocol_trend/COMPARISON.md) · [完整评测协议](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/HISTORICAL_DEV57_RUN.md) · [最终验收](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/historical_protocol_trend/FINAL_AUDIT.json) · [另一入口的结果与协议比较](experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/evaluation/round_01_final/BASELINE_COMPARISON.md)


## 2026-10-16—18：纯 Rubric 选样的五组单轮 SFT 消融

本轮研究 rubric 的选择效果、选择机制与学习机制。使用原始 Qwen3-8B 的 540 条轨迹、11,254 个步骤和英文 v6 format 评分；五组分别从各自候选池全局等概率、无放回选择 1,710 步，无任务配额、执行/语法过滤、内容去重或最终成功门槛。ZeroFail3 使用全部 1,710 步。

- 五组各三个 seed，从原始模型建立全新 LoRA，固定学习率 2e-4、r8/alpha16、逐步骤 token 平均 loss，GPU1 单卡累积两步；每次仅 1 epoch、855 次更新。
- 15 次训练和 DEV57 全部完成。DEV 使用同一提示词、关闭 thinking、temperature 0、seed 100、50 步、32,000 上下文和官方测试。重新评测的原始模型基线为 **1/57**。
- 最初加入逐题配额的试验已经停止并归档，旧权重不纳入下表；正式运行均按全池均匀抽样重建并重新初始化。

| 策略 | 三个 seed 的 DEV57 成功题数 | 平均成功率 | 相对 Random |
| --- | --- | ---: | ---: |
| Random | 8、4、2 | 8.19% | — |
| Net3：P−F≥3 | 2、4、8 | 8.19% | 0 pp |
| Pass4：P≥4 | 6、3、9 | 10.53% | +2.34 pp |
| ZeroFail3：F=0 且 P≥3 | 10、8、12 | **17.54%** | **+9.36 pp** |
| HighFail3：F≥3 | 3、3、3 | 5.26% | −2.92 pp |

**选择效果**：ZeroFail3 三次均胜过 Random，但 Net3 无平均收益、Pass4 增益不稳定，不能概括为所有 rubric 选样均有效。HighFail3 平均弱于 Random，却没有低于原始模型基线；相同分数也不代表三次成功的是相同任务。

**选择机制**：ZeroFail3 将训练文档查询占比从 Random 的 14.4% 提高至 62.2%，偏向更早、更短的步骤；业务修改与终止覆盖很少。选样同时改变行为类型和历史长度，不只是改变抽象质量分数。

**学习机制证据**：ZeroFail3 的评测执行错误率从 Random 的 37.1% 降至 18.8%，重复代码率从 65.2% 降至 54.0%。但 Net3 错误率更低而任务成功率无净收益，说明局部执行正确并不充分。现有证据为行为关联与案例，尚不能确认独立因果机制。

ZeroFail3 的跨 seed 净收益中一半来自同一任务家族，且 DEV57 已用于探索；后续应比较相同历史状态下的动作偏好，并消融 rubric 分项。训练仍是等步骤/更新预算，不是等 token 或等算力。

[最终分析报告](experiments/2026-10-16_appworld_rubric_selection_ablation/REPORT.md) · [运行与进度](experiments/2026-10-16_appworld_rubric_selection_ablation/README.md) · [逐运行结果](experiments/2026-10-16_appworld_rubric_selection_ablation/analysis/results.csv) · [选样统计](experiments/2026-10-16_appworld_rubric_selection_ablation/analysis/final_selection.json) · [行为统计](experiments/2026-10-16_appworld_rubric_selection_ablation/analysis/final_behavior.json)
