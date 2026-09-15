# taowen 工作区

这是 taowen 的个人工作区，用于存放需要通过 Git 进行版本控制的源代码、脚本、配置文件、项目文档和经确认需要保留的派生数据。

当前工作重点是研究 AppWorld 工具型智能体的轨迹学习：从可验证的正确 ReAct 轨迹构造监督数据，在同一 Qwen3-8B 基座上完成 LoRA 和全参数 SFT，并使用统一的 AppWorld Dev 协议比较训练前后的能力。

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

1. 开始任务前创建独立分支。
2. 在分支中修改并测试代码。
3. 提交前使用 `git status` 和 `git diff --cached` 检查变更。
4. 确认无误后提交，并在配置远程仓库后推送分支。

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

原始 Qwen3-8B 已在完整 AppWorld Dev 集上取得 5/57 task success，作为后续评测基线。训练只使用 AppWorld train 任务；Dev 数据不参与训练，后续继续使用官方 evaluator 进行独立对照。

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

训练 loss 只说明模型对这 67 条教师轨迹的拟合情况，不能直接代表 AppWorld 泛化能力。最终结论需要比较原始模型、LoRA 模型和全参数 SFT 模型在同一套 57 题 Dev 官方评测上的 task success、scenario goal completion 和运行稳定性。

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
- epoch 1–4 本地完整权重：`artifacts/checkpoints`

Git 保存训练数据、通用脚本、配置、指标、Loss 图、中文报告和 SHA256 清单。LoRA adapter、全参数模型权重和中间 checkpoint 体积较大，均由 `.gitignore` 排除并保留在训练服务器上。

### 后续 Dev 评测入口

- LoRA：[scripts/run_appworld_qwen3_react_lora_full_dev.sh](scripts/run_appworld_qwen3_react_lora_full_dev.sh)
- 全参数 SFT：[scripts/run_appworld_qwen3_react_full_sft_full_dev.sh](scripts/run_appworld_qwen3_react_full_sft_full_dev.sh)

两份入口脚本分别加载 LoRA adapter 与独立完整模型，并复用原始模型 Dev 基线的 AppWorld ReAct 评测协议。
