# CFST-Action-1epoch 训练报告

状态：训练完成，核验通过；尚未运行检查30题或Dev57。

从原Qwen3-8B + train90 LoRA第5轮adapter独立启动，重新建立AdamW优化器。学习率2e-4，全局batch=2，双卡各1条，梯度累积1；BF16、SDPA、seed=20260928、最大40,960 tokens；LoRA r=8、alpha=16、dropout=0。保持旧版训练模板和completion-only loss。

| 项目 | 实际结果 |
| --- | ---: |
| 唯一样本 / 实际训练样本次数 | 8 / 8 |
| 每条样本实际进入参数更新的次数 | 1 |
| 优化器更新 | 4 |
| 教师动作监督tokens | 1,493 |
| 输入tokens（历史加答案，不含padding） | 99,675 |
| 输入tokens（按8对齐，含padding） | 99,712 |
| 历史tokens（不计入loss） | 98,182 |
| 第一次 / 最后一次更新的loss | 0.936241 / 0.903857 |
| 更新loss的算术平均 | 0.916896 |
| 训练结束后原数据包诊断loss | 0.426403 |
| 更新阶段耗时（秒） | 60.95 |
| 训练、诊断与保存耗时（秒；不含加载） | 70.27 |
| 最大单卡预留显存（GiB） | 86.61 |
| 实际更新的LoRA张量 | 504 / 504 |
| 与起点权重的L2差值 | 2.246652 |

每个更新使用的样本不同，首尾loss不能直接视为同一批数据的下降量。诊断loss是训练完成后，对本分支原训练包做一次无梯度计算，不更新权重、不增加训练轮数，也不是独立验证分数。任务效果仍需之后的同协议检查30题评测。

保存的adapter已经与Qwen3-8B重新加载并完成一次有限数值前向检查。权重SHA256：`c87311f2629834b642db2d668b3981052ff8aed460d68f36268d3cb837ab023f`。

[独立adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/adapter) · [训练配置](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/training_config.json) · [每次更新及实际样本记录](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/loss_history.jsonl) · [完整指标](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/metrics.json) · [原始日志](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06b_lora_one_epoch/CFST-Action/train.log)
