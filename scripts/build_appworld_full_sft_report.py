#!/usr/bin/env python3
"""Build the final Chinese report for the five-epoch full-SFT experiment."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def fmt(value: float) -> str:
    return f"{value:.6f}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--lora-experiment", type=Path, required=True)
    args = parser.parse_args()

    experiment = args.experiment.resolve()
    metrics = json.loads((experiment / "metrics" / "metrics.json").read_text(encoding="utf-8"))
    loss_summary = json.loads(
        (experiment / "metrics" / "loss_summary_5epochs.json").read_text(encoding="utf-8")
    )
    generation_path = experiment / "metrics" / "generation_smoke.json"
    generation = json.loads(generation_path.read_text(encoding="utf-8"))
    model = metrics["model"]
    training = metrics["training"]
    train_data = metrics["data"]["train"]
    validation = metrics["validation"]
    ranks = metrics["distributed"]["ranks"]

    table_rows = []
    for row in loss_summary["epoch_summaries"]:
        table_rows.append(
            f"| {row['epoch']} | {row['steps']} | {fmt(row['mean_loss'])} | "
            f"{fmt(row['first_20_mean_loss'])} | {fmt(row['last_20_mean_loss'])} |"
        )

    gpu_lines = []
    for row in ranks:
        gpu_lines.append(
            f"- GPU {row['local_rank']}：峰值 allocated {row['peak_allocated_gib']:.2f} GiB，"
            f"峰值 reserved {row['peak_reserved_gib']:.2f} GiB"
        )

    report = f"""# AppWorld 67 任务 Qwen3-8B 全参数 SFT 五轮训练报告

## 1. 结论

本实验从原始基座 `{model['source_base_model']}` 独立开始，已完成累计 **5 个 epoch** 的
全参数 SFT，最终状态为 **{metrics['status']}**。没有加载、合并或继续训练任何 LoRA adapter。

最终 Hugging Face 模型目录：

`{model['final_model']}`

该目录包含完整模型权重、配置和 tokenizer，可以作为独立模型被 Transformers 或 vLLM 加载。

## 2. 与 LoRA 对照实验的一致性

LoRA 对照实验位于 `{args.lora_experiment.resolve()}`。两组实验均使用：

- 同一原始 Qwen3-8B 基座；
- 同一份 67 任务数据，共 {train_data['count']} 个决策级训练样本；
- 5 个 epoch，每轮 320 个双卡同步更新，总计 {training['global_steps']} 步；
- 每卡 batch 1、全局 batch 2、gradient accumulation 1；
- AdamW，学习率 {training['learning_rate']}，weight decay {training['weight_decay']}；
- BF16、SDPA、gradient checkpointing；
- 最大上下文 {training['max_length']:,} tokens，`enable_thinking=False`；
- 仅 assistant completion token 参与 loss；
- 相同随机种子和 DistributedSampler 数据顺序。

核心实验变量是参数更新方式：LoRA 只训练 21,823,488 个低秩参数；本实验训练
{model['trainable_parameters']:,} / {model['total_parameters']:,} 个参数，即 100%。为容纳完整参数、
梯度和 AdamW 状态，本实验使用双卡 FSDP FULL_SHARD；这只改变状态的存放与通信方式，不改变
训练目标或全局 batch。

## 3. 数据与长度

- 训练任务：67 个
- 决策样本：{train_data['count']}
- 最短/最长输入：{train_data['tokens']['min']:,} / {train_data['tokens']['max']:,} tokens
- 截断样本：{train_data['truncated_samples']}
- completion-only 监督，无 prompt token loss

## 4. Loss 变化

| epoch | 优化步数 | 平均 loss | 前 20 步平均 loss | 后 20 步平均 loss |
|---:|---:|---:|---:|---:|
{chr(10).join(table_rows)}

总 loss 图位于 `metrics/loss_curve_total_5epochs.png`，同时提供 PDF 和原始 CSV/JSON 数据。

- 横轴：全局 optimizer step。每一步表示两张 GPU 完成一次同步梯度更新；每个 epoch 320 步。
- 纵轴：completion-only token 的交叉熵 loss，越低表示模型对教师轨迹中正确下一步文本分配的概率越高。
- 浅蓝线：每个同步更新步的原始 loss。
- 红线：向后 50 步的因果移动平均。
- 竖向虚线：五个 epoch 的边界。

## 5. 双卡 FSDP 与资源

{chr(10).join(gpu_lines)}

训练、逐轮完整权重导出和诊断验证总用时 {training['elapsed_seconds'] / 60:.2f} 分钟。
epoch 1–4 的完整模型检查点保存在 `artifacts/checkpoints`，最终 epoch 5 模型保存在
`artifacts/model`。

## 6. 诊断验证和模型重载

- 诊断 loss：{fmt(validation['loss'])}
- 诊断 perplexity：{fmt(validation['perplexity'])}
- 完整模型重载与生成状态：{generation['status']}
- 生成的非空 Python 代码块数量：{generation['python_block_count']}

诊断数据的 7 个任务也包含在 67 任务全量训练集中，因此此处 loss 只用于检查数值和训练管线，
不能作为泛化指标。模型能力必须由独立的 AppWorld Dev 官方 evaluator 判断。

## 7. AppWorld Dev 就绪状态

`scripts/run_appworld_qwen3_react_full_sft_full_dev.sh` 可使用 vLLM 直接加载本实验完整模型。
具体命令保存在 `DEV_EVAL_READY.md`。本次训练不会自动运行 57 题 Dev 评测。
"""
    (experiment / "REPORT.md").write_text(report, encoding="utf-8")

    dev = f"""# AppWorld Dev 评测准备

最终全参数 SFT 模型：

`{model['final_model']}`

建议创建独立 Dev 实验目录后执行：

```bash
cd /root/autodl-tmp/workspace-tw
EVAL_DIR=/root/autodl-tmp/workspace-tw/experiments/$(date +%Y-%m-%d_%H%M%S)_appworld_qwen3-8b_react_full_sft_full_dev
bash scripts/run_appworld_qwen3_react_full_sft_full_dev.sh "$EVAL_DIR" "{model['final_model']}"
```

该命令会运行 AppWorld Dev 官方 evaluator；不要把本训练实验中的诊断 loss 当作 Dev 成绩。
"""
    (experiment / "DEV_EVAL_READY.md").write_text(dev, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
