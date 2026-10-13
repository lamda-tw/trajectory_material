# AppWorld 逐步 rubric 评价

更新：2026-10-12。当前候选为 **v4**，已完成抽样与重复性实测。运行流程可以处理全量输入，但语义稳定性尚未通过本轮复核，不建议直接作为 540 条轨迹的正式固定标签来源。

## 当前方案

每次输入一条完整轨迹，按 R1—R8 评价所有实际 step。成功与失败轨迹使用同一标准，保留 P/F/U/N，不合成总分或训练权重。统一输出 `[step_id, 八字符标签串, 简短依据]`；含 F/U 时一句话说明主要问题，不设 audit/batch 模式。

v4 在各条 rubric 中直接收紧适用性、错误隔离、部分执行后的重试及证据边界，没有附加补丁模块。正文 2,152 字符。输入协议与 v3 相同，继续使用原 v3 适配器。

## 文件与调用

| 文件 | 用途 |
| --- | --- |
| [prompt_v4.txt](prompt_v4.txt) | 当前候选提示词，测试后保持原文不变 |
| [prepare_input_v3.py](prepare_input_v3.py) | 从原始轨迹准备统一输入，无模型调用 |
| [output_schema_v4.json](output_schema_v4.json) | v4 三列输出结构 |
| [validate_output_v4.py](validate_output_v4.py) | 本地验证输出、步骤覆盖及短依据 |
| [VERSIONS.md](VERSIONS.md) | 各版本修改与实验结果 |

```bash
python prepare_input_v3.py SOURCE.json INPUT.json --trajectory-id base:TASK__SAMPLE
python validate_output_v4.py INPUT.json RESPONSE.json
```

替换 prompt 中唯一的 `{{TRAJECTORY_JSON}}` 后调用 judge；不附官方成败、训练数组或检查点。调用日志须保存模型、推理强度和实际 prompt/输入；结构通过不代表语义正确。

## v4 实测状态

[v4 报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V4_REPORT.md) · [逐步结果](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/review/V4_TRAJECTORIES.md)。

主实验覆盖 15 条不同轨迹、279 步，回归检查 48/50、新任务 40/43，312 个执行/适用性机械检查均符合；这些不是独立准确率。与 v3 相同的两条输入重评，v4 high 一致性为 204/224，低于 v3 的 216/224；medium 诊断为 197/224，未解决问题。

v3 的提交误判、部分执行后重试及覆盖参数推断问题有所修复，但未知证据被判为确定错误、恢复判定和 R3 事实口径仍不稳定。下一次修改应另建 v5，优先验证这些边界，不能覆盖 v4 后继续沿用同一版本号。

实验目录已准备 540 条输入，剩余 525 条尚未评分。全量入口可运行不等于当前质量已获验证。

## 历史资料

[v3 实测报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V3_REPORT.md) · [v1/v2 报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/REPORT.md) · [初版设计说明](DESIGN_NOTES.txt)。旧 prompt、schema 和历史评分均保留。
