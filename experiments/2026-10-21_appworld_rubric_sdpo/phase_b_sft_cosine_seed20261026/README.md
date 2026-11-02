# 同 seed 纯 ZeroFail3 SFT：余弦学习率三轮对照

当前用户授权：GPU1、与上一实验相同 seed=20261026、从原始 Qwen3-8B 重新开始三轮，训练因素只改变学习率；无人值守自动处理基础设施异常；尽量少保存模型。

前5次有效更新和恒定学习率对照完全相同，warmup到5e-5；第6–54次按不重启余弦逐步降至5e-6。不是每轮边界跳变。第18/36/54批分别评估dev57。每轮90题、每批5题、每题一条完整在线轨迹，完成后Codex v7逐步评分，只有F=0且P>=3做SFT。所有FAIL屏蔽，SDPO loss为0。LoRA r8、alpha16；其余训练/生成参数及任务顺序不变。

[实时中文进度](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/PROGRESS.md) · [状态](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/STATUS.json) · [心跳](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/runs/sft/heartbeat.json) · [对比报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/REPORT.md) · [预检](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/preflight.json)

AutoPanel run：`appworld-rubric-ZeroFail3-SFT-cosine-seed20261026`。每约30秒追加已提交批次loss、梯度、学习率，每轮追加dev57和行为指标。与`appworld-rubric-ZeroFail3-SFT-seed20261026`对比。

只保留最新可续训完整状态与已评估最优轮次（按成功题数、Macro、较早轮次依次选择），重合只存一份。新检查点安全提交并验收后才删除旧权重；保留全部轨迹、评分、指标和评估报告。旧实验文件不动。

[学习率曲线](/root/autodl-tmp/workspace-tw/experiments/2026-10-21_appworld_rubric_sdpo/phase_b_sft_cosine_seed20261026/analysis/learning_rate_schedule.png)；具体公式、54个更新的数值见config/learning_rate_schedule.json。有效更新计数来自检查点，空batch不推进，进程重启不重置。

正式比较基线为phase_b_sft_seed20261026的三轮。相同seed不意味着新采轨迹和外部Codex评分完全一致；后续在线轨迹差异是学习率改变后的下游结果。不得复用旧数据冒充在线采样。
