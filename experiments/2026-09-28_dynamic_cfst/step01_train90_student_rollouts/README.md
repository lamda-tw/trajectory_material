# 第一步：train90 学生轨迹

**已完成：90/90，官方成功46题（51.1%）、失败44题，完整性核验通过。** 先看 [结果报告](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step01_train90_student_rollouts/REPORT.md)。

使用现有 Qwen3-8B 和 train90 LoRA epoch5 adapter，原协议运行 train90。

- 配置与来源：`manifest.json`、`config/`。
- 逐题即时官方评分：`task_status.jsonl`。
- 原始交互、执行代码、环境反馈、数据库和逐题官方报告：`experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/tasks/<task_id>/`。
- 官方聚合结果：同级 `evaluations/train.json`。
- 完成后生成：`REPORT.md`、`task_results.csv`、`success_task_ids.txt`、`failed_task_ids.txt`、`infrastructure_error_task_ids.txt`、`summary.json`。
- 运行记录：`logs/run.log`；恢复运行必须先检查状态与已完成标记，避免重复推理。

这是已用于 SFT 的训练任务诊断，不作为未见任务的泛化成绩。
