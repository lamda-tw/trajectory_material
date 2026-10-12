# 完整 train90 的两卡单次 GRPO 更新

2026-10-10 用户授权 GPU 0、1 同时使用。单卡运行在第 1 条轨迹、第 10 个步骤停止，尚未执行 optimizer.step；中断记录保存在 step04 运行目录的 orchestration/parallel_transition。原 540 条评分、reward、advantage 和 batch 全部保留，不重采、不重评，也不进入五轮方案。

## 如何并行且只更新一次

- 每张卡分别加载初始 SFT policy 和独立冻结的初始 SFT reference。90 个完整六条组按预计计算量分配，两卡各 45 题、270 条，覆盖全部 540 条且互不重复。
- 两卡只计算梯度，worker 内没有 optimizer。每步 loss 仍除以全局 540 和本条轨迹的生成 token 数，保留所有失败、零优势样本及原始 behavior logprob。
- 两个分片全部完成并校验后，合并器对梯度求和，统一做一次梯度裁剪和一次 AdamW step。不会再除以卡数，也不会分别得到两个更新后的模型。
- 合并器从相同初始模型加载，检查两个分片的模型、reference、batch 和执行身份相同。数值上与完整单批次梯度累积等价；计算顺序变化可能带来浮点舍入差异，不承诺逐位一致。
- 只提交一个 LoRA checkpoint，并检查保存重载的真实 token logprob。没有第二轮 PPO、重新采样或自动评测。

## 运行文件

运行目录：`/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1`。

- manifest.json：冻结的源码身份、原 batch SHA256、各卡任务分配和预计计算量。
- status.json / STATUS.md：两卡实时进度和整体执行阶段。
- worker_0 / worker_1：各卡训练日志、进度、累计梯度及完成清单。
- checkpoint：最终更新后的 adapter、optimizer/RNG 和来源清单；必须全部校验成功后才提交。
- evaluation_target.json：成功保存后的评测加载路径。模型为 LoRA adapter，需与 `/root/autodl-tmp/models/Qwen3-8B` 一起加载。

每卡每完成六条轨迹原子保存累计梯度、RNG、归一化指标及批次/分片身份。中断后从本卡最近完整组恢复，最多重算当前组；尚未合并的梯度不会被当作模型 checkpoint。已完成分片经过哈希校验后直接复用，已提交的模型经过校验后跳过，防止重复更新。

主进程持有新旧运行目录的锁，两卡 worker 各自也持有锁。任何 worker 失败都停止合并；其他 worker 的已保存梯度保留。启动时检查对应 GPU 无其他计算进程且至少 80 GiB 空闲，GPU 被占用则等待，不停止其他人的任务。

## CPU 验证与入口

5 项 CPU 测试通过：分组覆盖、不等长分片的梯度与单次更新数值等价、无效分片拒绝、缺分片时禁止 GPU 加载，以及实际小型 Qwen3 LoRA 的中断恢复/合并/一次更新/保存重载。旧训练源码、评分规则与 batch 没有改动。

```bash
# 只准备与校验，不加载 GPU 模型。
/root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step06_train90_two_gpu/run.py

# 执行或中断后恢复；已有运行进程时不要重复启动。
/root/autodl-tmp/workspace-tw/.conda-training/bin/python /root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step06_train90_two_gpu/run.py --execute
```

预计两卡会减少梯度计算耗时，实际加速取决于轨迹长度和负载分配，以运行数据为准。
