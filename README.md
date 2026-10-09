# taowen 工作区

这是 taowen 的个人工作区，用于存放需要通过 Git 进行版本控制的源代码、脚本、配置文件、项目文档和经确认需要保留的派生数据。

当前工作重点是研究 AppWorld 工具型智能体的轨迹学习：在 Qwen3-8B 上比较 LoRA 与全参数 SFT、经验证的单步修复训练，以及固定 rubric 评分能否提供有效的策略学习信号。

截至 **2026-10-09**，原始 Qwen3-8B 与现有 train90 / epoch5 SFT LoRA 各完成 540 条配对采样，共 1,080 条训练集轨迹并通过验收。当前下一步是统一静态 rubric 评分；本系列尚未执行 rubric 评分、GRPO 更新或新的 Dev 评测。

- 当前安排：[静态 rubric 研究待办](plans/2026-10-08_rubric_research/README.md) · [实验计划](plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md) · [长期研究设想](plans/2026-10-08_rubric_research/RESEARCH_IDEA.md)。
- 最新实验：[原始模型采样](experiments/2026-10-08_static_rubric_grpo/README.md) · [SFT LoRA 采样](experiments/2026-10-08_static_rubric_grpo_lora_init/README.md) · [完整实验报告](experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)。
- 前一阶段：[Dynamic CFST 实验总览](experiments/2026-09-28_dynamic_cfst/README.md)。以下按日期保留各阶段的主要结果。

## 原始数据位置

共享原始数据存放在本 Git 仓库之外：

`/root/autodl-tmp/data/raw_data`

请不要修改、移动或删除共享原始数据。程序读取原始数据时，应通过固定只读路径或命令行参数引用，不应把原始数据复制进本工作区。

## 版本控制范围

建议提交：

- 源代码和脚本；
- 配置文件示例；
- 项目说明和技术文档；
- 可复现分析所需的小型辅助文件；
- 经团队确认需要版本化的派生数据清单。

默认不提交：

- 未经确认的大体积原始数据；
- 模型 checkpoint；
- 日志、缓存和临时文件；
- Python 虚拟环境；
- 密钥、密码和本地环境变量文件。

具体忽略规则请查看 `.gitignore`。AppWorld 67 任务的 SFT JSONL、转换脚本和校验结果已纳入版本控制；模型权重、checkpoint、训练状态、日志和运行时缓存保留在服务器本地，不进入普通 Git 历史。

## 基本工作流程

1. 本工作区由个人使用，默认直接在 `main` 上工作，以不同 Git commit 区分版本；除非用户明确要求，不创建新分支。
2. 在 `main` 上修改并完成必要检查。
3. 提交前使用 `git status` 和 `git diff --cached` 检查变更。
4. 确认无误后提交；需要推送时按用户指令执行。

## 文档约定

本工作区内面向使用者的 README 文档统一使用中文编写。具体数据版本放在 `data/YYYY-MM-DD/`，详细转换记录写入该日期目录 README；本文件只维护高层变更。

## 2026-09-08：高 O2 Qwen3-8B SFT 数据

- 从共享只读目录中的 7 条高 `effectiveness.o2` 轨迹生成工具型智能体 SFT 数据。
- 输出位于 `data/2026-09-08/`，包含完整轨迹审计表示、决策级样本、按任务族分片、rollout 输入、清单和可复现脚本。
- 以 0006、0007、0008、0009、0010 五个 task family 构建 5-fold grouped cross-validation；同一 family 不跨 train/validation。
- 每个 fold 都有独立的 `train.jsonl`、`validation.jsonl`、`validation_tasks.jsonl` 和划分说明。
- 只进行一次 grouped holdout 时，推荐使用 `fold_05_holdout_0010`；一折是一场独立训练实验，不是一个 epoch。
- 数据删除 source thinking，规范化 Qwen function-calling 结构，并要求训练时采用 completion-only loss。
- 当前工具 schema 来自观测调用推断；Qwen 精确 token 长度检查与具体训练框架适配仍需在训练前完成。

详细说明见 [data/2026-09-08/README.md](data/2026-09-08/README.md)。

## 2026-09-10：Qwen3-8B AppWorld 完整 dev one-shot

