#!/usr/bin/env python3
"""Generate the Chinese FFT report."""
import argparse
import json
from pathlib import Path


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment", type=Path, required=True)
    parser.add_argument("--lora-experiment", type=Path, required=True)
    args = parser.parse_args()
    exp = args.experiment.resolve()
    cfg = load(exp / "config/training_config.json")
    met = load(exp / "metrics/metrics.json")
    probe = load(exp / "probe/metrics/metrics.json")
    loss = load(exp / "metrics/loss_summary_5epochs.json")
    gen_path = exp / "metrics/generation_smoke.json"
    gen = load(gen_path) if gen_path.exists() else {"status": "NOT_RUN", "python_block_count": 0}
    tr, model = met["training"], met["model"]
    data, val = met["data"]["train"], met["validation"]
    if met["status"] != "SUCCESS" or tr["epochs_completed"] != 5:
        raise ValueError("training is not a five-epoch success")
    if tr["global_steps"] != cfg["global_steps"] or model["trainable_percent"] != 100.0:
        raise ValueError("step or full-parameter invariant failed")
    if data["truncated_samples"] != 0 or not Path(model["final_model"]).is_dir():
        raise ValueError("data truncation or final model invariant failed")
    loss_rows = "\n".join(
        f"| {x['epoch']} | {x['steps']} | {x['mean_loss']:.6f} | {x['first_20_mean_loss']:.6f} | {x['last_20_mean_loss']:.6f} |"
        for x in loss["epoch_summaries"]
    )
    gpu_rows = "\n".join(
        f"| {x['rank']} | {x['peak_allocated_gib']:.2f} GiB | {x['peak_reserved_gib']:.2f} GiB |"
        for x in met["distributed"]["ranks"]
    )
    probe_rows = "\n".join(
        f"| {x['rank']} | {x['peak_allocated_gib']:.2f} GiB | {x['peak_reserved_gib']:.2f} GiB |"
        for x in probe["distributed"]["ranks"]
    )
    report = f"""# AppWorld Codex-RFT train90：Qwen3-8B 全参数 SFT 五轮训练报告

## 结论

本实验从原始基座 {model['source_base_model']} 独立开始，完成 5 个连续 epoch 的全参数 SFT，状态为 {met['status']}。没有加载或合并 LoRA；更新参数 {model['trainable_parameters']:,}/{model['total_parameters']:,}（100%）。

最终完整模型：{model['final_model']}。本流程没有运行 Dev 或 test_normal，模型留给后续独立评测。

## 数据与训练契约

- 90 个任务、90 条成功轨迹、{data['count']} 条决策样本；难度 1/2/3={cfg['difficulty']['1']}/{cfg['difficulty']['2']}/{cfg['difficulty']['3']}
- 输入 token min/p50/p95/max={cfg['token_lengths']['min']}/{cfg['token_lengths']['p50']}/{cfg['token_lengths']['p95']}/{cfg['token_lengths']['max']}，截断样本={data['truncated_samples']}
- train.jsonl SHA-256：{cfg['train_sha256']}
- max_length=40960、enable_thinking=False、仅 assistant completion 参与 loss
- 双卡 FSDP FULL_SHARD、BF16、SDPA、gradient checkpointing、全局 batch=2
- 序列长度超过 {cfg['activation_offload_threshold']} token 时启用 activation CPU offload，短样本保持纯 GPU 路径
- fused AdamW，峰值 LR={tr['learning_rate']:.2e}，warmup={tr['warmup_steps']} step，cosine 降至 {tr['min_learning_rate']:.2e}，梯度裁剪={tr['max_grad_norm']}
- 每轮 {cfg['steps_per_epoch']} step，总计 {tr['global_steps']} step，seed={cfg['seed']}

旧 67 题 FFT 使用 LoRA 学习率 2e-4，epoch 2/5 的 Dev 均为 0/57。本实验没有照搬，而采用低 20 倍的 1e-5 峰值学习率，并加入 warmup、cosine 衰减和梯度裁剪。是否最优仍需独立 Dev 验证。

## 最长样本门禁

正式训练前，两张卡分别对 {cfg['probe_samples'][0]['tokens']} 和 {cfg['probe_samples'][1]['tokens']} token 的最长样本完成真实 forward/backward/update，状态 {probe['status']}。

| rank | 峰值 allocated | 峰值 reserved |
|---:|---:|---:|
{probe_rows}

## 五轮 Loss

| epoch | step | 平均 loss | 前20步 | 后20步 |
|---:|---:|---:|---:|---:|
{loss_rows}

逐步数据、CSV 和 PNG/PDF 曲线位于 metrics/。训练 loss 只表示教师动作拟合，不能替代官方 evaluator。

## 资源、诊断和产物

| rank | 峰值 allocated | 峰值 reserved |
|---:|---:|---:|
{gpu_rows}

- 训练、逐轮权重导出及诊断验证耗时：{tr['elapsed_seconds']/3600:.2f} 小时
- 训练内诊断 loss/perplexity：{val['loss']:.6f}/{val['perplexity']:.6f}（诊断样本来自训练任务，不是泛化成绩）
- 最终模型重载生成检查：{gen.get('status')}；Python code block={gen.get('python_block_count')}
- epoch 1–4：artifacts/checkpoints/epoch_N_model；epoch 5：artifacts/model
- 最终权重哈希：metrics/final_model_weights.sha256

## 后续评测边界

建议先在 Dev 57 题上与同数据 LoRA 对齐 ReAct agent、输出接口、temperature、seed、步数和上下文预算，并按预先定义规则选择 checkpoint；随后再评测 test_normal。test_normal 失败轨迹、私有 evaluator 条件和状态数据不得回流训练或选模。

LoRA 对照：{args.lora_experiment.resolve()}。两者参数化和学习率不同，训练 loss 绝对值不可直接解释为端到端能力差异。
"""
    (exp / "REPORT.md").write_text(report, encoding="utf-8")
    (exp / "EVAL_READY.md").write_text(
        f"# AppWorld 后续评测准备\n\n最终全参数模型：{model['final_model']}。\n\n先评测 Dev 并确定 checkpoint，再运行 test_normal；训练内 diagnostic loss 不是泛化成绩。\n",
        encoding="utf-8",
    )
    print(report)


if __name__ == "__main__":
    main()
