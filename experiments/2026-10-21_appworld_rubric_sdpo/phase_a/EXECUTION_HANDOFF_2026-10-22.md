> 后续更新：评分已通过纯本地恢复，32/32 有效且没有新增评分请求。调试技术验收已通过，见 [调试报告](analysis/calibration/REPORT.md)。下文保留先前阻塞过程。

# 阶段 A 首次执行记录与恢复入口

2026-10-22 用户明确授权 GPU1 开始阶段 A。本次已完成以下工作，没有更新模型参数：

- GPU1 的 UUID 与原配置一致，启动时没有占用进程。GPU0 未使用。
- 8 个调试状态各独立恢复两次，8/8 通过：历史 observations、完整动作前状态指纹和 API 请求/响应记录一致。
- 基础 Qwen3-8B 未加载 adapter，四组共 32 个调试候选已生成；实际 prompt token IDs 与准备记录一致。
- 32/32 个候选均完成隔离动作执行，并通过动作前状态核对。模型本身的执行错误保留为结果，没有重采样。
- 125 个正式准备样本完成双重恢复，124 个符合条件。`state_55532d6f4a44f323` 的历史 step 5 observation 不一致，保留并排除，不换样。
- 首个无梯度教师分布调试已完成：相同分布 KL 为 0，原回答 log-prob 与来源 vLLM 记录的平均绝对差约 2.3e-6。其余正式分布检查未运行。当前尾部概率实现使用 FP32 差值，接近 1 的 top-100 质量存在数值精度限制，正式检查前应审阅。

## 离线评分情况

32 个调试评分请求已结束，旧审计器记录 24 个 valid、8 个 protocol failure。已检查的失败类型是 CLI 的 `Falling back from WebSockets to HTTPS transport...` 传输通知被误当作工具调用；这些请求已有完整 JSON 返回。不能把该审计失败算作 Qwen 失败，也不能未经恢复核验就声称全部评分通过。

修正后的严格审计位于 `runtime_code/a_judge_audit.py`，调用入口为 `scripts/a_judge_v2.py`：仅放行已核实的传输回退通知，仍拒绝真实工具调用。原 v7 prompt 和已有候选不变。该入口复用并重新校验首次完整返回，不因效果好坏重评分。

恢复入口（在工作区根目录执行）：

```bash
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/a_judge_v2.py --stage calibration
.conda-training/bin/python experiments/2026-10-21_appworld_rubric_sdpo/scripts/a_analyze.py --stage calibration
```

这两个步骤尚未成功执行完成：启动恢复命令的自动审批连续超时，允许的一次重试也未通过。返回原因是审批没有在期限内完成，并非认定该操作不安全。此前独立运行的 Qwen 生成、分布调试和环境重放进程均已结束；没有启动正式候选生成、正式动作执行、B/C 或训练。

## 继续执行前的检查

1. 恢复并核验全部 32 个评分，审阅目标标签和实际观察；助手复核不能称为独立人工金标。
2. 记录盲评局限：反馈 prompt 和条件字段未交给评委，但部分候选自己的 commentary 提及反馈；保留真实原文。
3. 保存调试验收与正式运行器摘要，建立 `phase_a/config/calibration_execution_gate.json` 后才允许正式候选生成。当前该门尚未放行。
4. 按 `formal_replay_eligibility.json` 使用可恢复样本，不替换排除项；正式生成继续使用冻结的 prompt、种子和预算。
5. 继续单步执行、原 v7 离线评分、配对家族 bootstrap、固定复核清单和无梯度分布检查。阶段 B/C 需另行决定。

输入、模型文件摘要和版本见 `phase_a/config/model_manifest.json`；恢复审计见 `phase_a/config/*_replay_eligibility.json`；候选缓存见 `phase_a/generations/calibration/`；实际执行见 `phase_a/execution/`；原评分返回见 `phase_a/judging/candidate_calibration/`。以上结果保留，可从缓存恢复。