- 使用本地 `Qwen3-8B`、官方 `simplified_react_code_agent` 和固定 one-shot Prompt；未进行训练或微调。
- 按 `dev.txt` 顺序执行全部 57 个唯一 task（19 个 scenario），57/57 均启动、结束并完成 task-specific evaluation，基础设施/评分链路失败为 0。
- 官方结果为 5/57 task success，TGC `8.8`、SGC `0.0`；本轮主要结论是完整 dev 推理与评分链路可用，不把当前分数视为最终能力上限。
- 成功 task 为 `fac291d_1`、`23cf851_2`、`68ee2c9_3`、`6c2c621_1`、`6c2c621_2`。
- 固定配置为 temperature `0`、seed `100`、每次最多 `3000` completion tokens、每任务最多 `50` steps、vLLM context `32000`，单进程在 GPU0 顺序执行。
- 正式运行耗时 `2h 21m 48s`，共 688 次 LM 调用、4190 次 AppWorld API 调用，累计 4,546,793 tokens。
- 实验根目录为 `experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/`；Git 仅保存配置、聚合评分、报告和任务状态，不保存模型日志、缓存、数据库副本或原始数据链接。
- 完整说明见 [FULL_DEV_RUN_REPORT.md](experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/FULL_DEV_RUN_REPORT.md)，逐任务分类见 [task_status.jsonl](experiments/2026-09-10_210441_appworld_qwen3-8b_react_oneshot_full_dev/task_status.jsonl)。
- 复现入口为 [run_appworld_qwen3_react_full_dev.sh](scripts/run_appworld_qwen3_react_full_dev.sh)，隔离配置入口为 [appworld_run_isolated_config.py](scripts/appworld_run_isolated_config.py)，报告生成器为 [build_appworld_full_dev_report.py](scripts/build_appworld_full_dev_report.py)。

## 2026-09-15：AppWorld ReAct 轨迹学习、LoRA 与全参数 SFT

### 实验目标

本阶段研究如何把 AppWorld 中通过官方 evaluator 且能在干净环境中重放成功的 ReAct 轨迹，转换为 Qwen3-8B 可学习的 completion-only 监督数据，并比较 LoRA 与全参数 SFT 对工具型智能体能力的影响。

原始 Qwen3-8B 已在完整 AppWorld Dev 集上取得 5/57 task success，并作为本轮评测基线。训练只使用 AppWorld train 任务；Dev 数据不参与训练。LoRA epoch 5、全参数 SFT epoch 2 和 epoch 5 均已使用同一套 57 题 Dev 官方 evaluator 完成独立对照。

### 训练数据

- 数据目录：[data/2026-09-15_appworld_qwen3-8b_react_sft_67/](data/2026-09-15_appworld_qwen3-8b_react_sft_67/)
- 来源：67 条官方评测成功且干净环境 replay 成功的 AppWorld train ReAct 轨迹
- 监督规模：67 个任务、640 个决策级样本
- 格式：任务上下文和历史 observation 作为 prompt，当前 reasoning 与 Python action 作为 assistant completion
- 训练目标：只对 assistant completion token 计算交叉熵 loss
- 上下文：使用 Qwen3 chat template，`enable_thinking=False`，最大长度 32,768 tokens；640 条样本均不截断
- 数据校验：任务分片完整、样本 ID 唯一、chat-template prefix 一致，未检测到凭据或特权上下文泄漏

### LoRA 与全参数 SFT 对照

两组实验都从同一个原始 `Qwen3-8B` 基座开始，使用相同的 67 任务数据、样本顺序、随机种子、5 个 epoch、1,600 个 optimizer steps、全局 batch 2、AdamW、学习率 2e-4、BF16、SDPA、gradient checkpointing 和 completion-only loss。核心实验变量是参数更新方式。

| 项目 | LoRA | 全参数 SFT |
|---|---:|---:|
| 可训练参数 | 21,823,488（0.2657%） | 8,190,735,360（100%） |
| 双卡策略 | DDP | FSDP FULL_SHARD |
| epoch / optimizer steps | 5 / 1,600 | 5 / 1,600 |
| 第 1 轮平均 loss | 0.650503 | 1.166161 |
| 第 5 轮平均 loss | 0.106259 | 0.166918 |
| 模型重载与生成检查 | PASS | PASS |

训练 loss 只说明模型对这 67 条教师轨迹的拟合情况，不能直接代表 AppWorld 泛化能力。本轮已在同一套 57 题 Dev 官方评测上比较原始模型、LoRA 模型和全参数 SFT 模型的 task success、scenario goal completion 和运行稳定性，结果见下节。

