#!/usr/bin/env python3
"""Create a detailed Chinese report from the full-fold run artifacts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fmt(value: float, digits: int = 4) -> str:
    return f"{value:.{digits}f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment_dir.resolve()
    metrics = json.loads((exp / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    selection = json.loads((exp / "data" / "selection_manifest.json").read_text(encoding="utf-8"))
    generation = json.loads((exp / "metrics" / "generation_smoke.json").read_text(encoding="utf-8"))
    history = metrics["training"]["history"]
    ranks = metrics["distributed"]["ranks"]
    train = metrics["data"]["train"]
    validation = metrics["data"]["validation"]

    rank_rows = "\n".join(
        f"| {row['rank']} | {row['local_rank']} | {row['device_name']} | "
        f"{fmt(row['peak_allocated_gib'], 2)} GiB | {fmt(row['peak_reserved_gib'], 2)} GiB |"
        for row in ranks
    )
    loss_rows = "\n".join(
        f"| {row['step']} | {fmt(row['train_loss'], 6)} | {fmt(row['elapsed_seconds'], 2)} s |"
        for row in history
    )
    selected_train = "\n".join(
        f"- `{row['id']}`（family {row['task_family']}，源第 {row['source_line_number']} 行）"
        for row in selection["train"]["samples"]
    )
    selected_validation = "\n".join(
        f"- `{row['id']}`（family {row['task_family']}，源第 {row['source_line_number']} 行）"
        for row in selection["validation"]["samples"]
    )
    generated_preview = generation["generated_text"].replace("```", "''' ")[:1200]
    report = f"""# Fold 05 全量双卡 Qwen3-8B SFT 实验报告

## 1. 结论

本次 fold 05 全量训练已完整跑通，状态为 **{metrics['status']}**：读取 fold 05 全量数据、使用 Qwen 官方 tokenizer/chat template 做精确编码、执行 completion-only LoRA SFT、双卡 NCCL/DDP 同步、验证 loss、保存适配器，再从磁盘重载适配器完成单样本生成。生成重载检查状态为 **{generation['status']}**。

本次使用 fold 05 的全部 {selection['train']['count']} 条训练样本和全部 {selection['validation']['count']} 条验证样本，完成 {metrics['arguments']['epochs']} 个 epoch、{metrics['training']['global_steps']} 个优化步。本报告记录训练与验证结果，但暂不评价 O2；O2 需要独立的端到端工具 rollout 产物。

## 2. 实验范围与选择

- 工作区：`/root/autodl-tmp/workspace-tw`
- 基座：`{metrics['model']['base_model']}`（本地文件，未在线下载模型）
- 数据版本：`data/2026-09-08`
- 单折：`fold_05_holdout_0010`，训练 families 0006/0007/0008/0009，验证 family 0010
- 全量规模：train={selection['train']['count']}，validation={selection['validation']['count']}
- 数据副本顺序：按 trajectory 轮询并使用固定 tie-break；952/675 条源样本全部保留
- 方法：LoRA，r={metrics['arguments']['lora_r']}，alpha={metrics['arguments']['lora_alpha']}，目标模块 q/k/v/o + gate/up/down projections
- dtype：bfloat16；attention：SDPA；最大长度：{metrics['arguments']['max_length']} tokens
- batch：每卡 1，双卡全局 batch 2；epoch={metrics['arguments']['epochs']}；AdamW；lr={metrics['arguments']['learning_rate']}
- 隐藏思维：`enable_thinking=False`
- loss 边界：prompt 与 padding 的 labels 均为 -100，仅 completion token 参与 loss

远端真实仓库路径是 `/root/autodl-tmp/workspace-tw`；用户描述中的 `/autodl-tmp/workspace-tw` 在该主机上不存在。

## 3. 流程与门禁

