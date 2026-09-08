# 2026-09-08：7 条高 O2 轨迹的 Qwen3-8B Grouped-CV SFT 数据

## 1. 目标与当前结论

本目录从远端只读原始数据目录 `/root/autodl-tmp/data/raw_data` 中选取 7 条高 `effectiveness.o2` 智能体轨迹，转换为面向 `Qwen/Qwen3-8B` 的工具调用 SFT 数据。

训练目标是让模型学习：

- 根据用户任务和现有上下文选择下一步工具；
- 读取工具返回后决定继续、纠错、验证还是结束；
- 在工具失败后采取恢复动作；
- 在完成关键检查后生成最终答复。

本次没有训练模型。已经完成数据规范化、5-fold grouped cross-validation 划分、数据清单与结构验收。

## 2. 一条原始轨迹是否等于一条训练样本

不完全是。本目录同时保留两个粒度：

- `canonical/full_trajectories.jsonl`：7 行，一条原始轨迹对应一条完整规范化轨迹，用于审计和回看。
- 决策级 JSONL：把每个 assistant 决策点拆成一个 `prompt/completion` 样本，共 1,627 行。

实际 SFT 推荐使用决策级样本。每行中：

- `prompt`：模型在当前动作前能看到的 system、user、历史 assistant 调用和 tool 返回；
- `completion`：此刻应预测的恰好一个 assistant 动作；
- `tools`：传给 Qwen chat template 的工具定义；
- `metadata`：轨迹、任务族、O2、fold、标签、长度和权重等审计字段。

工具结果不是监督输出。它只进入后续决策的 `prompt`，模型学习的是“看到这个工具结果以后应该做什么”。

直接把一条数百步轨迹当成一个训练样本会产生极长序列、截断和 loss 边界不清晰，因此完整轨迹仅作审计，训练采用一个 assistant 决策点一行。

## 3. 7 条轨迹与真实 O2

质量只依据每条远端 `score.json` 中：

`result.aggregates[id=effectiveness.o2].score`

不依据目录状态 `SCORED`、`INVALID_CANDIDATE` 等判断。

| 轨迹 | O2 | task family | 决策样本 | score ruleset |
|---|---:|---:|---:|---:|
| EI-56TESTPK0006-easy-v1.2 | 98.513181 | 0006 | 166 | 4.11.1 |
| EI-56TESTPK0007-medium-v1.2 | 89.444495 | 0007 | 130 | 4.11.1 |
| EI-56TESTPK0008-easy-v1.2 | 98.416022 | 0008 | 169 | 4.11.1 |
| EI-56TESTPK0008-medium-v1.2 | 87.948952 | 0008 | 265 | 4.11.1 |
| EI-56TESTPK0009-medium-v1.2 | 98.176015 | 0009 | 222 | 4.11.1 |
| EI-56TESTPK0010-easy-v1.2 | 99.629670 | 0010 | 455 | 4.11.1 |
| EI-56TESTPK0010-medium-v1.2 | 89.007634 | 0010 | 220 | 4.11.1 |

7 个 score 文件均为 ruleset release `4.11.1`。原始项目中的 `rules.md` 声明 release `4.12.0`。本次没有用 4.12.0 重算历史得分，而是保留 score 文件中已冻结的 4.11.1 O2；两个版本及文件 SHA-256 均记录在 `manifest.json`。

## 4. 为什么采用 5-fold grouped cross-validation

共有 5 个任务族：0006、0007、0008、0009、0010。每一折完整留出一个 task family 做验证，其余四个 family 做训练。同一 family 的 easy/medium 永远处于同一侧，因此不会发生同族步骤跨 train/validation 的泄漏。

| Fold | 验证 family | 训练 families | train 决策样本 | validation 决策样本 | rollout 任务 |
|---|---:|---|---:|---:|---:|
| fold_01_holdout_0006 | 0006 | 0007, 0008, 0009, 0010 | 1,461 | 166 | 1 |
| fold_02_holdout_0007 | 0007 | 0006, 0008, 0009, 0010 | 1,497 | 130 | 1 |
| fold_03_holdout_0008 | 0008 | 0006, 0007, 0009, 0010 | 1,193 | 434 | 2 |
| fold_04_holdout_0009 | 0009 | 0006, 0007, 0008, 0010 | 1,405 | 222 | 1 |
| fold_05_holdout_0010 | 0010 | 0006, 0007, 0008, 0009 | 952 | 675 | 2 |