### 实验产物

LoRA 五轮实验：

- 实验目录：[experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/](experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/)
- 中文报告：[REPORT.md](experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/REPORT.md)
- Dev 评测说明：[DEV_EVAL_READY_EPOCH5.md](experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/DEV_EVAL_READY_EPOCH5.md)
- 本地最终 adapter：`artifacts/continuation/adapter_epoch5`

全参数 SFT 五轮实验：

- 实验目录：[experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/](experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/)
- 中文报告：[REPORT.md](experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/REPORT.md)
- Dev 评测说明：[DEV_EVAL_READY.md](experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/DEV_EVAL_READY.md)
- 本地最终完整模型：`artifacts/model`
- epoch 1–4 中间完整权重原位于 `artifacts/checkpoints`，已于 2026-09-18 清理；最终模型仍保留在 `artifacts/model`

Git 保存训练数据、通用脚本、配置、指标、Loss 图、中文报告和 SHA256 清单。LoRA adapter、全参数模型权重和中间 checkpoint 体积较大，均由 `.gitignore` 排除并保留在训练服务器上。

### Dev 评测入口（已完成）

- LoRA：[scripts/run_appworld_qwen3_react_lora_full_dev.sh](scripts/run_appworld_qwen3_react_lora_full_dev.sh)
- 全参数 SFT：[scripts/run_appworld_qwen3_react_full_sft_full_dev.sh](scripts/run_appworld_qwen3_react_full_sft_full_dev.sh)

两份入口脚本分别加载 LoRA adapter 与独立完整模型，并复用原始模型 Dev 基线的 AppWorld ReAct 评测协议；本轮正式对齐评测已经完成。

### 正式 Dev 对齐评测结果

四组结果均覆盖 Dev 的 57 个唯一任务和 19 个 scenario，并使用同一套 AppWorld ReAct 提示、工具接口与官方 evaluator。

| 模型 | Task Goal Completion（TGC） | Scenario Goal Completion（SGC） | 测试项通过 |
|---|---:|---:|---:|
| Base Qwen3-8B | 5/57（8.8%） | 0/19（0%） | 114/291（39.2%） |
| LoRA epoch 5 | 5/57（8.8%） | 1/19（5.3%） | 105/291（36.1%） |
| Full-SFT epoch 2 | 0/57（0%） | 0/19（0%） | 64/291（22.0%） |
| Full-SFT epoch 5 | 0/57（0%） | 0/19（0%） | 86/291（29.6%） |

正式评测目录和报告：

- LoRA epoch 5：[experiments/2026-09-15_174500_appworld_qwen3-8b_react_lora_aligned_full_dev/](experiments/2026-09-15_174500_appworld_qwen3-8b_react_lora_aligned_full_dev/)；[REPORT.md](experiments/2026-09-15_174500_appworld_qwen3-8b_react_lora_aligned_full_dev/REPORT.md)
- Full-SFT epoch 2：[experiments/2026-09-15_220731_appworld_qwen3-8b_react_full_sft_epoch2_aligned_full_dev/](experiments/2026-09-15_220731_appworld_qwen3-8b_react_full_sft_epoch2_aligned_full_dev/)；[REPORT.md](experiments/2026-09-15_220731_appworld_qwen3-8b_react_full_sft_epoch2_aligned_full_dev/REPORT.md)
- Full-SFT epoch 5：[experiments/2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev/](experiments/2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev/)；[REPORT.md](experiments/2026-09-15_205155_appworld_qwen3-8b_react_full_sft_epoch5_aligned_full_dev/REPORT.md)

Full-SFT epoch 2 和 epoch 5 的 57 个任务中，`content=null` 均为 0。两次全参数 SFT 的退化不是接口层吞掉模型输出，而是模型输出和工具决策质量下降。

Git 只保留轻量报告、聚合元数据和复现配置；`logs/`、`cache/`、`outputs/`、运行时数据库、模型文件和指向服务器绝对路径的 symlink 均排除在版本控制之外。`artifacts.sha256` 可能引用仅保留在服务器上的 ignored 产物，因此 clone 后不保证能够完成全部离线哈希复验。

## 2026-09-16：Train-15 四模型对齐诊断

