# CFST 第一实验：执行备注

> **2026-09-29适用范围更新：** 下文六分支、学习率2e-5、每支8,000监督tokens等均为早期历史草案，不能用于当前执行。当前以 [第6步1epoch计划](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/STEP06_ONE_EPOCH_PLAN.md) 为准：三个分支、学习率2e-4、各自数据一遍、6/4/10次更新，保持旧评测协议；现已完成训练及核验，后续第7b步检查30题也已完成，结果见滚动待办；训练产物见 [第6b步训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/README.md)。

本文件供实际实施时查路径和参数。阅读方法先看 [METHOD_PROPOSAL.md](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md)。

以下是计划，尚未执行。路径已经核对；新训练设置是本次拟定的起点，不是已验证的最佳配置。

## 已有模型与数据

- 基座：[Qwen3-8B](/root/autodl-tmp/models/Qwen3-8B)。
- 初始adapter：[train90 LoRA第5轮 adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter)。
- 原实验名称：2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5。
- 原评测服务名称：appworld-codex-rft-train90-epoch5。
- 原训练配置：[training_config.json](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/config/training_config.json)。
- 原评测配置：[Dev57 manifest](/root/autodl-tmp/workspace-tw/experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57/manifest.json)。
- 原有教师训练数据：[train.jsonl](/root/autodl-tmp/workspace-tw/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/train.jsonl)。它已用于训练初始模型，本实验主要新增学生失败状态下的修复目标。
- AppWorld任务根目录：[runtime](/root/autodl-tmp/data/benchmarks/appworld/runtime)。沿用项目当前90题train与57题dev清单。
- 纠错教师沿用已有采样配置：gpt-5.6-sol，reasoning_effort=high；依据 [采样manifest](/root/autodl-tmp/workspace-tw/experiments/2026-09-20_103356_appworld_codex_rft_train90_unattended/manifest.json)。新采样仍需确认该接口能调用，不能静默换教师。

## 六组短训练的拟议共同设置

| 项目 | 第一版设置 |
|---|---|
| 初始化 | 相同Qwen3-8B基座 + 相同旧adapter；各组独立开始 |
| 更新参数 | 继续训练已有LoRA，rank=8、alpha=16，不做FFT |
| 优化器 | AdamW；所有组从同样的全新优化器状态开始 |
| 学习率 | 固定2e-5，比旧五轮训练的2e-4更小，作为短程补充训练起点 |
| 每卡batch / 全局batch | 1 / 2；沿用双卡训练结构 |
| 训练精度 | BF16 |
| 训练窗口 | 40,960；新增样本超长时送审处理，不静默裁掉关键历史 |
| 监督对象 | 仅修复步骤的assistant答案；包括可见说明与Python代码 |
| 训练预算 | 每组累计约8,000个目标tokens，包含重复采样；实际偏差尽量控制在5%内 |
| 训练量匹配 | 随机对照匹配目标长度及历史长度分布；记录步数、输入tokens和耗时，不宣称等目标tokens就等计算量 |
| 随机种子 | 初次20260928；有正信号后用另一个种子复验 |
| 输出 | 六个独立新adapter；原adapter保留 |

本轮不要求各组训练相同epoch数。因为不同组的样本长度不同，按需要学习的目标tokens匹配预算更清楚。相同全局batch下更新次数可能不同，要在结果中记录，后续再做等更新次数的敏感性检查。

随机对照从60题产生的同一个合格修复池抽样，不限错误类别；不得为了让结果好看而排除某类。检查训练组与对照是否严重重叠；若池太小无法形成有区别的对照，先补采60题中的修复样本。

## 执行与评测设置

沿用原LoRA评测：temperature=0，seed=100，context=32,000，每轮最多3,000输出tokens，每题最多50个动作，无reasoning parser，官方evaluator评分。

从中间位置继续的测试，先重放原动作恢复数据库、REPL变量等状态，再让被测模型接手。所有模型使用相同起点和剩余动作预算：前面已经执行的动作也计入整题50步上限。Codex替代动作在修复验证中也占一步。每个被测模型使用独立环境副本。

temperature=0下重复相同执行不算独立随机试验。复验首先改变训练种子；如增加随机生成评测，必须为所有组统一温度和采样次数，作为另一项实验报告。

30道train检查题在六组训练前固定，先标记需要检查的决策类型，不根据训练后成绩换题。每题优先固定一个检查起点；保留一定数量原本成功的起点以检查退化。某类不足时如实报告数量，不伪造三类等量数据。

从这30题选出一个训练组后，锁定选择，再跑Dev57三个模型。若没有正收益，则不强行选“最佳组”宣布成功，按主计划调整或停止。Dev用于开发评价，最终论文性能结论另需预先固定的独立测试。

## 需要复用和扩展的现有程序

| 已有文件 | 已有能力 | 本实验的扩展 |
|---|---|---|
| [appworld_run_isolated_lora_config.py](/root/autodl-tmp/workspace-tw/scripts/appworld_run_isolated_lora_config.py) | 加载adapter、指定数据集、逐题评分 | 新建train90及三个Dev模型的运行配置；显式关闭reasoning parser，不能依赖旧默认值 |
| [appworld_codex_rft_sampler.py](/root/autodl-tmp/workspace-tw/scripts/appworld_codex_rft_sampler.py) | 用Codex按环境反馈生成动作 | 提供学生错误前缀、生成单步修复候选；续跑交回Qwen |
| [continue_appworld_react_lora.py](/root/autodl-tmp/workspace-tw/scripts/continue_appworld_react_lora.py) | 加载已有adapter、completion-only续训 | 在独立实验入口加入累计目标token停止条件、独立优化器初始化、每组新输出目录 |
| [convert_appworld_codex_rft_to_qwen_sft.py](/root/autodl-tmp/workspace-tw/scripts/convert_appworld_codex_rft_to_qwen_sft.py) | 现有prompt/completion格式与脱敏逻辑 | 复用格式契约，新写“学生前缀→已验证修复”转换；不能不加改造直接把混合来源轨迹塞进旧转换器 |

另需新增：执行前缀恢复器、修复验证记录、60/30题分组清单、三类数据与随机对照构建器、从固定起点续跑的比较程序。新增文件名称在实现时确定，本次不创建这些程序。

先验证一条任务前缀能正确重放，再扩到批量；若状态或可见反馈不一致，先修复恢复程序，不在错位环境中进行实验。