### Fold 与 epoch 不是一回事

一个 fold 是一场完整且独立的训练实验：

1. 从同一个未经本批数据微调的 Qwen3-8B 基座开始；
2. 使用该 fold 的 `train.jsonl` 训练若干 epoch；
3. 使用该 fold 的 `validation.jsonl` 和 `validation_tasks.jsonl` 评估；
4. 保存该 fold 独立的 checkpoint 和指标。

完整 5-fold 需要这样独立训练 5 次。不能先训练 fold 1，再拿 fold 1 的 checkpoint 接着训练 fold 2，否则验证任务已经通过前一折参数更新泄漏进模型。

### 只训练一次时如何退化

推荐单次划分是：

`folds/fold_05_holdout_0010`

它与最初的划分一致：0006/0007/0008/0009 训练，0010 验证。如果只跑这一折，就是一次 grouped holdout 实验，不是“完整 5-fold 交叉验证”，也不能报告五折平均结果。

完整 5-fold 汇总时建议：

- 主指标：5 个 holdout family 指标的宏平均和标准差，使每个 family 权重相同；
- 辅助指标：按验证样本数加权的 micro 平均；
- 同时保留逐 family 指标，因为各折样本数差异很大。

## 5. 文件架构

```text
data/2026-09-08/
├── README.md
├── manifest.json
├── fold_registry.json
├── tools.inferred.json
├── requirements-tokenizer.txt
├── canonical/
│   ├── full_trajectories.jsonl
│   ├── decision_samples.jsonl
│   ├── family_0006.jsonl
│   ├── family_0007.jsonl
│   ├── family_0008.jsonl
│   ├── family_0009.jsonl
│   ├── family_0010.jsonl
│   ├── rollout_tasks.jsonl
│   └── rejected_samples.jsonl
├── folds/
│   ├── fold_01_holdout_0006/
│   ├── fold_02_holdout_0007/
│   ├── fold_03_holdout_0008/
│   ├── fold_04_holdout_0009/
│   └── fold_05_holdout_0010/
│       ├── README.md
│       ├── split.json
│       ├── train.jsonl
│       ├── validation.jsonl
│       └── validation_tasks.jsonl
└── scripts/
    ├── conversion_core.py
    ├── convert_trajectories.py
    └── validate_dataset.py
```

每个 fold 都真实保存自己的 `train.jsonl` 和 `validation.jsonl`，因此可以直接按目录选择实验，不需要先解析索引文件。代价是同一 canonical 样本会出现在四个 fold 的训练文件和一个 fold 的验证文件中，磁盘占用较大；这是为了换取训练入口清晰和减少人为拼接错误。

### canonical 文件

- `full_trajectories.jsonl`：7 条完整规范化轨迹。
- `decision_samples.jsonl`：全部 1,627 个决策级样本，主要用于审计和重新划分。
- `family_*.jsonl`：按 task family 保存一次的 canonical 决策分片。
- `rollout_tasks.jsonl`：7 条只含根 system/user 的整任务生成输入。
- `rejected_samples.jsonl`：单步 completion 超限而拒绝的样本；本次为 0 行。

### fold 文件

- `train.jsonl`：该折训练数据。
- `validation.jsonl`：该折决策级验证数据。
- `validation_tasks.jsonl`：仅含该折 holdout 轨迹的根任务，用于端到端 rollout。
- `split.json`：训练/验证 family、计数和数据文件 SHA-256。
- `README.md`：人类可读的该折说明。

`fold_registry.json` 汇总 5 折配置并标记默认单折。

## 6. Qwen 数据结构与 loss

简化后的单行结构：

```json
{
  "id": "EI-...::assistant-0001",
  "prompt": [
    {"role": "system", "content": "稳定 EI 工具智能体约束"},
    {"role": "user", "content": "任务输入"},
    {"role": "assistant", "content": "", "tool_calls": []},
    {"role": "tool", "tool_call_id": "...", "name": "Read", "content": "工具返回"}
  ],
  "completion": [
    {
      "role": "assistant",
      "content": "",
      "tool_calls": [
        {
          "id": "...",
          "type": "function",
          "function": {
            "name": "Read",
            "arguments": {"file_path": "data/..."}
          }
        }
      ]
    }
  ],
  "tools": [],
  "metadata": {
    "task_family": "0008",
    "fold_id": "fold_03_holdout_0008",
    "split": "validation",
    "trajectory_sample_weight": 0.005917
  }
}
```

