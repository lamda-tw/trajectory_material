# AppWorld step rubric 实验

当前版本 **v5**：建议冻结为全量离线探索标注基线，保留已知噪声；尚未证明总体95%准确率。本轮测试12条完整轨迹、201步，另两次重复调用；没有启动540条全量评分或训练。

[v5报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V5_REPORT.md) · [逐步评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/review/V5_TRAJECTORIES.md) · [复核记录](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/review/v5_quality_summary.json) · [正式prompt](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/prompt_v5.txt)。

回归检查50/52、新任务36/39；这些是开发检查而非独立准确率。具体证据复核、重复差异、限制和成本见报告。成功与失败轨迹均使用同一prompt、一次调用和统一三列输出，无权重、总分或audit/batch模式。

`manifest_v5_corpus.json`登记540条输入，`v5_scored_index.json`保留12条首次有效v5结果，`manifest_v5_remaining.json`登记528条未评分输入。准备输入不等于已经评分；旧v4结果不可改名混用。

复查现有实验：`python scripts/analyze_v5.py`；只整理原始结果展示：`python scripts/render_v5.py`。所有模型调用的请求、输入、配置、哈希和原始输出保存在`runs/v5_*`；旧版文件均保留。

[v4历史报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V4_REPORT.md) · [v3历史报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V3_REPORT.md) · [v1/v2历史报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/REPORT.md)。
