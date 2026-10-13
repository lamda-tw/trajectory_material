# AppWorld 逐步 rubric 评价

既有540条评分的冻结版本为 **v5**。已完成原始 Qwen3-8B 的全部 540 条训练集轨迹、11,254 步评分，纯评分用时 1 小时 52 分 51 秒；可作为离线诊断与候选 step 筛选基线。没有证明总体准确率超过 95%，不直接视为精确 reward 或训练真值。历史 pilot 为 12 条、201 步及两次重复调用。

一条完整轨迹调用一次，成功和失败轨迹均逐步评价R1—R8；保留P/F/U/N与一句短依据，不计算总分、reward或固定权重，不设audit/batch模式。v5共2,111字符，适用边界直接写在唯一Evaluation Rubrics模块中。

| 文件 | 用途 |
| --- | --- |
| [prompt_v5.txt](prompt_v5.txt) | 当前冻结提示词 |
| [prepare_input_v3.py](prepare_input_v3.py) | 沿用统一输入适配器，不改变轨迹证据 |
| [output_schema_v5.json](output_schema_v5.json) | 三列输出结构 |
| [validate_output_v5.py](validate_output_v5.py) | 校验版本、格式、步骤覆盖和短依据 |
| [VERSIONS.md](VERSIONS.md) | 不可覆盖的各版本记录 |

```bash
python prepare_input_v3.py SOURCE.json INPUT.json --trajectory-id base:TASK__SAMPLE
python validate_output_v5.py INPUT.json RESPONSE.json
```

替换prompt中唯一的`{{TRAJECTORY_JSON}}`后调用judge；不附官方成败或检查点。保存输入、prompt、模型和推理强度。输出结构通过不代表语义正确。

[v5实测报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/V5_REPORT.md) · [逐步结果](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/review/V5_TRAJECTORIES.md) · [逐项复核](/root/autodl-tmp/workspace-tw/experiments/2026-10-12_appworld_step_rubric_pilot/review/v5_quality_summary.json)。

相同52项开发回归由v4的47项符合提高到v5的50项，新任务36/39。仍有F/U边界、局部/全局覆盖和协议漏判。总体判断大多可用，不继续追求完全一致；不要将未知直接作为错误或把这些标签视为独立真值。完整复核的分母和限制见报告。

历史 pilot 当时准备了 540 条输入并评分 12 条；现已在独立全量实验中重新评分全部 540 条，未复用 pilot 输出。所有 v1—v4 文件与结果保留，今后任何 prompt 修改须建立新版本。


2026-10-13：用户确认暂时冻结v5，用于原始Qwen3-8B的540条AppWorld训练集采样轨迹。[本次全量实验](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/README.md)独立保存，新跑全部540条；历史pilot保留。评分与后续评价分开计时。

全量实验已完成：[详细报告](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/REPORT.md) · [逐步评分](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/analysis/step_labels.csv) · [抽样复核](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_qwen3_8b_step_rubric_v5_full/review/MANUAL_REVIEW.md)。540 条全部有效，2 次格式重试；冻结 prompt 内容和原始评分保持不变。

后续评分新增 [prompt_v6.txt](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/prompt_v6.txt)，配套 output_schema_v6.json / validate_output_v6.py。v6 将上述边界直接整合进唯一 rubric 模块，保持简短输出；尚未实测，不回写540条v5标签。版本依据见 [VERSIONS.md](/root/autodl-tmp/workspace-tw/plans/2026-10-12_appworld_step_rubric/VERSIONS.md)。

后续训练实验：[只使用既有动作的 LoRA 局部 SFT 对照方案](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/PLAN.md)。两组按题匹配监督 token，训练后统一 DEV57；训练策略不调用新 judge 或替代动作教师。

上述训练对照已完成：[完整结果与策略讨论](/root/autodl-tmp/workspace-tw/experiments/2026-10-13_appworld_rubric_local_sft_vs_uniform/REPORT.md)。DEV57：base 3/57、uniform 6/57、rubric 4/57；本轮固定硬筛选未优于同预算均匀抽样，不能将质量标签直接等同于学习价值。v5评分不变。