- 从 `SFT67 ∩ Train90` 固定选择 5 个完整 scenario、每个 3 个任务，共 15 个训练内任务；该结果用于诊断轨迹学习，不作为未见任务泛化分数。
- 四组均使用官方 ReAct prompt、temperature `0`、seed `100`、每题最多 `50` steps 和官方 evaluator；Base 与三个训练模型分别复用各自正式 Dev 评测的接口设置。
- Base 为 1/15 TGC、0/5 SGC、32/84 条断言通过；LoRA epoch 5 为 4/15 TGC、1/5 SGC、43/84 条断言通过。
- Full-SFT epoch 2 和 epoch 5 均为 0/15 TGC，断言通过分别为 15/84 和 25/84；说明全参数训练未形成端到端可用策略，问题不只是 Dev 泛化。
- LoRA 的成功集中于较简单场景，体现明确的 seen-task 优势，但尚不足以证明通用工具策略能力提升。
- 实验目录：[experiments/2026-09-16_154629_appworld_train15_four_models_aligned/](experiments/2026-09-16_154629_appworld_train15_four_models_aligned/)
- 中文报告：[artifacts/REPORT.md](experiments/2026-09-16_154629_appworld_train15_four_models_aligned/artifacts/REPORT.md)
- 结构化汇总：[artifacts/summary.json](experiments/2026-09-16_154629_appworld_train15_four_models_aligned/artifacts/summary.json)

## 2026-09-18：裸 Qwen3-8B AppWorld test_normal

- 使用本地裸 `Qwen3-8B`、官方 `simplified_react_code_agent`、官方 one-shot ReAct prompt 与 AppWorld 0.2.0.dev0 evaluator，对 `test_normal` 全部 168 个任务（56 个 scenario）完成推理和评分。
- 协议与 2026-09-10 的完整 Dev 基线一致：temperature `0`、seed `100`、单次最多 `3000` completion tokens、每题最多 `50` steps、context `32000`，GPU0 单进程顺序执行。
- 官方结果为 12/168 task success，TGC `7.1`、SGC `0.0`；难度 1/2/3 的 TGC 分别为 `19.3`、`2.1`、`0.0`。
- evaluator 条件通过 386/1077（35.8%）。主要错误不是单一类型：最终答案不匹配涉及 90 题，交易或购物状态错误 48 题，Venmo 状态错误 39 题，Spotify 状态错误 38 题；23 题达到 50 步上限。
- 接口审计发现 3 次空 `content`，分布于 3 个 scenario，占 2859 次 LM 调用的 0.105%，因此触发风险提示但不足以解释主体失败；80 次 `content=null` 均为可解释的纯 reasoning 长度截断，无法解释的空响应为 0。
- 168 个任务目录、`finished` 标记、官方逐题报告、逐题“正确/错误”记录和官方聚合 ID 均完成一致性校验；运行退出码为 0。
- 实验目录：[experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/)
- 中文报告：[REPORT.md](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/REPORT.md)
- 逐题结果：[task_status.jsonl](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/task_status.jsonl)
- 结构化汇总：[summary.json](experiments/2026-09-17_105709_appworld_qwen3-8b_react_oneshot_test_normal/summary.json)

## 2026-09-21：Codex-RFT train90 LoRA 正式评测

- 使用 train90 上的 Codex-RFT 成功轨迹训练 Qwen3-8B LoRA 5 轮，评测时加载同一份最终 adapter；训练记录见 [训练报告](experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/REPORT.md)。
- 官方 Dev 57 题成功 23/57，TGC `40.4`、SGC `21.1`；详见 [Dev 报告](experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/REPORT.md)。
- 官方 test_normal 168 题成功 51/168，TGC `30.4`、SGC `16.1`；详见 [Test 报告](experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168/REPORT.md)。
- 两次评测使用 ReAct agent、temperature `0`、seed `100`、每题最多 `50` 步、每轮最多 `3000` 输出 tokens、vLLM context `32000`；不启用 reasoning parser。历史基座评测使用了不同的输出解析协议，其分数差异不能全归因于 LoRA 权重。
- Test 失败题中有 24 题遇到上下文请求被拒绝：13 题为输入与预留输出之和超过窗口，11 题为输入本身超过窗口。原始轨迹与测试环境数据仅保留在本地，不进入 Git。
- 针对这 24 题的受限诊断复测已于 2026-09-22 完成，结果见下一节；测试题反馈不用于训练。

## 2026-09-22：Test 上下文错误 24 题扩窗复测

