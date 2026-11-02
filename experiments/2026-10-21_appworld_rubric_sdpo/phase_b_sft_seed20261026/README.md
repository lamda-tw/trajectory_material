# 纯 ZeroFail3 SFT：seed 20261026 三轮复现

从原始 Qwen3-8B 重新初始化 LoRA，只改变训练 seed；使用 GPU1。每批5题，每题1条完整在线轨迹；Codex v7 评分后仅 ZeroFail 且 PASS>=3 进入 SFT。前5次有效更新 warmup 至5e-5，此后恒定。共54批，每18批评估一次 dev57，三轮后停止。用户已明确取消15小时上限。

新 seed 同时影响 LoRA 初始化、题目顺序和 rollout 派生种子。dev57 seed 固定100。首批不复用旧轨迹/评分；旧 seed 续训保持暂停。

[配置](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/config/run.json) · [日程](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/config/schedule.json) · [预检](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/analysis/preflight.json) · [动态报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/REPORT.md) · [运行状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_seed20261026/STATUS.json)

AutoPanel / TensorBoard run 名称：`appworld-rubric-ZeroFail3-SFT-seed20261026`。训练loss、梯度、学习率、每轮dev57和文档重复指标每30秒从已提交文件导出。

模型仅保留首批、每轮末及最近两批完整检查点；所有轨迹、评分、dataset、metrics和官方报告保留。原有实验模型不清理。最终报告对照原 seed 20261022 的三轮结果。
