# SFT LoRA 起点：train90 采样结果

更新：2026-10-09。**完整 train90 × 6 = 540 条轨迹已完成并验收。** 官方 train 终态成功 186/540；23 个全失败组、63 个成功/失败混合组、4 个全成功组。这些是训练内采样统计，不是 dev 成绩。

本轮只执行采样与验收，尚无 rubric 评分、GRPO 更新或新 dev 结果。后台采样已结束。完整过程见 [实验报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/RUBRIC_GRPO_EXPERIMENT_REPORT.md)。

## 执行记录

策略为 Qwen3-8B + 现有 train90 / epoch5 LoRA，rank 8、alpha 16。使用 GPU 0、独立端口 8129，任务、六个 seed、prompt、parser、解码参数与预算均与 raw 分支配对。

昨夜因 AppWorld 无法序列化 Python Ellipsis 日志参数而中断。2026-10-09 完成日志兼容修复，保留原有 342 条轨迹不变，补齐 198 条；模型动作、真实环境反馈与官方终态评价保持原协议。全部 540 条通过 token 重建、old logprob 对齐与完整性验收。

已执行的采样命令为 `python -u step01_collect.py --execute`，当前无需重复启动。历史 supervisor 最多尝试三次；恢复记录和修复前快照保存在 recovery/2026-10-09/。

## 结果与来源

- [最终统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/summary.json)
- [完整验收](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/collection_validation.json)
- [轨迹索引](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectory_index.json)
- [两分支采样统计](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/collection_comparison.json)
- [恢复与最终诊断](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/recovery/2026-10-09/final_diagnostics.json)
- [冻结初始 adapter](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/initial_adapter)
- [采样任务清单](/root/autodl-tmp/workspace-tw/experiments/2026-10-08_static_rubric_grpo_lora_init/preparation/planned_jobs.json)

本目录已有采样和验收入口、静态规则与 judge 模块，尚无经过真实更新验证的 LoRA GRPO 续训入口。config 中继承的旧训练预算不是已执行记录。COMPARISON.md 的有效内容已并入 plans；来源快照中的历史副本保留原样。

后续安排统一见 [当前待办](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/README.md) 与 [实验计划](/root/autodl-tmp/workspace-tw/plans/2026-10-08_rubric_research/EXPERIMENT_PLAN.md)。实验报告仅存放在本实验目录。
