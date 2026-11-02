# 阶段 A：正式实验与助手结果复核完成

> **2026-10-22 正式结果：**99 个 FAIL、25 个干净对照，892 个候选全部执行并评分，99 份无梯度诊断完成；固定 20 状态、144 候选助手复核完成，非独立人工金标。C0/C1/C2/C3 的四层等权 LR 为 13.25%/18.69%/75.15%/63.44%。详见 [正式报告](analysis/formal/REPORT.md)。原版 B 的全部绿灯条件尚未满足；训练和 B/C 均未启动。

以下保留 **2026-10-21 准备阶段的历史说明**；其“尚未执行”等措辞不代表当前状态。当前结果以上方正式报告及根目录 STATUS.json 为准。

执行顺序：

1. 已完成：冻结 100 FAIL + 30 干净对照 + 8 调试状态的抽样及原始文件摘要。
2. 已完成：准备 138 条完整来源轨迹，共 3,429 个实际步骤；凭据等值脱敏；138/138 原动作前 prompt tokens 精确一致。
3. 已完成：8 条调试完整轨迹各用原 v7 和 v7-feedback 评分一次；8 个目标步标签一致，反馈均符合结构和长度要求，已完成助手证据复核。见 [调试报告](calibration/REPORT.md)。
4. 已完成：130 条正式来源轨迹用 v7-feedback 评分，共 3,148 个步骤；另有 1 次纯 JSON 格式修复，实质内容未变化。
5. 已完成：整理 v6→v7 标签变化、反馈可用性、长度、后续证据标记、四组候选输入与共同输出预算。100 个 FAIL 目标均通过准备检查，25 个干净对照保留，5 个不再符合条件；正式最多 900 个待生成动作。
6. 等用户明确开始后：进行状态恢复/执行检查、Qwen 调试和正式候选生成；本轮不会自动进入此步骤。

重新评分后不再含 F 的历史 FAIL 样本保留并标记，不换样。反馈过长或不可用也记录原因。候选输入准备成功只表示文件与上下文预算已检查，不表示环境状态恢复通过，更不表示纠错成功。

本地准备和来源评分命令如下。`--execute` 表示实际远程评分；当前已有本轮用户授权，但不能用它启动 GPU：

```bash
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/prepare_sources.py
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/score_sources.py --stage calibration --execute
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/analyze_sources.py --stage calibration
```

正式来源评分还检查 `calibration/review_gate.json` 中的调试审阅结论；通过后使用 `--stage formal`。脚本按请求摘要复用已成功输出，不因反馈不利重新抽样。

来源 prompt 位于实验根目录 `config/scoring_prompt_v7_feedback_en.txt`。纠错候选的未来盲评使用未修改的 `config/scoring_prompt_v7_en.txt`，只看真实前缀和新动作的实际观察；未知后果保留 U，不能拼接原失败分支后续。

结果入口：

- [准备报告与样本统计](analysis/PREPARATION_REPORT.md)
- [目标步标签及完整反馈](analysis/target_feedback_inventory.csv)
- [全部来源步骤的 v7 标签](analysis/all_source_step_scores_v7.csv)
- [固定 20 状态复核清单](config/manual_audit_states.csv)；本次 [助手证据复核](analysis/formal/assistant_review.json) 单独保存，未覆盖自动标签，独立盲审未完成
- [最终审计](analysis/final_preparation_audit.json)

来源评分完成后的 CPU 整理命令如下；重复执行会核对既有冻结输入，不生成 Qwen 动作：

```bash
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/analyze_sources.py --stage formal
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/finalize_preparation.py
```
