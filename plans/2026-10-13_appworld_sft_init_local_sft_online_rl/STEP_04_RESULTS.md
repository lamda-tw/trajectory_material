# 第 4 步：联合训练器、整池采集接口及基础验收

2026-10-14，北京时间。已实现并执行 CPU 数学测试和 GPU1 基础集成试跑。没有启动正式 RL/SFT，也没有新采集正式 540 条；已有首轮 540 条已完整导入只读池索引。

## 已确定的实验语义

- 一轮固定行为模型采集 90×6=540 条，轮内不采新轨迹；第一轮使用现有池。
- 池内单遍分批训练，**每批完成后更新参数一次**；轮末保存最终模型并采集下一池。
- 每批在同一参数状态累积 RL、KL 和步骤等权 SFT 梯度，统一裁剪并更新已有 LoRA。基座冻结；只存在一个可训练 adapter。
- old log-prob 整轮固定；reference 始终为初始 SFT 模型 A0。A0 概率在训练阶段之前缓存，不使用禁用 adapter 的裸基座。
- 固定 2,623 步每轮完整学习一次，P−F≥4 之外没有新增筛选。
- GPU0 不使用；所有 GPU 入口固定 GPU1 UUID，且本实验 GPU 阶段具有互斥锁。

## 代码与产物

| 文件 | 作用 |
| --- | --- |
| scripts/joint_core.py | GRPO 优势、clipped objective、sampled-k3 KL、完整前缀目标概率、步骤平均 CE、共享 LR、原子 checkpoint/RNG 恢复 |
| scripts/joint_trainer.py | 完整轨迹池内的单遍联合更新；单样本微批；逐 batch 原子提交；轮内不启动采集 |
| scripts/round_data.py | 原始轨迹/完整任务组验收，旧 540 导入，固定随机调度 |
| scripts/collect_round.py | 单一行为 adapter 与单一 vLLM 服务采完一池；模型不更新；技术失败留档重试 |
| scripts/rollout_worker.py / policy_server.py | AppWorld 隔离运行、原始消息/token/行为概率/官方终态保存 |
| scripts/05_build_schedule.py | 可审查的候选五轮消费清单，不做正式冻结 |
| rollout/round_01/pool.json | 全部旧 540 条的只读引用、哈希、奖励、行为版本；未重采 |
| data/sft_schedule_candidate.jsonl | 当前 15 批候选对应的 75 次具体任务组和 SFT 身份 |
| config/pool_training_draft.json | 当前工程候选：lambda=0.1、KL=0.01、共享峰值 LR=5e-6；非正式冻结配置 |

GPU 真实试跑所使用的配置另存于 references/step04_smoke_config.json。历史 config/draft.json、step03_training_draft.json、step_equal_training_draft.json 和前期 manifest 保留为快照，不能误认作当前配置。当前入口为 config/current_draft.json。

## 实际验收结果

1. **CPU 数学**：checks/joint_math.json 通过。步骤平均与微批/分段梯度完全一致；生产 accumulator 与整体联合目标的最大梯度误差约 7.45e-9；目标位置分块与标准完整 logits 的最大 LoRA 梯度误差约 1.61e-8；checkpoint 恢复与连续更新参数误差为 0。验证了 RL 标量为 0 时梯度仍可非零、全等奖励优势归零、错误 checkpoint 被拒绝。
2. **GPU1 最长样本**：31,814 token 完整前缀加目标成功反向传播，峰值 allocated 显存 38.98 GiB，耗时 50.58 秒；21,823,488 个已有 LoRA 参数可训练，基座无梯度。见 smoke/gpu_probe/report.json。
3. **真实新采集接口**：1 个固定训练任务，2 条试跑轨迹，每条上限 2 个动作。4 个动作的 prompt_ids 与本地模板/完整历史逐项一致，response_ids 解码与原始输出一致；均有官方结果。见 checks/collection_protocol.json。它们是工程试跑，不进入正式池。
4. **真实联合更新与恢复**：在上述小池及完整 SFT 目标上执行 2 次隔离更新，最大 LoRA 参数变化 3.755e-6；两次保存/重载误差为 0，reference 缓存哈希不变。两条实际奖励都是 0，保留全等组；第 1 次 RL/KL 梯度为 0，SFT 正常更新；第 2 次 KL 非零。非零 RL 梯度已通过 CPU 构造例验证，不能声称本次真实短池具有非零 RL 奖励差异。见 smoke/joint_integration/report.json。
5. **GPU 约束**：检查了 UUID 映射和并发阶段互斥，进程退出后锁释放。见 checks/gpu1_lock.json。
6. **候选预算**：每轮 15 批，共 75 次更新；旧 540+新 2,160=2,700 条 RL 消费；13,115 次 SFT 步骤呈现、1,026,190 监督 token，身份没有丢失或重复消费。见 checks/schedule_candidate.json。

## 已处理的环境问题

现有 vLLM 0.10.2 的 NVML 设备查询会对 CUDA_VISIBLE_DEVICES 调用 int()，不支持 GPU UUID，导致首次服务启动失败。首次本地兼容尝试又遇到环境未安装顶层 pynvml，之后改用 vLLM 自带的 NVML 包，成功启动和采样。

修复位于 scripts/vllm_uuid_compat/sitecustomize.py，仅本实验 vLLM 子进程通过 PYTHONPATH 启用。保持 CUDA_VISIBLE_DEVICES 为物理 GPU1 UUID，并通过 NVML 检验该 UUID 仍对应 index=1；没有修改共享 vLLM 安装、没有改成 GPU0。失败日志保留在 smoke/collection_protocol/server/vllm.log。

## 尚未完成、不可夸大的部分

- **15 批仍为全池试跑候选，不是已确定的最佳设置。** 显存实测支持单样本梯度累积，有效 batch 可以增大而不把全部序列同时放入显存。下一阶段由 agent 在 GPU1 上检查完整池的后期策略偏离和耗时，自行确定批次数；若变更，重算全局 LR 和消费调度，不要求用户替代工程判断。
- 此次真实短池仅用于基础集成测试；两次重复使用它是恢复测试，不是正式“池内单遍”调度，也不能代替完整 540 池更新阶段。
- **HF/vLLM 数值差异尚需制定正式容差。** 三个历史动作的平均绝对 log-prob 差约 0.0036—0.0141；新试跑池初始约 0.0136，未更新前约 0.45%（按轨迹均值归约）的 token ratio 已越过 [0.8,1.2]。不能把该基线误认为真实策略漂移，也不应覆盖原始 old_logprobs 来消除它。详见 checks/logprob_alignment.json。
- 当前 KL 是在行为策略采样动作上计算的 sampled-k3 正则，不是精确当前策略 KL；sampled_action_nll 也不是完整分布熵。正式试跑前需补齐独立分支/熵诊断。
- 尚未完成整轮 540 新采集试验、完整池训练稳定性试验、轮间自动编排、DEV57 初始基线及正式配置冻结。formal 入口会拒绝缺少 FREEZE/基线的运行。

本步骤仅证明核心代码与基础链路可运行，不能据此宣称五轮正式实验已具备无人值守验收结论。
