# AppWorld 67 任务 Qwen3-8B LoRA 五轮训练报告

## 1. 结论

本实验已完成累计 **5 个 epoch** 的 LoRA 微调，最终状态为 **SUCCESS**。训练使用全部
67 个已通过官方 evaluator 和干净环境 replay 的 AppWorld train 任务，共 640 个
completion-only 决策样本。每个 epoch 由双卡 DDP 完成 320 次同步参数更新，总计 1,600 步。

最终模型由原始基座 `/root/autodl-tmp/models/Qwen3-8B` 和以下 LoRA adapter 组成：

`/root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/artifacts/continuation/adapter_epoch5`

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
- 被截断训练样本：0
- 可训练参数：21,823,488 / 8,212,558,848
  （0.2657%）
- 累计训练与诊断验证用时：5080.22 秒

## 4. Loss 变化

| epoch | 优化步数 | 平均 loss | 前 20 步平均 loss | 后 20 步平均 loss |
|---:|---:|---:|---:|---:|
| 1 | 320 | 0.650503 | 0.946417 | 0.634202 |
| 2 | 320 | 0.380826 | 0.435444 | 0.370342 |
| 3 | 320 | 0.236069 | 0.220636 | 0.246289 |
| 4 | 320 | 0.150793 | 0.114325 | 0.161347 |
| 5 | 320 | 0.106259 | 0.103640 | 0.112524 |

总 loss 图位于 `metrics/loss_curve_total_5epochs.png`，同时提供 PDF 版本和原始 CSV/JSON。

- 横轴：全局 optimizer step。每一步表示两张 GPU 完成一次同步梯度更新；每个 epoch 有 320 步。
- 纵轴：completion-only token 的交叉熵 loss，数值越低表示模型对正确下一步 reasoning 和 Python action
  分配的概率越高。
- 浅蓝线：每一个同步更新步的原始 loss。
- 红线：向后 50 步的因果移动平均，用于观察总体趋势。
- 竖向虚线：五个 epoch 的分界。

## 5. 双卡使用情况

epoch 1 峰值 allocated：GPU 0 为 63.52 GiB，GPU 1 为
66.04 GiB。epoch 2–5 峰值 allocated：GPU 0 为
66.04 GiB，GPU 1 为 65.58 GiB。
完整时间序列分别保存在 `logs/gpu_usage.csv` 和 `logs/gpu_usage_epochs2_5.csv`。

## 6. 诊断验证与 adapter 重载

- epoch 5 后诊断 loss：0.085363
- epoch 5 后诊断 perplexity：1.089112
- adapter 重载与生成状态：PASS
- 生成的非空 Python 代码块数量：1
- 最终 adapter SHA-256：`bc23973cae22ce9db1c28f3869201b10b9e665a2d4b3f5639f988d2658611aa4`

诊断数据的 7 个任务也包含在 67 任务全量训练集中，因此该 loss 只用于检查数值和管线状态，不能作为
泛化指标。模型效果必须由独立的 AppWorld Dev 官方 evaluator 判断。

## 7. AppWorld Dev 就绪状态

`scripts/run_appworld_qwen3_react_lora_full_dev.sh` 已支持用 vLLM 加载基座和本次 LoRA adapter。
具体命令保存在 `DEV_EVAL_READY_EPOCH5.md`。本次续训不会自动运行 57 题 Dev 评测。
