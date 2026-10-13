# Qwen3-8B AppWorld 540 轨迹 v5 全量评分

**已完成。** 全新评分 540/540 条轨迹、11,254 个 step、90,032 个 rubric 分项。纯评分用时 **1 小时 52 分 51 秒**；官方对照、语义复核和报告单独计时。完整结论见 [REPORT.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md)。

冻结 prompt_v5，SHA256 `bc6335bf245b1c0991970662bad230cd30d6ae04c0e7e8fb8af0e1d57c70de4b`。使用 gpt-5.6-sol/high，一条完整轨迹一次请求，并发 2→4→8；共 542 次调用，2 次格式失败重试后全部成功。原始评分及 prompt 未根据复核改写。

本次调用使用服务器 Codex CLI 已登录的 ChatGPT 账号，脱敏标识 `qz***@gmail.com`；电脑端是否同账号无法核对。全部评分 input 11,754,719 tokens、output 2,555,901 tokens，含失败重试，不含后续评估对话。认证来源见 [AUTH_PROVENANCE.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/AUTH_PROVENANCE.json)，不保存认证秘密。

| 入口 | 内容 |
| --- | --- |
| [REPORT.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md) | 详细报告、质量边界与下一步学习实验建议 |
| [scored_trajectories.jsonl](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/scored_trajectories.jsonl) | 540 条完整评分汇总 |
| [step_labels.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/step_labels.csv) | 11,254 行 step 评分 |
| [trajectory_metrics.csv](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/trajectory_metrics.csv) | 轨迹统计及评分后官方对照 |
| [step_candidates.jsonl](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/step_candidates.jsonl) | 6,381 个不同候选 step，非训练真值，权重为 null |
| [MANUAL_REVIEW.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/MANUAL_REVIEW.md) | 预先抽样的 12 条完整轨迹、176 步复核 |
| [SUPPLEMENTAL_REVIEW.md](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/SUPPLEMENTAL_REVIEW.md) | 额外定向诊断，不并入抽样质量率 |
| [TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/TIMING.json) | 已关闭的纯评分计时 |
| [EVALUATION_TIMING.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/EVALUATION_TIMING.json) | 独立评估与报告计时 |
| [COMPLETION_CHECK.json](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/COMPLETION_CHECK.json) | 完成校验和文件哈希 |

`assets/` 保存冻结 prompt、schema 和输入适配器；`runs/scoring/<id>/` 保留请求、输入、原始模型响应、事件、全部尝试与最终首次有效评分。`research/official_outcomes.json` 仅在评分后用于分析，不进入 judge 输入。没有复用旧 pilot 结果、没有执行轨迹代码、没有启动训练。

v5 可作为离线诊断/候选筛选基线；八维 P/F/U/N 不合成固定总分。抽样复核不能证明总体准确率超过 95%，R7=P 也不能替代官方成功奖励。下一步应检验局部训练的效果，无需因追求完美 prompt 全量重跑。未来 prompt 修改须新建版本。