- 同一 LoRA adapter 和 ReAct 协议，只把推理窗口从 `32000` 提至 `40960`；运行 24/24 题，官方成功 1/24。
- 上下文拒绝从 24/24 降至 8/24；另有 15 题无窗口错误但仍未成功。官方测试条件由 55/213 增至 83/213。
- 这是按旧报错挑选的子集，不是新的完整 test_normal 168 题成绩；新旧轨迹存在分叉，不能将每题结果都归因于窗口。
- 完整协议、逐题对照、token 开销与因果边界见 [中文报告](experiments/2026-09-22_101628_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal_context40960_24/REPORT.md)。

## 2026-09-23：train90 全参数 SFT 方案准备

- 已保存工作区基线，并对照 train90 LoRA 与旧 67 轨迹全量 SFT，完成 [训练方案、配置草案和 CPU 核验](plans/2026-09-23_train90_full_sft/README.md)。
- 拟使用同一原始 Qwen3-8B、90 条轨迹的 1170 个决策样本、40960 上下文和 5 轮训练，更新全部参数；规划更低学习率、completion 位置 logits 优化与完整断点续训。
- 以上为训练授权前的准备记录；后续已完成训练器改造、双卡预检与正式五轮训练，实际结果见下节。

## 2026-09-23：train90 全参数 SFT 五轮实验

- 从原始 Qwen3-8B 开始，对与 train90 LoRA 相同的 90 条轨迹、1170 个决策样本完成 5 轮 / 2925 步训练，全部 8,190,735,360 个参数参与优化。FP32 主参数与 AdamW 状态，BF16 计算和最终权重；最大训练序列 37015 tokens，额外 token 截断为 0。
- 每轮平均 loss：`0.589548 → 0.274838 → 0.129335 → 0.053033 → 0.016795`。正式启动到模型导出约 3.36 小时，包含保存和第 100 步保存频率切换的恢复过程，不含此前预检。
- 训练期间每轮末滚动保存一次；训练完成后按用户要求清理最终完整续训状态，释放约 91.54 GiB，保留约 15.3 GiB 的 BF16 最终模型和全部训练记录。模型重载/输出格式、399 个权重 tensor 的名称形状、完整参数数量和 SHA-256 核验均通过。Dev 57 题和 test_normal 168 题结果见后文；训练 loss 不代表任务成功率。
- [中文报告](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/REPORT.md) · [本次五轮 loss](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/metrics/loss_curve_total_5epochs.png) · [与旧 67 轨迹的 loss 对比](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/metrics/loss_curve_compare_full_sft_67_vs_90.png) · [独立核验记录](experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/metrics/final_artifact_validation.json)。PDF、逐步 CSV、复现命令和完整指标均在同一实验目录。

## 2026-09-23：train90 全参数 SFT Dev57 正式评测

- 固定上述第 5 轮最终完整模型，按 train90 LoRA 相同的 Dev 57 题、ReAct 提示词、temperature `0`、seed `100`、每题 `50` 步、单次 `3000` 输出 tokens、context `32000` 和无 reasoning parser 协议完成官方评分。
- 全参数 SFT 成功 **12/57**，TGC **21.1**、SGC **0.0**；对照 LoRA 为 23/57、40.4、21.1，少成功 11 题。共同成功 7 题、新增成功 5 题、退化 16 题；测试条件通过 163/291。
- 正式评测约 23.3 分钟，57 个任务记录与官方结果一致，evaluator 错误为 0。1003 次 LM 请求含 9 次上下文拒绝；994 次正常回复均保留 Python 代码。该次 Dev 运行未扩窗重试；后续 test_normal 168 题已独立完成，见下节。
- [中文报告](experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/REPORT.md) · [逐题对照 CSV](experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/task_comparison.csv) · [结构化结果及审计](experiments/2026-09-23_062600_appworld_qwen3-8b_react_full_sft_codex_rft_train90_dev57/summary.json)。模型不复制到评测目录，原始轨迹、数据库、日志和缓存仅保留在本地。

## 2026-09-23：train90 全参数 SFT test_normal168 正式评测

