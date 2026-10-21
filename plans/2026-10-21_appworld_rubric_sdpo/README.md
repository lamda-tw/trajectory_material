# AppWorld：rubric 反馈纠错与 SDPO 实验计划

日期：2026-10-21。当前状态：**计划与 CPU 抽样已完成；尚未执行状态重放、模型推理、Codex 评分或训练。**

- [PLAN.md](PLAN.md)：阶段 A 的执行协议、评估及进入阶段 B/C 的条件；阶段 B/C 的训练方案。
- [states_selected.csv](states_selected.csv)：100 个 FAIL 状态与 30 个干净对照，已固定。
- [calibration_states.csv](calibration_states.csv)：8 个独立调试状态，不计入正式结果。
- [selection_audit.json](selection_audit.json)：抽样覆盖、原始文件哈希及统计。
- [protocol.json](protocol.json)：采样条件、预算、门槛和训练建议参数。
- [prompts](prompts)：反馈、重提示与盲评模板。
- [prepare_plan.py](prepare_plan.py)：只读原始轨迹，确定性生成或检查抽样；不调用模型和网络。

在仓库根目录复核已保存的抽样：

```bash
python plans/2026-10-21_appworld_rubric_sdpo/prepare_plan.py --check
```

后续执行器尚未实现。计划中的 A/B/C 执行命令属于待实现接口，不能视为已经跑过的实验。此次准备不修改现有实验或其他计划。
