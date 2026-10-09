# 原始 Qwen3-8B：train90 采样结果

更新：2026-10-09。**完整 train90 × 6 = 540 条轨迹已完成并验收。** 官方 train 终态成功 39/540；70 个全失败组、20 个成功/失败混合组、0 个全成功组。这些是训练内采样统计，不是 dev 成绩。

本轮只执行采样与验收，尚无 rubric 评分、GRPO 更新或新 dev 结果。采样服务已退出。LoRA 的配对采样也已完成，记录见 [LoRA 实验](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/README.md)。

## 执行记录

使用原始 Qwen3-8B、不加载 adapter；GPU 0 生成、最多六路隔离环境并发。temperature=1、不开 thinking、50 步上限、32000 上下文、单步最多 3000 token。全部成功和失败轨迹均保存模型动作、环境反馈、真实 token IDs 与旧策略 logprobs。

已执行的采样命令为 `python -u step01_collect.py --execute`，当前无需重复启动。该入口只负责第一阶段采样。

## 结果与来源

- [最终统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/summary.json)
- [完整验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/collection_validation.json)
- [轨迹索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/trajectory_index.json)
- [逐任务统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/task_summary.csv)
- [冻结配置与任务清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts/collection_manifest.json)
- [持续实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)

已有代码包含早期训练原型；`run.py pilot/train/all` 及 config 中的旧预算不代表本次实际执行过的实验。PROTOCOL.md 的有效说明已移入 plans，历史源码和配置快照保持原样。

后续安排统一见 [当前待办](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md) 与 [实验计划](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md)。
