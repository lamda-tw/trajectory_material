# AppWorld 逐步 rubric 评分实验

更新：2026-10-12（北京时间）。**v3 已完成真实测试**：原六条开发样本、新增两条任务、两条相同输入重评，共 10 次调用；8 条不同轨迹、99 个不同步骤。全部首试通过结构与步骤覆盖验收。

结论：可以继续用于有抽检的小规模 step 标注；存在维度误判、证据过度推断和标签漂移，尚不能把全部输出直接当作训练真值。原开发检查点 28/28，新任务检查点 18/19；重复评分 216/224 个标签一致。这些指标不等于独立准确率。

## 当前入口

- [v3 实测报告](V3_REPORT.md)：结果、反例、稳定性与实际时间。
- [v3 全部逐步结果](review/V3_TRAJECTORIES.md)：每个 step 的 R1—R8 标签和短依据。
- [比较统计](review/v3_comparison.json)、[复核发现](review/v3_review_findings.json)、[最终验证](v3_final_validation.json)。
- [原六条清单](manifest_v3.json)、[新两条清单](manifest_v3_unseen.json)、[新任务预设检查点](review/v3_unseen_checks.json)。
- [调用配置](judge_config_v3.json)、[调用脚本](scripts/run_judge_v3.py)。
- [原六条运行](runs/v3_test/)、[新任务运行](runs/v3_unseen/)、[重复运行](runs/v3_repeat/)。

## 评分协议

每次将一条完整轨迹输入同一个 prompt，输出所有 step 的八维 P/F/U/N 标签和一句主要依据。小样本与未来全量使用同一协议，不设输出模式，不合成 reward 或训练权重。成功和失败轨迹使用相同规则。

模型为 `gpt-5.6-sol / high`，最多同时两个请求；关闭工具和浏览，并核对调用事件。准备输入中去除官方成败和 token/logprob 数组。schema、轨迹 ID、步骤顺序及短依据要求在本地严格验证；结构通过不等于语义正确。

prompt、schema 与输入准备器继续维护在 [plans 目录](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/README.md)，本目录保存冻结快照及实验结果。任何 prompt 修改都须创建新版本，旧结果不覆盖。

在本实验目录进行新调用（必须使用新的运行名）：

```bash
python scripts/run_judge_v3.py --execute --run NEW_RUN_NAME
python scripts/run_judge_v3.py --execute --run NEW_UNSEEN_RUN --manifest manifest_v3_unseen.json
```

## 历史结果

[v1/v2 报告](REPORT.md) · [v1/v2 逐轨迹对照](review/TRAJECTORIES.md) · [v1/v2 统计](review/comparison.json)。历史文件中的 audit/batch 仅描述当时版本，v3 已取消。历史输入转换与调用问题保留在原报告，本轮没有重放轨迹、训练或覆盖任何旧评分。