- 固定第5轮最终全参数模型，与 train90 LoRA 原始完整 test_normal168 使用相同 ReAct、temperature `0`、seed `100`、50步、单次3000输出tokens、context32000和无reasoning parser协议；168题首轮messages、输入token数和固定请求字段逐题核对一致。
- 全参数 SFT 成功 **28/168**，TGC **16.7**、SGC **5.4**（3/56场景）；LoRA为51/168、30.4、16.1，少成功23题。条件通过数为498/1077，对照LoRA598/1077。
- 共同成功18题、FFT新增成功10题、退化33题。退化题中29题出现提交动作但未满足业务条件，2题耗尽步数，2题上下文中断。全量FFT有29题超窗、19题归为50步终止；不能仅用窗口解释总体差额。
- 五轮平均训练loss更低，但Dev和Test的任务完成率均低于LoRA；小数据过度适配、更新范围和纠错轨迹不足值得优先验证，现有最终模型不能证明第2轮一定优于第5轮。
- 正式运行约83.1分钟，退出码0、评分器错误0。3667次LM请求中3638次正常回复均含Python代码，29次为上下文拒绝占位；模型未修改，GPU已释放。逐题/场景CSV、7组案例、1008份原始证据哈希及最终一致性检查均通过。
- [详细中文报告](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/REPORT.md) · [逐题对照CSV](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/task_comparison.csv) · [场景对照CSV](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/scenario_comparison.csv) · [配对案例](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/CASE_STUDIES.md)。
- [性能对比图](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/metrics/performance_comparison.png) · [五轮loss对比图](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/metrics/training_loss_comparison.png) · [结构化结果](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/summary.json) · [最终核验](experiments/2026-09-23_070617_appworld_qwen3-8b_react_full_sft_codex_rft_train90_test_normal168/metrics/final_validation.json)。PNG/PDF均已保存，原始轨迹和数据库仅保留在本地。

## 2026-09-23：train90 全参数 SFT 两轮停止对照

- 从原始 Qwen3-8B 重新训练相同 train90 数据，完成 **2轮 / 1170步**；保留原五轮的2925步cosine计划和88步warmup，只执行前两轮，避免同时改变学习率路径。每轮平均loss为 `0.589565 → 0.272481`。
- 固定最终第2轮模型，按旧五轮和LoRA相同协议完成 test_normal 全部168题。两轮 **28/168、TGC 16.7、SGC 8.9（5/56）**；五轮28/168、16.7、5.4（3/56）；LoRA51/168、30.4、16.1（9/56）。
- 两轮和五轮共同成功17题、两轮新增11题、丢失11题。两轮完整场景增加2个，但条件通过数从498/1077降至444/1077；难度1成功多4题，难度2/3少3题/1题。总体任务成功率未提高，也未缩小与LoRA的差距，本次结果不足以确认五轮过拟合。
- 两轮上下文拒绝44题、50步终止35题，对照五轮29题、19题；重复行为和错误恢复问题在两轮模型中同样存在。按56个场景配对bootstrap得到TGC分差0个百分点、95%区间[-4.76,+4.76]，仅描述场景组成敏感性。
- 前1170步学习率及每卡样本长度/监督token序列全部匹配，但混合精度分布式重训未实现逐位数值复现；不能当作同一次训练保存的epoch2/epoch5权重对照。用户在观察旧test结果后指定第2轮，本次为诊断性复验，没有根据新test成绩选择检查点。
- 训练约69.9分钟，正式评测约84.2分钟；保留epoch1和最终epoch2两份BF16模型，各约15.27GiB，无optimizer重启分片。168题状态、官方评分、30个模型文件哈希、1008份任务证据及归档校验全部通过，GPU已释放。
- [详细中文评测报告](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/REPORT.md) · [训练报告](experiments/2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5/REPORT.md) · [六组配对案例](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/CASE_STUDIES.md) · [逐题CSV](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/task_comparison.csv) · [场景CSV](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/scenario_comparison.csv)。
- [两轮/五轮loss对比](experiments/2026-09-23_093945_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch2_prefix5/metrics/loss_comparison.png) · [性能对比图](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/metrics/performance_comparison.png) · [结构化结果](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/summary.json) · [最终核验](experiments/2026-09-23_093945_appworld_qwen3-8b_react_full_sft_codex_rft_train90_epoch2_prefix5_test_normal168/metrics/final_validation.json)。图像同时保存PDF，权重和原始运行轨迹仅保留在服务器本次实验目录。

## 2026-09-28—29：Dynamic CFST 单步修复训练与 Dev57 评测