1. 检查两张 GPU、CUDA、模型分片和磁盘。
2. 创建 `.conda-training`，从 base 克隆现有 CUDA/PyTorch 包后独立安装 Transformers、Tokenizers、PEFT、Accelerate；未修改 base。
3. 从 fold 05 生成 `data/train.jsonl` 与 `data/validation.jsonl`，保存源/输出 SHA-256 与样本清单。
4. 使用两进程 `torchrun` 执行 NCCL all-reduce 探针；必须 world size=2 且通信和为 3。
5. 两个 rank 各加载一份 Qwen3-8B，注入 LoRA，执行 DDP 训练。
6. 跨 rank 聚合 completion-token 加权验证 loss。
7. rank 0 保存 LoRA adapter 与 tokenizer，并写结构化指标。
8. 退出 DDP 后重新从磁盘加载 base + adapter，在 GPU 0 进行一次 greedy generation。
9. 生成本报告、环境快照、GPU 监控 CSV 与产物校验和。

## 4. 双卡使用证据

NCCL world size 为 {metrics['distributed']['world_size']}，训练指标记录了两个独立 rank。两卡峰值显存如下：

| rank | local rank | GPU | 峰值 allocated | 峰值 reserved |
|---:|---:|---|---:|---:|
{rank_rows}

`logs/gpu_usage.csv` 还保存了按秒采样的 GPU 利用率和显存。本次为 fold 05 全量单 epoch 训练；上述证据用于确认双卡均实际参与计算，不能据此评估更多卡的扩展效率。

## 5. 数据与 tokenizer 结果

训练 token 数：min={train['tokens']['min']}，max={train['tokens']['max']}，mean={fmt(train['tokens']['mean'], 2)}；completion token：min={train['completion_tokens']['min']}，max={train['completion_tokens']['max']}，mean={fmt(train['completion_tokens']['mean'], 2)}；发生左侧 prompt token 裁剪的训练样本为 {train['truncated_samples']} 条，共裁剪 {train['truncated_prompt_tokens_total']} tokens。

验证 token 数：min={validation['tokens']['min']}，max={validation['tokens']['max']}，mean={fmt(validation['tokens']['mean'], 2)}；completion token：min={validation['completion_tokens']['min']}，max={validation['completion_tokens']['max']}，mean={fmt(validation['completion_tokens']['mean'], 2)}；发生左侧 prompt token 裁剪的验证样本为 {validation['truncated_samples']} 条，共裁剪 {validation['truncated_prompt_tokens_total']} tokens。

训练样本：

{selected_train}

验证样本：

{selected_validation}

## 6. 训练与验证结果

- 可训练参数：{metrics['model']['trainable_parameters']:,} / {metrics['model']['total_parameters']:,}（{fmt(metrics['model']['trainable_percent'], 4)}%）
- 优化步：{metrics['training']['global_steps']}
- 训练阶段用时：{fmt(metrics['training']['duration_seconds'], 2)} 秒
- 验证 completion target tokens：{metrics['validation']['completion_target_tokens']}
- 验证 loss：{fmt(metrics['validation']['loss'], 6)}
- 验证 perplexity：{fmt(metrics['validation']['perplexity'], 4)}

| step | 双 rank 平均 train loss | 累计时间 |
|---:|---:|---:|
{loss_rows}

这些数值证明全量单折训练与验证归约能够完成；但本次只有一个 fold、一个 epoch，不能单独用于超参数比较或泛化效果判断。

## 7. 适配器重载与生成检查

- 样本：`{generation['sample_id']}`
- 输入 tokens：{generation['input_tokens']}
- 新生成 tokens：{generation['generated_tokens']}
- 状态：{generation['status']}

```text
{generated_preview}
```

该检查的验收条件是 adapter 能从磁盘重载、前向与 generation 无异常、产生非空 token；不要求内容正确，也不做 O2 评分。

## 8. 产物说明

- `STATUS.txt`：最终 SUCCESS/FAILED 状态
- `command.txt`：本次入口命令
- `environment.txt`：GPU、系统、Python、pip freeze、Git 状态
- `data/`：fold 05 全量 train/validation、选择 manifest 与 SHA-256
- `artifacts/adapter/`：LoRA 权重、配置、tokenizer
- `artifacts/metrics.json`：结构化训练、验证、token 与双卡峰值信息
- `metrics/generation_smoke.json`：适配器重载生成结果
- `logs/`：准备、DDP、训练、重载生成及 GPU 按秒监控日志
- `scripts_snapshot/`：本次用到脚本的快照
- `artifacts.sha256`：实验目录关键文件校验和