训练接入时必须：

1. 使用目标 Qwen 模型自带 tokenizer 的 `apply_chat_template`，不要手写 Qwen 特殊 token；
2. 将每行的 `tools` 传给 chat template；
3. 使用 `enable_thinking=False`，与本数据删除 source thinking 的策略一致；
4. 拼接 `prompt + completion`；
5. prompt token 和 padding token 的 label 设为 `-100`；
6. 只让 completion token 参与交叉熵 loss；
7. 超长裁剪必须保持 assistant 工具调用和对应 tool 结果完整。

这是一种框架中立的 Qwen 结构化中间格式。LLaMA-Factory、ms-swift、TRL 对字段名和 completion-only collator 的要求不完全相同；确定训练框架后还需要一个很薄的 dataloader/format adapter，但不应重新破坏这里保存的 tool-call 语义。

Qwen 官方参考：

- https://github.com/QwenLM/Qwen3/blob/main/docs/source/getting_started/concepts.md
- https://github.com/QwenLM/Qwen3/blob/main/docs/source/framework/function_call.md
- https://huggingface.co/Qwen/Qwen3-8B

## 7. 规范化与裁剪规则

### thinking 与 system

- 删除 1,155 个 source `thinking` 块，共 2,721,501 字符；
- 不保留 `reasoning_content`；
- 保留可见 assistant 文本、工具调用和最终答复；
- 用统一中文 EI 工具智能体 system prompt 替换 7 条轨迹中与 DeepSeek/原 harness/临时环境绑定的 system 内容。

本批数据训练可观察行为，不训练隐藏思维链。以后若需要训练显式规划，应另建人工审核的短规划字段，而不是恢复原始 thinking。

### 工具消息

- `tool_use` 转成 assistant 的 `tool_calls`；
- function `arguments` 保证为 JSON object；
- `tool_result` 转成 `role=tool`；
- 保留 `tool_call_id`、工具名、成功/错误状态和结果正文；
- 验证器要求 tool 结果只能引用此前出现的调用，调用 ID 不能重复。

共保留 1,813 个工具调用和 1,813 个工具结果，观测到 11 种工具。

### 路径和超长内容

- 将原运行时 `/workspace` 和随机 session 路径相对化；
- 根 user 内容上限 16,000 字符；
- 单工具结果上限 10,000 字符；
- 超限工具结果保留头尾，并加入省略字符数及原文 SHA-256 摘要；
- 决策 prompt 消息预算 24,000 字符；
- 从最近历史向前按完整 assistant-tool 块选择，不从调用与结果之间硬切；
- 单 completion 上限 16,000 字符。

本次截断 44 个工具结果，共省略 385,440 字符；没有 completion 被拒绝。1,596/1,627 个决策样本发生历史窗口截断，说明原轨迹非常长，因此精确 token 长度检查尤其重要。

## 8. 数据统计

标签可以重叠，只作为审计 metadata，不是额外训练目标：

- 含工具调用的 assistant 决策：1,620；
- 含可见 assistant 文本：546；
- 验证行为启发式命中：415；
- 紧跟失败工具结果后的恢复决策：54；
- 每条轨迹最后的最终答复：7。

验证标签只匹配独立的 `verify/validate/validation/check/test/pytest/unittest` 等词或中文“验收/校验/核对”，不会把任务编号 `TESTPK` 误算成验证行为。

字符长度：

| 项目 | min | p50 | p95 | max |
|---|---:|---:|---:|---:|
| prompt | 6,072 | 23,825 | 23,987 | 24,000 |
| completion | 152 | 446 | 2,150 | 14,132 |

详细按 family、目标工具、标签、长度和轨迹统计见 `manifest.json`。

## 9. 轨迹权重

每个样本都带有：

`trajectory_sample_weight = 1 / 该原始轨迹的决策样本数`

如果训练器应用该权重，每条原始轨迹的理论总权重约为 1，可避免 455 步轨迹单纯因为更长而压过 130 步轨迹。普通训练器通常会忽略未知 metadata，因此该权重不会自动生效；是否使用必须在训练代码、sampler 或 loss 中显式实现并做消融实验。

## 10. 工具 schema 的限制

