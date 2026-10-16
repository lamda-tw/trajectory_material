> **2026-10-15已变更执行范围：仅完成当前单轮，保存模型后结束。** 下面原自动链已停止使用；以 [最新范围](SINGLE_POOL_MODEL_SCOPE.md) 和 [实时记录](ROUND_01_RUN.md) 为准。

# 第一轮启动与参数来源

用户已授权完成必要检查后直接执行第一轮；仅使用物理 GPU1。当前新增的自动入口为 `scripts/run_round1.py --execute`，范围止于第一轮训练后的 DEV57，不自动启动第 2—5 轮。

## 更新什么

延续此前 90 条轨迹 SFT 训练完成的原有 r=8、alpha=16 LoRA，21,823,488 个参数。使用 `PeftModel.from_pretrained(..., is_trainable=True)` 加载既有权重；基座冻结，不重新随机初始化、不额外并联 adapter、不合并到基座。原始 adapter 文件只读，更新保存到本实验 `training/round_01/step_XXXXX/`。

初始 adapter SHA-256：`c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。

## 本次自动执行的顺序

1. 使用完整旧 540 池，在 GPU1 计算固定 A0 reference 概率并缓存。对全池测量 HF/vLLM 差异，保留原始 old log-prob，不覆盖、不删样。缓存带原始轨迹和 A0 哈希，正式阶段可以复用这一不含更新的缓存。
2. 独立目录 `smoke/full_pool_15` 完整试跑：15 批，每批 6 个任务×6 条轨迹；SFT 每轮完整 2,623 步，各批 174/175 步。峰值 LR=5e-6，4 次 warmup，跨五轮连续余弦衰减。每批测量漂移、loss、完整 RL+KL 与 SFT 梯度范数，另记录代表动作上的独立 RL/KL/SFT 梯度和全词表熵。代表动作诊断不参与样本选择。
3. 预先写入的工程检查：同一 A0 的后端平均绝对 log-prob 差 ≤0.05，ratio 越界比例 ≤2%；更新阶段轨迹等权的 ratio 越界比例 ≤25%、sampled-k3 ≤0.1、平均绝对 log-prob 差 ≤0.2。全部都是运行级检查，不是数据筛选，也不是论文保证的最优阈值。最终更新后另查每个训练任务 sample 0 的首动作，共 90 个固定状态。
4. 如果 15 批超过漂移范围，从 A0、新 optimizer 和零游标独立试 5 批，每批 18 个任务×6 条，峰值 LR=2e-6，warmup=2、五轮总计25次更新；SFT 每批524/525步。若仍不通过，则保留现场停止正式推进，不跳样、不根据 DEV 调参。后端对齐异常、NaN 或来源错误也会停止。
5. 通过完整试跑与预算验收后，生成 `config/training_config.json`、最终五轮调度和 `FREEZE.json`。冻结代码、配置、样本、输入池和验收文件哈希。这里的试跑权重不进入正式训练。
6. 固定 A0 做全新 DEV57：temperature=0、seed=100、每题50步上限、每动作3000 token、上下文32000、thinking=False。57题都需完整官方评测，模型失败照实计入，只对基础设施失败重试。
7. 正式第一轮重新从 A0、新 optimizer 和零游标开始。完整540条RL轨迹池内单遍；2,623个SFT步骤完整单遍，共205,238个监督token。每批一次联合更新：`RL + 0.01 KL + 0.1 SFT`。SFT先在每步目标token内平均，再对原始步骤平均。
8. 独立验算逐批身份、540条轨迹各一次、2,623步各一次、监督token总数，保存A1。使用相同协议做第一轮DEV57，输出 `ROUND_01_COMPLETE.json`，停止在第一轮终点。

## 无人值守和恢复

- 监督进程锁防止重复启动；每个GPU阶段经GPU1 UUID启动器和GPU互斥锁。
- 每批checkpoint原子提交，保存optimizer/RNG/游标；崩溃后重算尚未提交批，已提交批不重复更新。已存轨迹与reference按哈希复用。
- 每20秒写心跳，监测可用磁盘和阶段进展；40分钟无进展视为基础设施异常。瞬态错误最多3次恢复；数值或来源异常保留现场，不能假装完成。
- 只清理本实验记录且进程启动标识仍匹配的子进程，不终止同事进程。GPU0不使用。
- 实时状态为 `STATUS.json`、`runtime/round1_run/heartbeat.json`；reference为 `cache/round_01_A0_reference/progress.json`，试跑为 `smoke/full_pool_15/progress.json` 或 fallback 05，正式为 `training/round_01/progress.json`。
- 自动流程不是无人监督即可处理所有未知故障的保证。出现无法保持实验定义的问题时，会记录 `runtime/round1_run/ERROR.json` 并停止推进。

启动命令（从实验目录）：

```bash
/root/autodl-tmp/workspace-tw/.conda-training/bin/python -u scripts/run_round1.py --execute
```

本说明描述已实现入口和执行约定；实际当前阶段以 STATUS.json 和 ROUND_01_RUN.md 为准，不能把排队的正式阶段当作已经发生。