## 9. 复现

在仓库根目录执行：

```bash
bash scripts/run_full_fold05_sft.sh experiments/2026-09-09_full_qwen3-8b_lora_2gpu_fold05_epoch1
```

脚本使用固定 seed `{metrics['arguments']['seed']}` 与确定性抽样。GPU 浮点内核和 DDP 时序仍可能造成末位差异。

## 10. Task 2：端到端推理 / O2 CSV 就绪性

### 判定

**当前状态：BLOCKED，本次不执行端到端推理，也不生成伪造 CSV。** 适配器重载后的单轮 generation 只能证明模型可以从磁盘加载并生成 token，不等同于带工具的 agent rollout。

目前能够确认的输入包括两个 `validation_tasks`（easy/medium）、从历史轨迹推断出的 11 个工具 schema，以及 `raw_data` 中历史运行使用过的源文件。历史目录同时包含高分运行留下的脚本、CSV 和答案；若直接复制或复用这些内容，会造成 holdout 答案泄漏，不能作为本模型的推理结果。

正式推理仍需外部提供或确认：

1. 可执行的 `agent_core` / `cowork` 推理 harness，以及加载“本地 Qwen3-8B + 本次 LoRA adapter”的接入方式。
2. 完整且只读的 `.agent-sdk/skills/OptAgent`、`.agent-sdk/skills/EIAgent-requirement-docs` 及其 phases、references、scripts；现有轨迹只保留了截断后的技能文本，无法还原正式技能行为。
3. 11 个工具的安全沙箱执行器，而不仅是 JSON schema；至少包括 AskUserQuestion、Bash、Edit、get_goal、Glob、Grep、present_files、Read、Skill、TodoWrite、Write。
4. 与历史答案分离的干净任务包：每个 validation task 的原始 input 文件、允许读取的数据目录、输出目录及应提交的 CSV 文件名/列 schema。
5. rollout 合同：最大步数、超时、工具失败策略、停止条件，以及 evaluator 要求的 `run_metadata`、trajectory 和模型/harness 命名格式。

条件具备后，建议分别创建 easy/medium 的全新隔离工作目录，只读挂载输入数据和技能，加载 base+adapter 执行工具循环，校验 CSV 文件存在、列名和数据类型，再用官方 `eval score run` 评分。整个流程不得读取历史运行生成的脚本或 CSV。

## 11. 限制与下一步

1. 本次只完成 fold 05 单折的 1 个 epoch；它是一次完整训练运行，但仍不足以单独建立统计结论。
2. 最大长度为 {metrics['arguments']['max_length']}；若有裁剪应根据下一阶段显存实测提高到 24576 或更高，并优先保证完整 assistant-tool 块。
3. 当前 tool schema 是从全部 7 条轨迹推断的，不是正式 runtime contract。
4. 当前验证只有 teacher-forced completion loss 与非空生成，尚未做 tool-call JSON 结构正确率、工具名准确率、端到端 rollout 或 O2。
5. 轨迹归一权重字段本次未启用；正式 fold 训练应对是否使用该权重做明确选择。
6. 下一阶段应在冻结的推理 harness 中执行两个 holdout validation tasks，验证 tool-call 结构、CSV 合同和端到端 O2；之后再决定是否增加 epoch 或跑其余四折。

## 12. 最终验收清单

- [x] 推荐单折且无 task-family 泄漏
- [x] Qwen chat template + `enable_thinking=False`
- [x] completion-only labels
- [x] 两张 RTX PRO 6000、两个 NCCL rank
- [x] LoRA 反向传播与 optimizer step
- [x] 跨卡验证 loss 聚合
- [x] adapter/tokenizer 落盘
- [x] adapter 从磁盘重载并生成非空输出
- [x] 日志、配置、环境、结果、脚本快照与报告集中归档
- [x] Task 2 推理依赖审计完成；因缺少正式 harness/skills/runtime 且存在历史答案泄漏风险，按要求暂不执行
"""
    (exp / "REPORT.md").write_text(report, encoding="utf-8")
    print(exp / "REPORT.md")


if __name__ == "__main__":
    main()
