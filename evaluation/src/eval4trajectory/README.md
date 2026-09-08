# eval4trajectory

读取 Codex/Agent 导出的 HTML 轨迹，以确定性规则实现 56A09AQ 轨迹规则第 11 章推荐的 12 项指标。

```powershell
$env:PYTHONPATH = "evaluation/src"
python -m eval4trajectory list
python -m eval4trajectory evaluate `
  --trajectory "trajectories/VIP用户轨迹分析/Leong Weng Wah 00714422/56A09AQ 项目物料盘点与缺货风险_2026-07-15.html" `
  --output "assessments/56A09AQ-trajectory"
```

输出：

- `score_result.json`
- `business_report.md`
- `feedback_trace.csv`
- `evidence_detail.csv`
- `gate_failures.json`
- `regression_cases.json`
- `improvement_actions.md`

12 项 MVP 沿用完整规则中的原始权重，总满分 50。报告同时提供：

- `raw_score`：12 项原始得分；
- `evaluated_max_score`：轨迹中存在充分通过/失败证据的项目满分；
- `normalized_score`：仅按已评价项归一化到 100；
- `coverage`：已评价满分占 50 分的比例。

没有观察到证据的指标标记为 `not_observed`，不会因为“用户没报错”就自动判满分。