- 从已有 train90 / epoch5 SFT LoRA 出发，完成 train90 学生轨迹采集，官方成功 46/90；按任务族冻结来源 60 题与检查 30 题，只在来源侧构造和验证教师单步替代动作。
- 共得到 20 条官方成功验证的修复样本，形成 State 12 条、Action 8 条、Mixed 20 条三个独立训练包。各包 1 epoch 分支分别更新 6、4、10 次；检查 30 题成功数分别为 17、19、15，按冻结规则选出 Action 候选。
- 完整 Dev57 结果如下；原 epoch5 基线复用历史记录，State 与 Mixed 为后续补充诊断。

| 模型 | Dev57 官方成功 | 测试条件通过 |
| --- | ---: | ---: |
| 原 train90 LoRA epoch5 | 23/57（40.4%） | 206/291 |
| CFST-Action，1 epoch | 31/57（54.4%） | 215/291 |
| CFST-State，1 epoch | 25/57（43.9%） | 179/291 |
| CFST-Mixed，1 epoch | 21/57（36.8%） | 184/291 |

- Action 相对基线新增成功 14 题、退步 6 题，净增 8 题，通过既有接受门槛。上述为本阶段 Dev 结果，尚未执行来源 60 题刷新；后续 State/Mixed 诊断保留原 Action 选择记录。
- [实验总览](experiments/2026-09-28_dynamic_cfst/README.md) · [1 epoch 训练记录](experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md) · [Action Dev57 报告](experiments/2026-09-28_dynamic_cfst/step07c_dev57_action_one_epoch/README.md) · [四模型逐题对照](experiments/2026-09-28_dynamic_cfst/step07e_dev57_state_one_epoch/four_model_per_task.csv) · [研究方案](plans/2026-09-28_capability_frontier/README.md)。

## 2026-10-08—09：静态 rubric 实验的双起点 train90 采样

本系列准备采用 DRACO 的固定 21 条规则进行轨迹级评分，再验证其是否能提供有效的 GRPO 相对优势。**目前只完成采样与验收；尚无 rubric 评分、GRPO 权重更新或本系列的新 Dev 结果。**

| 训练集采样诊断 | 原始 Qwen3-8B | 现有 SFT LoRA |
| --- | ---: | ---: |
| 完整轨迹 / 每题六条的完整组 | 540 / 90 | 540 / 90 |
| 官方终态成功轨迹 | 39/540（7.22%） | 186/540（34.44%） |
| 六次全失败的任务 | 70 | 23 |
| 成功与失败混合的任务 | 20 | 63 |
| 六次全成功的任务 | 0 | 4 |

- 两组使用相同的 train90 任务、六个固定 seed、ReAct prompt、parser 与执行预算。temperature `1`、top_p `1`、top_k `-1`、repetition_penalty `1`、`enable_thinking=false`；每题最多 50 步、上下文 32000、每步最多 3000 输出 tokens，超窗时结束且不裁剪历史。GPU 0 生成，最多六路隔离环境并发。
- LoRA 起点为已有 train90 / epoch5 adapter（rank 8、alpha 16）。它已使用同一 train90 的 Codex 示范训练，因此上表是训练内随机采样诊断，两组差值不能解释为 rubric 收益或 Dev 泛化提升。
- 两组全部轨迹通过完整性、token 重建与旧策略 logprob 对齐验收。LoRA 采样因 Ellipsis 日志序列化错误中断后，保留原有 342 条完整轨迹不变，修复日志兼容性并补齐 198 条；失败、无代码和预算耗尽样本均保留。
- 下一步按计划先检查 24 条轨迹的静态评分，再覆盖全部 1,080 条，分析规则判定与组内差异；评分可用后再接入 GRPO 续训和统一 Dev57 对照。实验目录中的早期训练原型与旧预算不代表已执行训练。
- [原始模型采样说明](experiments/2026-10-08_static_rubric_grpo/README.md) · [LoRA 采样说明](experiments/2026-10-08_static_rubric_grpo_lora_init/README.md) · [完整实验报告](experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md) · [配对采样统计](experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/collection_comparison.json) · [恢复验收记录](experiments/2026-10-08_static_rubric_grpo_lora_init/recovery/2026-10-09/final_diagnostics.json)。
- 总体规划集中在 [plans/2026-10-08_rubric_research/](plans/2026-10-08_rubric_research/README.md)，实际运行记录保留在 experiments。完整采样轨迹所在的 `runs/`、运行时缓存和模型权重由 `.gitignore` 排除；Git 中保留实验代码、配置、报告、来源快照及已纳入版本控制的恢复记录。
