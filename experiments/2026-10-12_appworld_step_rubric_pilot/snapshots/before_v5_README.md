# AppWorld 逐步 rubric 评分实验

更新：2026-10-12（北京时间）。当前候选 **v4** 已完成真实抽样，尚不建议作为全部 540 条轨迹的正式固定评分器。

主实验使用 gpt-5.6-sol / high：15 条不同轨迹、13 道题、12 类任务、279 步，另做三条重复评分，共 18 次完成；补充 medium 对照 4 次。合计 22 次完成、23 次尝试，其中一次模型容量繁忙失败。

回归检查 48/50，新任务检查 40/43，执行错误和只读适用性检查 312/312。v4 修复了若干具体反例，但相同两条输入的重复一致性从 v3 的 216/224 降为 204/224；medium 为 197/224。检查点符合率不能代替稳定性或独立准确率。

## 当前入口

- [v4 完整报告](V4_REPORT.md)：优化内容、抽样、重复性、成本与暂不全量的依据。
- [v4 全部逐步结果](review/V4_TRAJECTORIES.md)、[主实验比较](review/v4_comparison.json)、[medium 对照](review/v4_medium_comparison.json)。
- [残余问题](review/v4_residual_findings.json)、[最终验证](v4_final_validation.json)。
- [全量输入检查](v4_corpus_preflight.json)、[540 条清单](manifest_v4_corpus.json)、[剩余 525 条清单](manifest_v4_remaining.json)、[15 条已评分索引](v4_scored_index.json)。
- [high 配置](judge_config_v4.json)、[v4 调用脚本](scripts/run_judge_v4.py)。

## 统一协议与版本维护

每次输入一条完整轨迹，输出全部 step 的八维 P/F/U/N 标签和一句主要依据。成功和失败轨迹使用同一标准，没有 audit/batch 模式，不合成 reward 或权重。

唯一可维护的 prompt、schema 和验收器位于 [plans 目录](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/README.md)。本目录保留冻结输入、prompt、原始响应、事件与用量。任何 prompt 修改须新建版本；本轮 v4 在测试中没有修改。

540 条输入已在本地准备并校验哈希；最大约 52.8 万字符及 50 步轨迹已完整实测。剩余 525 条没有进行模型评分，全量运行命令仅作为准备好的入口保存在 v4 报告中。

## 历史资料

[v3 报告](V3_REPORT.md) · [v3 逐步结果](review/V3_TRAJECTORIES.md) · [v1/v2 报告](REPORT.md)。所有历史结果保持不变。
