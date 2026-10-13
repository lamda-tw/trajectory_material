# Rubric 局部动作五轮双卡 SFT

实验已完成。全新LoRA、相同2,440个rubric目标，5轮、6,100次更新、983,040监督token。DEV57官方成功：**第1轮 13/57，第3轮 10/57，第5轮 8/57**。本次观察中第1轮最高；loss下降不代表DEV成功率持续提升。

[完整报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/REPORT.md) · [五轮loss图](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/analysis/loss_5epochs.png) · [逐题比较](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/analysis/task_comparison.csv) · [最终adapter](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/training/rubric/adapter) · [用时](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_epoch5_ddp/TIMING.json)

本次第1、3、5轮独立保存并分别完成DEV57，见CHECKPOINTS_135.json和完整报告。本次使用历史五轮SFT配方，未接续旧adapter，未调用外部模型改动作。与旧一轮的差异不只epoch，且未训练五轮uniform组。
