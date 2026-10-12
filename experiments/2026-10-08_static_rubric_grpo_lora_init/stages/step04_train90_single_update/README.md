# train90：静态 rubric → reward → 单次 GRPO 更新

**两卡执行已接替本单卡入口。** 用户授权 GPU 0、1 并行，540 条评分及 batch 保留，本阶段未提交全量模型更新。请查看 [当前两卡入口](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step06_train90_two_gpu/README.md) 和 [进度](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step06_train90_two_gpu_v1/STATUS.md)。不要恢复旧单卡控制器。

**2026-10-10 15:24（北京时间）：全量评分已完成并核验，540/540 条、90/90 个完整六条组。** 网络中断后保留原 312 条有效评分并补齐 228 条，原评分 SHA256 全部未改动；共 11,340 项规则判定。输入来源、评分请求/响应一致性和每题 reward/advantage 重算均通过，90 组均有非零优势。全量 batch 已生成，readiness 的待评分数为 0。训练继续按原定单次更新及 GPU 空闲门槛执行，不再调用 judge。

[评分完成记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/scoring_completion.json) · [逐题/逐次输入输出索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/score_index.json) · [reward 明细](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/rubric/update_001/reward_summary.json) · [实时执行阶段](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/orchestration/status.json)

此前 step03 的实际规模是：3 题共 18 条得到评分，但只用 afc0fce_1 的 6 条轨迹累计梯度并执行一次 optimizer step。本阶段是独立的全量初次更新：policy 从原始冻结 SFT LoRA 加载，optimizer 新建；reference 单独加载同一个初始 SFT 模型并冻结。已有 540 条正是这个初始策略生成的，可以用于本次更新。

## 固定执行范围

- 完整 train90，每题六条，保留所有失败和零优势轨迹；不使用 dev。
- 官方 21 条静态规则、当前基线 prompt、gpt-5.6-sol / high 保持不变，不混入 v3 分数。
- 在**每题六条内部**保留至少出现一次 FAIL 的规则；`R=10*(P-F)/(P+F)`，NA 不计分母，分母为零记 0。优势同样只按本题六条归一化。
- 一个 PPO epoch；540 条全部累计梯度后执行**一次** AdamW step。每个生成步骤执行一次 backward；该批共 9,886 次 backward、1,785,724 个生成 token，最长上下文 32,000。只计算模型生成 token 的损失。
- 损失先在每条轨迹内部按生成 token 数平均，再对 540 条轨迹平均。lr=5e-5、clip=0.2、KL=0.01、梯度裁剪=1.0；LoRA rank8 / alpha16，沿用现有 SFT。
- GPU 1 延续用户授权，启动时重新检查空闲显存；准备阶段不分配或预留 GPU。
- 本入口只支持初始策略的 rubric update 1；若以后继续更新，需要新策略重新采样。

这里把 90 题作为一个完整梯度批次，是本轮确定的本地安排。“一个 PPO epoch”本身并不等于“一次 optimizer step”；本配置明确同时固定这两项，不能用旧入口的 `--updates 90` 代替。

训练逐步骤前向、反向、累计梯度，不同时把 540 条放入显存。全量计算显著多于六条 smoke；尚未实测全量训练耗时。checkpoint 只在整批更新完成并通过检查后提交；若训练中途退出，当前实现需要重算整批梯度，不支持从半批进度恢复。已经提交的 checkpoint 会被核验并跳过，避免重复更新。

## 底层命令

以下保留底层入口供检查。当前由 orchestration/after_scores.py 等待执行；它额外检查 GPU 是否被其他任务使用，不应并发手动启动下面的训练命令。

```bash
DRACO_STAGE=/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step04_train90_single_update

# 仅检查文件与缓存，写本地清单，不启动 judge 或模型。
python "$DRACO_STAGE/run.py" prepare

# 底层入口：补齐评分并计算全量 reward/advantage，不训练。
python "$DRACO_STAGE/run.py" score --execute

# 评分齐全后：只构建/校验全量 batch，无网络、无训练。
python "$DRACO_STAGE/run.py" build-batch

# 底层入口：加载已完成的 batch，累计全量梯度并更新一次。
python "$DRACO_STAGE/run.py" train --execute

# 或连续完成补评、组内 reward、一次训练。
python "$DRACO_STAGE/run.py" all --execute
```

`score / train / all` 不带 `--execute` 时均只准备。`score` 成功后自动写 batch；任何缺失、过期或未完成的评分均拒绝进入训练。评分并发 2，每次调用最多两次技术尝试；显式重启可以重试技术失败，旧请求目录移入 technical_failures 留档。若中断前已有完整有效响应，会恢复最早有效响应，不重抽语义结果。当前 18 条缓存均校验 prompt、cache key、原始 response、事件完成状态及最终消息一致性。

## 文件与验收

[运行清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/manifest.json)固定全部任务、输入 SHA256、初始 policy ID、配置和源码；[准备状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/readiness.json)记录缓存和待评数。jobs.json 与 input_inventory.json 保存全部轨迹清单；source_snapshot 留存本阶段代码。未来评分、batch 和 checkpoint 写入该运行目录的 rubric/update_001。

train.py 与已完成真实 8B 更新的 step03 训练代码逐字节一致，原 SHA256 记录在 provenance.json；本阶段 pipeline 限制任务规模和策略来源。原实验配置、原轨迹、初始 adapter、step03 源码及 checkpoint 均不修改。

纯标准库测试已通过 5 项：完整 90 组及独立优势、缺失/重复样本与过期策略拒绝、缺失评分拒绝、默认不执行、最早有效响应恢复及已验证 trainer 来源。此次测试不导入训练模型、不调用 judge、不执行 backward。原 stage03 的真实模型检查结果仍保留；这些准备检查不代表全量训练已经成功或 dev 效果已提升。
