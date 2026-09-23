# 固定第5轮模型 test_normal 168 题评测

- 模型：`/root/autodl-tmp/workspace-tw/experiments/2026-09-23_093106_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5/artifacts/model`；不重新训练，不选择中间 checkpoint。
- LoRA 对照：`/root/autodl-tmp/workspace-tw/experiments/2026-09-21_121920_appworld_qwen3-8b_react_lora_codex_rft_train90_test_normal168`，使用其原始完整 168 题结果与轨迹，不使用后续24题扩窗复测结果替换。
- 官方 test_normal 共168任务、56场景；与 train/dev 无交集。
- 与 LoRA 相同的任务顺序、ReAct agent、提示词、temperature=0、seed=100、50步、单次3000输出tokens、32000总上下文、无reasoning parser；GPU0单进程顺序执行。
- 每题写入官方 evaluator 结果，全体结束后生成官方聚合评分；上下文限制或模型行为导致的失败计入成绩，不扩大窗口重跑挑分。
- 环境只读复用 `/root/autodl-tmp/envs/`；所有文件修改和临时缓存仅在 workspace-tw。
- 产物包括中文报告、逐题CSV、两组同口径失败分析、代表轨迹案例、训练loss/性能图、官方结果及校验清单。
- 对训练轮数、低秩约束、优化器配置、轨迹分布偏移分别列出事实和待验证假设；不能从单个epoch5测试结果确认epoch2更优。
- 测试反馈用于事后报告，不进入任何训练或本次模型/超参数选择；后续方案只在训练任务和验证集上设计消融。
