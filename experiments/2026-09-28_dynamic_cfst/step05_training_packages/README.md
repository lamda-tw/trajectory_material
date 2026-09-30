# CFST 第5步：三个最小训练包

本步已经完成数据准备，**没有训练模型**。20条数据全部来自来源60题中经过“干净前缀重放 → 教师替换一个动作 → 原Qwen3-8B LoRA续跑 → 官方评分成功”验证的修复。检查30题和Dev57没有生成教师答案，也没有进入训练包。

## 生成结果

| 训练包 | 唯一数据 | 任务族 | 一轮输入tokens | 一轮监督tokens | 最长样本 |
| --- | ---: | ---: | ---: | ---: | ---: |
| CFST-state | 12条状态构建 | 8 | 99,928 | 1,826 | 11,256 |
| CFST-Action | 8条动作落地 | 6 | 98,182 | 1,493 | 22,193 |
| CFST-Mixed | 全部20条 | 12 | 198,110 | 3,319 | 22,193 |

这里的“一轮监督tokens”只计算教师修复答案。三个JSONL都只保存唯一数据，没有为了凑8,000 tokens提前复制样本。第6步训练时再按固定顺序循环各包，记录实际重复次数、更新步数和监督token数，使三个分支使用相同预算。

旧标签到新能力的转换如下：

- 原12条“状态错误”变为12条“状态构建”。
- 原7条“参数错误”变为7条“动作落地”。
- `6104387_3` 原来标为“恢复错误”，实际教师修复的是CSV构造和写入，所以成为第8条“动作落地”；“错误反馈后”和“CSV格式”仍保留为次要标签。

## 一条数据究竟训练什么

每行都沿用项目已有的Qwen completion-only格式：

```text
prompt：替换动作之前，学生当时真正看见的全部消息；环境凭证已脱敏
completion：教师的可见推理 + 一个经过最终官方成功验证的Python替代动作
```

训练脚本将 `prompt` 的全部label设为 `-100`，因此前面的任务要求、历史动作和环境反馈只作为条件，不计算损失。只有 `completion` 的assistant tokens计算损失。原错误动作、教师动作之后的学生续跑、官方失败条件、评估断言和ground truth都不在训练目标中。

## 固定顺序

先按冻结20条的原始顺序，用 `random.Random(20260928).shuffle` 生成一个全局顺序。Mixed直接使用该顺序；State和Action从同一全局顺序过滤得到，所以相同样本在三个包之间的相对顺序一致。

检查30题若多个分支完全并列，训练前冻结的顺序为：`CFST-state → CFST-Action → CFST-Mixed`。这只用于第7步的最终并列裁决，不能根据结果修改。

## 核验结果

独立验证共通过472项检查：

- State/Action各自不重叠，合并后与Mixed的20条完全一致；
- 12/8标签数量正确，20个任务ID均来自来源60题；
- 检查30题和Dev57教师答案均为0；
- 40条序列化记录逐条通过Qwen3聊天模板前缀检查；
- 40条记录逐条确认输入全部mask、修复答案全部参与loss；
- 最长样本22,193 tokens，全部低于40,960，无前缀截断；
- 20条均保留官方成功、前缀重放成功、教师输入边界干净和教师动作哈希。

## 文件说明

| 文件 | 用途 |
| --- | --- |
| `CFST-state/train.jsonl` | 12条状态构建训练数据 |
| `CFST-Action/train.jsonl` | 8条动作落地训练数据 |
| `CFST-Mixed/train.jsonl` | 全部20条混合训练数据 |
| `label_conversion.csv` / `.jsonl` | 20条旧标签到新能力的逐条转换与证据路径 |
| `package_stats.json` | 每包样本、任务族、输入与监督token统计 |
| `loss_mask_checks.jsonl` | 40条序列化记录的真实token和loss mask检查结果 |
| `manifest.json` | 来源边界、随机顺序、训练契约、包哈希与并列顺序 |
| `validation.json` | 472项一致性检查及结论 |
| `artifact_sha256.json` | 12个核心产物的SHA-256 |
| `prepare_step05.py` / `validate_step05.py` | 可复现的生成与独立验证脚本 |

复现命令：

```bash
.conda-training/bin/python experiments/2026-09-28_dynamic_cfst/step05_training_packages/prepare_step05.py
.conda-training/bin/python experiments/2026-09-28_dynamic_cfst/step05_training_packages/validate_step05.py
```

下一步是从同一个 **Qwen3-8B + train90 LoRA第5轮adapter** 分别训练State、Action、Mixed三个LoRA分支。本目录只冻结训练输入，不包含新adapter。
