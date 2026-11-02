# AppWorld：rubric 反馈纠错与 SDPO 实验计划

日期：2026-10-21。当前版本：v2。**计划、CPU 抽样和 v7 反馈扩展的本地检查已完成；尚未执行状态重放、模型推理、Codex 评分或训练。**

采用完整轨迹结束后一次性评分与生成反馈。阶段 A 候选按用户选择只纠错一步，执行后统一离线评审，未知后续效果保留 U。原 v7 评分规则不改，只扩展输出反馈；上一版自写的局部评分/反馈 prompt 已停用。

- [PLAN.md](PLAN.md)：阶段 A 的执行协议、评估及进入阶段 B/C 的条件；阶段 B/C 的训练方案。
- [PROMPT_REVISION.md](PROMPT_REVISION.md)：本次修订的边界、示例及评分时机说明。
- [states_selected.csv](states_selected.csv)：100 个 FAIL 状态与 30 个干净对照，已固定。
- [calibration_states.csv](calibration_states.csv)：8 个独立调试状态，不计入正式结果。
- [selection_audit.json](selection_audit.json)：抽样覆盖、原始文件哈希及统计。
- [protocol.json](protocol.json)：采样条件、预算、门槛和训练建议参数。
- [英文 v7-feedback](prompts/scoring_prompt_v7_feedback_en.txt)、[中文对照版](prompts/scoring_prompt_v7_feedback_zh.txt)：只扩展原 v7 的输出模块。
- [teacher_reprompt_v2.txt](prompts/teacher_reprompt_v2.txt)：教师/纠错候选的四组输入构造。
- [output_schema_v7_feedback.json](output_schema_v7_feedback.json)、[validate_v7_feedback.py](validate_v7_feedback.py)：新增反馈的结构与对应关系检查。
- [v7_feedback_provenance.json](v7_feedback_provenance.json)：原文不变部分、来源与生成文件哈希。
- [v7_feedback_local_validation.json](v7_feedback_local_validation.json)：结构、原 v7 输出兼容、后续证据标记和 Qwen token 上限的本地检查；不代表反馈语义已经验证。
- [prepare_plan.py](prepare_plan.py)：只读原始轨迹，确定性生成或检查抽样；不调用模型和网络。

在仓库根目录复核已保存的抽样：

```bash
python plans/2026-10-21_appworld_rubric_sdpo/prepare_plan.py --check
python plans/2026-10-21_appworld_rubric_sdpo/build_v7_feedback.py --check
```

后续执行器尚未实现。计划中的 A/B/C 执行命令属于待实现接口，不能视为已经跑过的实验。此次准备不修改现有实验或其他计划。
