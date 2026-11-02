# AppWorld rubric 反馈纠错与 SDPO：A/B/C 实验

建立日期：2026-10-21（Asia/Shanghai）。三个阶段统一放在本目录。

| 阶段 | 目的 | 当前状态 |
|---|---|---|
| [A](phase_a/README.md) | 用现有 FAIL 状态检验 Qwen3-8B 能否利用 Codex 反馈纠错 | 892 个正式动作及 99 份分布诊断完成；固定样本助手复核与正式报告已完成 |
| [B](phase_b/README.md) | 在线 v7-ZeroFail3 SFT ＋ FAIL-SDPO 及分支对照 | 混合、纯 SDPO、纯 SFT 均完成两轮和每轮 dev57；[三组正式比较报告](THREE_ARM_COMPARISON_REPORT.md)已完成 |
| [C](phase_c/README.md) | 冻结配置后的多种子正式比较 | 未启动 |

2026-10-26 最新结果：混合两轮 dev57 成功数为 5→1，纯 SDPO 为 2→0，纯 ZeroFail3 SFT 为 7→12。三个分支均按后续用户授权完成，纯 SFT 于 2026-10-25 23:17:40（UTC+8）结束。本次仅对现有结果做 CPU 复核和汇报，不启动新训练；阶段 C 仍未启动。详细数据、重复文档行为、具体案例和下一步建议见 [三组正式比较报告](THREE_ARM_COMPARISON_REPORT.md)。各分支原始报告与授权记录保留为历史证据。

- [混合原始报告](phase_b/REPORT.md)
- [纯 SDPO 原始报告](phase_b_sdpo_only/REPORT.md)
- [纯 SFT 自动报告](phase_b_sft_only/REPORT.md)
- [三组对比图](phase_b_sft_only/analysis/three_arm_review/three_arm_overview.png)
- [三组核验汇总](phase_b_sft_only/analysis/three_arm_review/summary.json)

- [冻结的 A/B/C 计划](plan_snapshot/PLAN.md)
- [v7 反馈修订说明](plan_snapshot/PROMPT_REVISION.md)
- [来源、prompt 与代码摘要](config/frozen_source_manifest.json)
- [本轮执行范围](config/authorization.json)
- [执行约束与当前校准边界](EXECUTION_NOTES.md)
- [Codex 评分配置](config/judge.json)
- [阶段 A 来源输入审计](phase_a/config/source_manifest.json)
- [阶段 A 准备报告](phase_a/analysis/PREPARATION_REPORT.md)
- [2026-10-22 执行记录与恢复入口](phase_a/EXECUTION_HANDOFF_2026-10-22.md)
- [2026-10-22 调试结果](phase_a/analysis/calibration/REPORT.md)
- [2026-10-22 正式结果与进入 B 的判断](phase_a/analysis/formal/REPORT.md)
- [目标步标签与完整反馈清单](phase_a/analysis/target_feedback_inventory.csv)

阶段 A 固定 100 个历史 FAIL、30 个干净对照、8 个调试状态，共 138 条不同来源轨迹，覆盖 train90。原历史 v6 标签用于固定抽样；本次整轨迹重新用 v7 评分，另存标签与目标步反馈，不覆盖旧实验。

来源评分已完成：8 条调试轨迹的双版本对照，以及 130 条正式轨迹的 v7-feedback 评分。100 个正式 FAIL 目标均取得符合结构、长度和上下文预算的反馈；干净对照有 25 个仍符合条件，另 5 个在 v7 下出现 F，保留记录但不进入中性反馈对照。2026-10-22 状态恢复另排除 1 个 FAIL 状态，892 个正式动作均已生成、执行和评分。四层等权 LR：C0 13.25%、C1 18.69%、C2 75.15%、C3 63.44%。具体反馈有效；干净对照和错误前缀下的教师分布限制仍保留。用户选择以局部 step 改善为目标，已授权 B 混合训练。

CPU 准备使用本地 tokenizer 重建输入；不加载模型权重。用于凭据脱敏的 AppWorld 初始任务读取仅在隔离本地目录执行，不加载 ground truth，不执行源轨迹，不把账户登记内容加入评审证据。

`phase_a/inputs`、`phase_a/judging`、`phase_a/ready` 与 `runtime` 包含本地原始材料或执行上下文，已由本目录 `.gitignore` 排除；反馈原始输出仍保留，失败与重试不覆盖。评分服务的所有工具均禁用。

目前脚本支持准备、来源评分、状态恢复、候选生成与执行、原 v7 离线评分、配对统计和无梯度分布诊断。阶段 A 不进行训练。

2026-10-26 后续授权：纯 SFT 从第二轮完整状态续训至第五轮，使用 GPU1，每轮评估 dev57，并接入 autopanel；详见 [五轮续训目录](phase_b_sft_extend5/README.md) 和 [五轮报告](phase_b_sft_extend5/REPORT.md)。
