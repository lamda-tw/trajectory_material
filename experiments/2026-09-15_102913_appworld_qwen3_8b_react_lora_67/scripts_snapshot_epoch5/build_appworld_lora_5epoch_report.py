#!/usr/bin/env python3
"""Build the final Chinese report for the cumulative five-epoch run."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment_dir.resolve()
    first = json.loads((exp / "artifacts" / "metrics_epoch1.json").read_text(encoding="utf-8"))
    continued = json.loads(
        (exp / "artifacts" / "continuation" / "metrics_epochs2_5.json").read_text(encoding="utf-8")
    )
    generation = json.loads((exp / "metrics" / "generation_smoke_epoch5.json").read_text(encoding="utf-8"))
    history = first["training"]["history"] + continued["training"]["history"]
    by_epoch: dict[int, list[float]] = {}
    for row in history:
        by_epoch.setdefault(int(row["epoch"]), []).append(float(row["train_loss"]))
    epoch_rows = "\n".join(
        f"| {epoch} | {len(losses)} | {mean(losses):.6f} | {mean(losses[:20]):.6f} | {mean(losses[-20:]):.6f} |"
        for epoch, losses in sorted(by_epoch.items())
    )
    ranks1 = first["distributed"]["ranks"]
    ranks2 = continued["distributed"]["ranks"]
    final_adapter = exp / "artifacts" / "continuation" / "adapter_epoch5"
    adapter_file = final_adapter / "adapter_model.safetensors"
    total_duration = float(first["training"]["duration_seconds"]) + float(
        continued["training"]["duration_seconds"]
    )
    report = f"""# AppWorld 67 任务 Qwen3-8B LoRA 五轮训练报告

## 1. 结论

本实验已完成累计 **5 个 epoch** 的 LoRA 微调，最终状态为 **{continued['status']}**。训练使用全部
67 个已通过官方 evaluator 和干净环境 replay 的 AppWorld train 任务，共 640 个
completion-only 决策样本。每个 epoch 由双卡 DDP 完成 320 次同步参数更新，总计 1,600 步。

最终模型由原始基座 `/root/autodl-tmp/models/Qwen3-8B` 和以下 LoRA adapter 组成：

`{final_adapter}`

## 2. 续训边界说明

第 1 个 epoch 的 adapter 被完整保留在 `artifacts/adapter_epoch1`，原始指标保存在
`artifacts/metrics_epoch1.json`。epoch 2–5 从该 adapter 连续加载模型权重，因此 LoRA 权重是连续的。

第 1 轮训练脚本没有保存 AdamW optimizer state，所以 epoch 2 开始时重新初始化了 AdamW。
学习率仍为 0.0002，weight decay 仍为 0，LoRA r=8、alpha=16、目标层、随机种子、数据、batch、
BF16、SDPA 和 32,768-token 上下文设置均保持一致。这个边界等价于从 epoch 1 权重继续训练四轮，
但不等价于 optimizer 动量无中断的单次五轮运行。

## 3. 训练设置

- 每卡 batch：1；双卡全局 batch：2
- loss：仅 assistant completion token 参与，prompt 和 padding 的 label 为 -100
- `enable_thinking=False`
- 最大上下文：32,768 tokens
- 被截断训练样本：{continued['data']['train']['truncated_samples']}
- 可训练参数：{continued['model']['trainable_parameters']:,} / {continued['model']['total_parameters']:,}
  （{continued['model']['trainable_percent']:.4f}%）
- 累计训练与诊断验证用时：{total_duration:.2f} 秒

## 4. Loss 变化

| epoch | 优化步数 | 平均 loss | 前 20 步平均 loss | 后 20 步平均 loss |
|---:|---:|---:|---:|---:|
{epoch_rows}

总 loss 图位于 `metrics/loss_curve_total_5epochs.png`，同时提供 PDF 版本和原始 CSV/JSON。

- 横轴：全局 optimizer step。每一步表示两张 GPU 完成一次同步梯度更新；每个 epoch 有 320 步。
- 纵轴：completion-only token 的交叉熵 loss，数值越低表示模型对正确下一步 reasoning 和 Python action
  分配的概率越高。
- 浅蓝线：每一个同步更新步的原始 loss。
- 红线：向后 50 步的因果移动平均，用于观察总体趋势。
- 竖向虚线：五个 epoch 的分界。

## 5. 双卡使用情况

epoch 1 峰值 allocated：GPU 0 为 {ranks1[0]['peak_allocated_gib']:.2f} GiB，GPU 1 为
{ranks1[1]['peak_allocated_gib']:.2f} GiB。epoch 2–5 峰值 allocated：GPU 0 为
{ranks2[0]['peak_allocated_gib']:.2f} GiB，GPU 1 为 {ranks2[1]['peak_allocated_gib']:.2f} GiB。
完整时间序列分别保存在 `logs/gpu_usage.csv` 和 `logs/gpu_usage_epochs2_5.csv`。

## 6. 诊断验证与 adapter 重载

- epoch 5 后诊断 loss：{continued['validation']['loss']:.6f}
- epoch 5 后诊断 perplexity：{continued['validation']['perplexity']:.6f}
- adapter 重载与生成状态：{generation['status']}
- 生成的非空 Python 代码块数量：{generation['python_block_count']}
- 最终 adapter SHA-256：`{sha256_file(adapter_file)}`

诊断数据的 7 个任务也包含在 67 任务全量训练集中，因此该 loss 只用于检查数值和管线状态，不能作为
泛化指标。模型效果必须由独立的 AppWorld Dev 官方 evaluator 判断。

## 7. AppWorld Dev 就绪状态

`scripts/run_appworld_qwen3_react_lora_full_dev.sh` 已支持用 vLLM 加载基座和本次 LoRA adapter。
具体命令保存在 `DEV_EVAL_READY_EPOCH5.md`。本次续训不会自动运行 57 题 Dev 评测。
"""
    (exp / "REPORT.md").write_text(report, encoding="utf-8")
    dev = f"""# AppWorld Dev 五轮 LoRA 评测入口

最终 adapter：`{final_adapter}`

```bash
cd /root/autodl-tmp/workspace-tw
EVAL_EXPERIMENT="/root/autodl-tmp/workspace-tw/experiments/$(date +%Y-%m-%d_%H%M%S)_appworld_qwen3-8b_react_lora_full_dev"
bash scripts/run_appworld_qwen3_react_lora_full_dev.sh \\
  "$EVAL_EXPERIMENT" \\
  {final_adapter}
```

该命令使用官方 57 题 Dev split 和 evaluator。本训练任务未自动启动 Dev 评测。
"""
    (exp / "DEV_EVAL_READY_EPOCH5.md").write_text(dev, encoding="utf-8")
    print(exp / "REPORT.md")


if __name__ == "__main__":
    main()
