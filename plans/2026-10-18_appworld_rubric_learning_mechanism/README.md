# AppWorld Rubric 学习机制实验计划

> 最新执行范围（2026-10-18T18:34:46+08:00，北京时间）：用户授权在空闲 GPU0 增加 seed **20261017**。GPU1 继续 **20261015、20261016**；每组 **1,358 步、1 epoch、679 更新**；DropR7 复用同 seed DropR5。共 **21 次实际训练、24 个条件记录**，仅按评分选样。GPU1 已运行；GPU0 预检通过并开始 DropR1 正式训练。同状态诊断尚未开始。

[完整计划](PLAN.md) 的当前主实验为逐项完整删除 R1–R8。忽略 Ri 的所有标签，仅要求其余七项 P≥3 且 F=0，允许 N/U；候选资格只由评分决定，然后全池等概率无放回抽取 1,358 步。没有语法、执行成功、最终成功、长度过滤，也没有任务配额或补足。

GPU1 跑 seed 20261015/20261016；GPU0 跑新增 seed 20261017。每个真实运行从原始 Qwen3-8B 新建 LoRA，1 epoch、679 更新。DropR7 使用同 seed 新 DropR5 的相同选样、顺序、模型与评测，因此是 7 种配方 × 3 seed = 21 次训练、14,259 次更新、1,197 个 DEV57 任务 rollout。不是复用旧 1,710 步模型，也不新增 Random/ZeroFail3 训练项目。

DropR5 的当前候选集合恰好等于完整八规则集合，可作等价参照；没有同预算 Random，本轮不直接证明优于随机选样。三个 seed 仍只提供有限的随机性证据。同状态动作诊断尚未运行，完整后续规模更新为原始模型加 21 个新模型、256 个状态、5,632 次单步生成。

[实验总进度](../../experiments/2026-10-18_appworld_rubric_dimension_ablation/README.md) · [三 seed 结果](../../experiments/2026-10-18_appworld_rubric_dimension_ablation/REPORT_THREE_SEEDS.md) · [候选池与集合哈希](candidate_counts.json) · [P 组成分析](PASS_ANALYSIS.md)

最小池为 DropR2 的 1,359 步，统一取 1,358 步保证两步累积完整。统一训练量不等于统一 token 数或算力；见完整计划 B5。上一阶段已推送节点为 `60db9d25`。
