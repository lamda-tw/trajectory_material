# GPU0 新增 seed 20261017

用户于 2026-10-18T18:34:46+08:00 授权使用空闲 GPU0 增加一轮独立 seed。与 GPU1 两个 seed 合计三轮；不是增加 epoch。

<!-- AUTO_PROGRESS_START -->
准备选样与校验。
<!-- AUTO_PROGRESS_END -->

每组 1,358 步、1 epoch、679 次更新；DropR1–R8，仅按其余七项 P≥3 且 F=0 取候选，再全池等概率无放回抽样。DropR7 复用同 seed DropR5，实际 7 次训练及 DEV57。无语法、执行成功、长度、最终成功过滤，无题目配额或补足。

原始 Qwen3-8B 每次新建 LoRA；LR=2e-4，r=8/alpha=16/dropout=0，其余设置与 GPU1 完全一致。训练及 DEV 程序逐字相同，只有单卡资源与输出路径隔离。物理 GPU0 UUID：`GPU-2044de33-9504-3cdf-451a-e9196cbdb21a`；推理端口 8180；world_size=1。评分 prompt 为既有英文 v6 format，保持评分哈希不变。新 seed 同时作用于选样、顺序与 LoRA 初始化；DEV 使用相同固定 seed=100。

[总进度](../README.md) · [三 seed 汇总报告](../REPORT_THREE_SEEDS.md) · [配方一致性](references/recipe_equivalence.json)
