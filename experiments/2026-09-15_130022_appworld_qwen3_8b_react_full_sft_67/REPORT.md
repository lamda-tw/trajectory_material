# AppWorld 67 任务 Qwen3-8B 全参数 SFT 五轮训练报告

## 1. 结论

本实验从原始基座 `/root/autodl-tmp/models/Qwen3-8B` 独立开始，已完成累计 **5 个 epoch** 的
全参数 SFT，最终状态为 **SUCCESS**。没有加载、合并或继续训练任何 LoRA adapter。

最终 Hugging Face 模型目录：

`/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/artifacts/model`

该目录包含完整模型权重、配置和 tokenizer，可以作为独立模型被 Transformers 或 vLLM 加载。

## 2. 与 LoRA 对照实验的一致性

LoRA 对照实验位于 `/root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67`。两组实验均使用：

- 同一原始 Qwen3-8B 基座；
- 同一份 67 任务数据，共 640 个决策级训练样本；
- 5 个 epoch，每轮 320 个双卡同步更新，总计 1600 步；
- 每卡 batch 1、全局 batch 2、gradient accumulation 1；
- AdamW，学习率 0.0002，weight decay 0.0；
- BF16、SDPA、gradient checkpointing；
- 最大上下文 32,768 tokens，`enable_thinking=False`；
- 仅 assistant completion token 参与 loss；
- 相同随机种子和 DistributedSampler 数据顺序。

核心实验变量是参数更新方式：LoRA 只训练 21,823,488 个低秩参数；本实验训练
8,190,735,360 / 8,190,735,360 个参数，即 100%。为容纳完整参数、
梯度和 AdamW 状态，本实验使用双卡 FSDP FULL_SHARD；这只改变状态的存放与通信方式，不改变
训练目标或全局 batch。

## 3. 数据与长度

- 训练任务：67 个
- 决策样本：640
- 最短/最长输入：3,277 / 25,070 tokens
- 截断样本：0
- completion-only 监督，无 prompt token loss

## 4. Loss 变化

| epoch | 优化步数 | 平均 loss | 前 20 步平均 loss | 后 20 步平均 loss |
|---:|---:|---:|---:|---:|
| 1 | 320 | 1.166161 | 1.784909 | 1.066574 |
| 2 | 320 | 0.629038 | 0.612017 | 0.707582 |
| 3 | 320 | 0.371676 | 0.382185 | 0.366305 |
| 4 | 320 | 0.239390 | 0.225208 | 0.249823 |
| 5 | 320 | 0.166918 | 0.174145 | 0.134783 |

总 loss 图位于 `metrics/loss_curve_total_5epochs.png`，同时提供 PDF 和原始 CSV/JSON 数据。

- 横轴：全局 optimizer step。每一步表示两张 GPU 完成一次同步梯度更新；每个 epoch 320 步。
- 纵轴：completion-only token 的交叉熵 loss，越低表示模型对教师轨迹中正确下一步文本分配的概率越高。
- 浅蓝线：每个同步更新步的原始 loss。
- 红线：向后 50 步的因果移动平均。
- 竖向虚线：五个 epoch 的边界。

## 5. 双卡 FSDP 与资源

- GPU 0：峰值 allocated 76.40 GiB，峰值 reserved 92.60 GiB
- GPU 1：峰值 allocated 76.40 GiB，峰值 reserved 92.70 GiB

训练、逐轮完整权重导出和诊断验证总用时 89.61 分钟。
epoch 1–4 的完整模型检查点保存在 `artifacts/checkpoints`，最终 epoch 5 模型保存在
`artifacts/model`。

## 6. 诊断验证和模型重载

- 诊断 loss：0.078924
- 诊断 perplexity：1.082122
- 完整模型重载与生成状态：PASS
- 生成的非空 Python 代码块数量：1

诊断数据的 7 个任务也包含在 67 任务全量训练集中，因此此处 loss 只用于检查数值和训练管线，
不能作为泛化指标。模型能力必须由独立的 AppWorld Dev 官方 evaluator 判断。

## 7. AppWorld Dev 就绪状态

`scripts/run_appworld_qwen3_react_full_sft_full_dev.sh` 可使用 vLLM 直接加载本实验完整模型。
具体命令保存在 `DEV_EVAL_READY.md`。本次训练不会自动运行 57 题 Dev 评测。
