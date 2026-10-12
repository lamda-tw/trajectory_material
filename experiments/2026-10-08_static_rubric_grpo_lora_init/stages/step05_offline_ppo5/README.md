# 固定 train90 轨迹的五轮离线 PPO

**2026-10-10 已取消此执行方案。** 用户改为完整 90×6 仅做一次更新；五轮等待进程已停止，本阶段未执行真实 8B 训练。当前入口为 [单次更新等待执行器](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step04_train90_single_update_v1/orchestration/README.md)。以下保留历史设计，不能作为当前启动指令。

2026-10-10：用户因资源不足选择离线方案，并随后明确要求暂不占用 GPU。**当前只运行补评分和 CPU 检查；评分完成后不会自动训练，也不会等 GPU 空闲后自行训练。**

实验固定完整 90 题 × 6 条 = 540 条初始 SFT 策略轨迹。18 条当前基线有效评分复用，剩余 522 条补评。当前补评由原 step04 的已验证评分入口执行；本阶段通过同一评分锁等待它结束，再补齐缺失结果并生成自己的固定 batch，避免重复评分。两处原始请求、响应和日志均保留。

## 五轮的准确含义

1. 官方 21 条静态规则和现有基线 judge/prompt 不变。在每题六条内计算 rule filtering、reward 和 advantage，训练前一次冻结；不混入 v3 评分。
2. 从生成这批轨迹的初始 SFT LoRA 开始，新建 AdamW，不从工程 smoke checkpoint 接着训练。
3. 每个 PPO epoch 都遍历同一批 540 条，累计全部梯度后执行一次 optimizer step。共五个 epoch、五次 optimizer step，epoch 之间连续使用模型和 optimizer 状态。
4. 五遍始终使用原采样时的 old logprob。第 2～5 遍的 PPO ratio 为当前 policy 概率 / 原始 behavior 概率，不把上一遍模型概率替换成 old，也不把 ratio 重置为 1。
5. KL reference 始终为独立冻结的初始 SFT 模型。其精确 logprob 在首遍缓存，后续按 trajectory SHA256、reference 身份和内容校验值复用。
6. 每遍每题六条及所有失败、零优势轨迹均保留；只对模型生成 token 计算损失，轨迹内按生成 token 平均后再对 540 条平均。

这是固定数据重复使用的离线 PPO/GRPO 实验，偏离 DRACO 更新后继续采样的在线循环。五轮不产生新 AppWorld rollout，也不重复调用 judge。五遍合计读取 8,928,620 个生成 token、执行 49,430 个逐步骤 backward；这是已验证输入的五倍计数，不是已完成训练量。

lr=5e-5、clip=0.2、KL=0.01、weight_decay=0、梯度裁剪=1、LoRA rank8/alpha16 沿用此前工程配置。这里没有把完整训练批拆成多次参数更新，也没有把五个 epoch 当成五次重新采样。

## 恢复与校验

- 每完成一题的六条轨迹，原子保存累计梯度、已处理轨迹数、指标、RNG 和 batch/epoch/parent 身份。中断后恢复到最近完整组；不会重复累计已保存的梯度。
- 每轮提交 adapter、optimizer、RNG、指标与来源清单，并验证 adapter 保存重载后的真实 token logprob 一致。五轮 checkpoint 分别放在 rubric/epoch_001 至 epoch_005。
- 后续轮从上一轮 checkpoint 和 optimizer 恢复，但数据、reward、advantage、behavior logprob 和 reference 保持不变。
- 原始 HF/vLLM 概率对齐检查始终比较初始 reference 与 behavior；当前 policy 对齐阈值只用于第 1 遍。后续正常策略变化通过 ratio、clip fraction、KL 等指标记录，不误判成采样协议错误。
- 第 1～5 遍若缺评分、来源不符、非有限 loss/gradient，均停止，不丢弃样本或自动记零奖励。
- 当前模型仍使用原始 8B policy 与独立 reference 的加载方式；没有做新的真实 GPU 验证。12 项测试在标准库或小模型 CPU 环境完成，包括实际五轮训练入口的 checkpoint 与 optimizer 续接。

## 当前允许的命令

```bash
DRACO_OFFLINE=/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/stages/step05_offline_ppo5

# 只校验输入与缓存，不加载模型。
python "$DRACO_OFFLINE/run.py" prepare

# 仅补评和构建固定 batch；若旧评分进程正在运行，会先等待共享锁。
python "$DRACO_OFFLINE/run.py" score --execute

# 全部评分已经存在时，只构建固定 batch。
python "$DRACO_OFFLINE/run.py" build-batch
```

没有“评分完成自动训练”的 all 命令。未来用户明确允许 GPU 后，才可运行：

```bash
python "$DRACO_OFFLINE/run.py" train --execute --allow-gpu
```

GPU 计划仍为 1 号卡，启动前要求空闲显存至少 80 GiB；不修改或停止他人的进程。当前不能执行上述训练命令。run.py 和 train.py 都拒绝缺少显式 GPU 启动标志的实际训练调用。

## 产物

[运行清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1/manifest.json) · [准备检查](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1/readiness.json) · [当前状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1/status.json) · [CPU 验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step05_offline_ppo5_v1/offline_validation.json)

本阶段源码与配置已独立冻结。原始轨迹、adapter、root config、step03 工程训练与 step04 单次更新入口均保留；step04 本次只执行 score。fixed_batch/batch.json 与 reward_summary.json 仅在全部 540 条评分有效时生成。准备检查中的缓存数是检查时的快照，运行中进度以评分日志及有效 judgement 文件为准。