原始轨迹顶层没有正式工具 JSON Schema。因此 `tools.inferred.json` 是从 7 条高 O2 轨迹的实际调用参数归纳出的结构，不是生产运行时契约。

正式训练/部署前必须核对：

- 工具名称与大小写；
- 必填参数；
- 参数类型和枚举；
- tool-call ID 协议；
- tool 返回格式和错误状态。

当前 5 折共享同一个全局工具 schema，把工具表视为环境能力。由于 schema 的字段是从全部 7 条轨迹推断的，严格研究报告中应披露这一点；取得正式 runtime schema 后应替换推断版本。

## 11. 验证结果和 tokenizer 状态

结构验证命令：

```bash
cd /root/autodl-tmp/workspace-tw/data/2026-09-08
PYTHONDONTWRITEBYTECODE=1 /root/miniconda3/bin/python scripts/validate_dataset.py
```

结构验收覆盖：

- JSONL 逐行解析与 ID 唯一；
- 7 条完整轨迹和 1,627 个 canonical 决策样本；
- 5 折 family 隔离；
- 每个 family 恰好验证一次、训练四次；
- 每折 train+validation 完整覆盖 canonical 且无重复；
- prompt/system/user 与单 assistant completion 结构；
- thinking/reasoning 泄漏；
- 工具名、arguments、call ID 和 tool-result 引用；
- 字符预算和 metadata 计数；
- 每折 rollout 任务只来自 holdout family；
- manifest 中全部输出文件 SHA-256。

最终结果必须为 `PASS`。

远端已有完整模型目录 `/root/autodl-tmp/models/Qwen3-8B`，约 16G，包含 config、tokenizer 和五个 safetensors 分片；但当前 `/root/miniconda3` 环境没有安装 `transformers` 和 `tokenizers`，因此本次没有完成精确 Qwen token 长度检查，也不会为了验证擅自安装或下载。

训练环境准备好依赖后可执行：

```bash
/root/miniconda3/bin/python scripts/validate_dataset.py \
  --model /root/autodl-tmp/models/Qwen3-8B \
  --max-length 16384
```

验证器设置 `local_files_only=True`，不会联网下载。实际 `max-length` 应替换为最终训练配置。

## 12. 复现

在本日期目录执行：

```bash
PYTHONDONTWRITEBYTECODE=1 /root/miniconda3/bin/python scripts/convert_trajectories.py
PYTHONDONTWRITEBYTECODE=1 /root/miniconda3/bin/python scripts/validate_dataset.py
```

`scripts/convert_trajectories.py` 固定检查：

- 输出解析后必须位于 `/root/autodl-tmp/workspace-tw`；
- 源数据只读自 `/root/autodl-tmp/data/raw_data`；
- 7 条 trajectory 和 score 必须各自唯一；
- O2 必须从真实 score 聚合字段读取。

`manifest.json` 记录源 trajectory/score、rules.md 和所有输出文件的 SHA-256。

## 13. 训练前仍需决定

- 最终基座是否确为 `Qwen/Qwen3-8B`；
- 采用 LLaMA-Factory、ms-swift、TRL 还是自研训练器；
- 正式工具 schema；
- 实际 max sequence length；
- 是否启用轨迹归一权重；
- 决策级验证与端到端 rollout 的具体指标；
- 5 个 family、7 条轨迹仍然很少，交叉验证减少了划分偏差，但不能消除小样本方差；
- O2 是整轨质量信号，不保证每个局部动作都是唯一最优，重要恢复与验证步骤仍建议抽样人工检查。

## 14. 本次重要改进

- 将实际输出从本地改为远端 `/root/autodl-tmp/workspace-tw/data/2026-09-08`；
- 修正外层 README 中过时的原始数据路径；
- 从远端 score 文件重新读取 O2、ruleset、路径和 SHA-256；
- 从固定单一划分升级为 5-fold task-family grouped cross-validation；
- 每折生成独立、可直接读取的 train/validation/rollout 文件和说明；
- 指定 `fold_05_holdout_0010` 为推荐单次退化划分；
- 同时保存一轨迹一行的审计数据与一决策一行的训练数据；
- 删除 source thinking，规范化 Qwen function calling，实施 completion-only loss 边界；
- 增加按族分片、逐轨权重、裁剪摘要、工具/标签/长度统计和完整 SHA-256 验证。
