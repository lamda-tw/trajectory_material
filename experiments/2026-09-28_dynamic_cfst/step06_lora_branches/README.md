# CFST 第6步：三个独立LoRA分支

第6步训练状态为 **SUCCESS**。三个分支都从同一个 **Qwen3-8B + train90 LoRA第5轮adapter** 独立启动，只执行一次新的CFST短训，然后保存各自adapter。没有串行继承State、Action或Mixed之间的权重。

## 关于“沿用旧参数”

- **沿用模型权重：** 三个分支均加载相同基座和相同epoch5 adapter，源adapter SHA-256为 `c8fdfd…9938`。
- **重新建立优化器：** epoch5 adapter是模型权重产物，不含本次三分支共用的AdamW状态；每支都从相同的新AdamW状态开始。
- **保持相同训练配置：** LoRA结构、BF16、长度、batch、学习率和seed完全相同。
- **只短训本step：** 每支处理约8,000个修复答案tokens后结束，没有再跑原来的5个epoch。

## 训练结果

| 分支 | 唯一数据 | 监督tokens | 更新步数 | 首步 → 末步loss | 重合诊断loss |
| --- | ---: | ---: | ---: | ---: | ---: |
| CFST-state | 12 | 8,138 | 27 | 1.0632 → 0.0944 | 0.0364 |
| CFST-Action | 8 | 8,150 | 22 | 1.4323 → 0.0603 | 0.0405 |
| CFST-Mixed | 20 | 8,160 | 25 | 1.2286 → 0.2438 | 0.1956 |

三个实际预算范围为8,138–8,160，最大差22 tokens，即目标8,000的0.275%。更新步数不同是因为三包的修复答案长度不同；控制量是计划中预先指定的监督token预算。

![三分支训练loss](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/loss_curves.png)

## 三个adapter

- [CFST-state adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-state/adapter) · [训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-state/REPORT.md)
- [CFST-Action adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Action/adapter) · [训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Action/REPORT.md)
- [CFST-Mixed adapter](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Mixed/adapter) · [训练报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/CFST-Mixed/REPORT.md)

最终权重SHA-256分别为：

- State：`846bf990d1c675b3f151f8a81e497f6a20528e9d0d3b25e2e5673206ef8f026d`
- Action：`16cea6a7e5f2895498af3c4d6f0914af849fdbc16e71994aecbf155927e0be4e`
- Mixed：`fe5b0676f87b1f3d4575ffd83e25adf1cbaacafd4c13a29d3c682fb8e8777709`

三个哈希互不相同，且504/504个LoRA tensors相对源adapter发生非零变化。

## 验收结果

73项训练、预算、来源、配置、权重与结构检查全部通过。随后把三个adapter同时重新加载到同一个Qwen3-8B上，分别执行真实forward：三者logits全部有限且哈希互不相同。GPU在流程结束后已释放。

- [结构化汇总](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/summary.json)
- [73项验证](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/validation.json)
- [真实重载验证](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/reload_validation.json)
- [训练前冻结计划](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/training_plan.json)
- [Loss曲线PDF](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step06_lora_branches/loss_curves.pdf)

本步没有运行检查30题或Dev57，也不能从训练loss判断哪个分支更好。下一步必须按第7步协议让原模型和三个新分支从头完成冻结的检查30题。
