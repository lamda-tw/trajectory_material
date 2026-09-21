#!/usr/bin/env python3
"""Build the final Chinese report for the Codex-RFT LoRA run."""

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
    return sum(values) / len(values) if values else 0.0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-dir", type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment_dir.resolve()
    config = json.loads((exp / "config" / "training_config.json").read_text(encoding="utf-8"))
    metrics = json.loads((exp / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    probe = json.loads((exp / "probe" / "artifacts" / "metrics.json").read_text(encoding="utf-8"))
    generation = json.loads((exp / "metrics" / "generation_smoke.json").read_text(encoding="utf-8"))
    history = metrics["training"]["history"]
    losses = [float(row["train_loss"]) for row in history]
    first = mean(losses[:50])
    last = mean(losses[-50:])
    ranks = metrics["distributed"]["ranks"]
    train = metrics["data"]["train"]
    validation = metrics["validation"]
    adapter_model = exp / "artifacts" / "adapter" / "adapter_model.safetensors"
    source = config["source_guards"]
    lengths = config["token_lengths"]
    completions = config["completion_lengths"]
    difficulty = config["difficulty"]

    report = f"""# AppWorld Codex-RFT train90：Qwen3-8B LoRA 微调报告

## 1. 结论

本次训练状态为 **{metrics['status']}**。Qwen3-8B 已在全部 {config['train_tasks']} 个 AppWorld
train 任务、{config['train_trajectories']} 条 Codex 成功轨迹转换得到的
{config['train_decision_samples']} 条决策级样本上完成 5 个连续 epoch 的 completion-only LoRA SFT。
两张 GPU 均参与 NCCL/DDP，同步更新 {metrics['training']['global_steps']} 步；保存后的 adapter
已从磁盘重新加载并通过单样本 ReAct Python 生成检查。

最终 adapter：`{exp / 'artifacts' / 'adapter'}`

## 2. 数据边界与训练契约

- 数据目录：`{config['dataset_dir']}`
- 原始 `train.jsonl` SHA-256：`{config['train_sha256']}`
- 官方 evaluator 成功任务：{source.get('official_evaluator_success_tasks')} / {config['train_tasks']}
- 独立 Codex thread：{source.get('unique_codex_threads')}
- 难度 1/2/3：{difficulty.get('1', difficulty.get(1))} / {difficulty.get('2', difficulty.get(2))} / {difficulty.get('3', difficulty.get(3))}
- raw observation 进入训练：{source.get('raw_observations_included')}
- ground truth 进入模型消息：{source.get('ground_truth_in_model_messages')}
- 敏感值泄漏：{source.get('sensitive_value_leaks')}
- loss：只监督当前 assistant completion；prompt 与 padding label 均为 `-100`
- Qwen chat template：`enable_thinking=False`

训练输入长度（token）为 min={lengths['min']}、p50={lengths['p50']}、p95={lengths['p95']}、
max={lengths['max']}、mean={lengths['mean']:.2f}；completion 长度为 min={completions['min']}、
p50={completions['p50']}、p95={completions['p95']}、max={completions['max']}、
mean={completions['mean']:.2f}。共有 {lengths['over_32768']} 条超过 32,768 token，
因此本实验使用 Qwen3-8B 原生上限 {config['max_length']}，实际截断样本为
{train['truncated_samples']} 条。

## 3. 训练配置

- 基座：`{config['base_model']}`
- LoRA：r={config['lora_r']}，alpha={config['lora_alpha']}，dropout={config['lora_dropout']}
- 注入层：q/k/v/o projection 与 gate/up/down projection
- 精度 / attention：{config['dtype']} / {config['attention']}
- 每卡 batch / 全局 batch：{config['per_gpu_batch_size']} / {config['global_batch_size']}
- optimizer：{config['optimizer']}，learning rate={config['learning_rate']}，weight decay={config['weight_decay']}
- epoch / optimizer step：{config['epochs']} / {metrics['training']['global_steps']}
- 可训练参数：{metrics['model']['trainable_parameters']:,} / {metrics['model']['total_parameters']:,}（{metrics['model']['trainable_percent']:.4f}%）
- 训练与诊断验证耗时：{metrics['training']['duration_seconds']:.2f} 秒

最长两条样本先独立执行了真实 forward/backward/update smoke，最大长度为
{config['probe_samples'][0]['tokens']} token，状态为 {probe['status']}。

## 4. Loss 与诊断

- 前 50 步平均训练 loss：{first:.6f}
- 后 50 步平均训练 loss：{last:.6f}
- 最后一步训练 loss：{losses[-1]:.6f}
- 训练内诊断 loss：{validation['loss']:.6f}
- 训练内诊断 perplexity：{validation['perplexity']:.6f}

诊断集从每个训练任务各取最后一个决策，共 {config['diagnostic_validation_samples']} 条，且它们
全部已参与训练。因此这两个诊断数值只能检查数值稳定性和拟合状态，**不能解释为 Dev 泛化性能**。
是否提升必须使用独立 AppWorld Dev 和官方 evaluator，与相同基座/推理配置的零样本及旧 adapter 对照。

## 5. 双卡与显存证据

| rank | GPU | 峰值 allocated | 峰值 reserved |
|---:|---|---:|---:|
| 0 | {ranks[0]['device_name']} | {ranks[0]['peak_allocated_gib']:.2f} GiB | {ranks[0]['peak_reserved_gib']:.2f} GiB |
| 1 | {ranks[1]['device_name']} | {ranks[1]['peak_allocated_gib']:.2f} GiB | {ranks[1]['peak_reserved_gib']:.2f} GiB |

逐秒 GPU 记录保存在 `logs/gpu_usage.csv`。

## 6. Adapter 重载检查与产物

- 重载生成状态：{generation['status']}
- 样本：`{generation['sample_id']}`
- 输入 / 生成 token：{generation['input_tokens']} / {generation['generated_tokens']}
- 非空 Python fenced code block：{generation['python_block_count']}
- adapter 权重 SHA-256：`{sha256_file(adapter_model)}`
- 完整结构化指标：`artifacts/metrics.json`
- 训练配置与数据哈希：`config/training_config.json`
- 全流程日志：`logs/`

本实验只完成训练及格式/重载验证，没有在此流程中运行 AppWorld Dev；因此报告不作准确率上升保证。
"""
    (exp / "REPORT.md").write_text(report, encoding="utf-8")
    print(exp / "REPORT.md")


if __name__ == "__main__":
    main()
