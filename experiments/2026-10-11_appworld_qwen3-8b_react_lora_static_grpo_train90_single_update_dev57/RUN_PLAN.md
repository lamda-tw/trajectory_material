# 静态 rubric GRPO 单次更新：dev57 评测

完整 90 题 × 6 轨迹累计梯度、一次 optimizer step 的最终 LoRA；Qwen3-8B 基座不合并复制。复用 2026-09-23 全参数 SFT 评测的官方 dev57、ReAct 提示词及评测器；同时引用更新前 LoRA 历史成绩作主要对照。

温度 0，seed 100，50 步，单次输出最多 3000 tokens，模型窗口 32000。无 reasoning parser，无 enable_thinking 覆盖，遵循历史 dev 协议；此处与训练轨迹采集的显式 enable_thinking=false 有区别。按原顺序在 GPU 0 执行 57 题，逐题保存输入输出与官方评分。上下文溢出、模型代码错误和预算耗尽均保留，不重采挑选结果。

本次不更新模型、不调用 rubric judge，不运行 test_normal。状态见 STATUS.md；结果见 REPORT.md、summary.json、task_comparison.csv 及 experiments/outputs 下完整轨迹。
