# 第3步：单步修复的实际验证

**状态：已完成，3次尝试全部通过官方评分，扩大采集门槛已满足。** 本步没有训练模型。

## 做了什么

先在5个冻结候选上分别新建AppWorld环境，重放替换点之前的原学生动作。共重放57步；凭证脱敏、JSON格式归一后，每一步环境返回都与第一步原日志一致。这个检查先于教师调用完成。

正式验证时，每题再次从干净环境重放前缀。教师固定为 **Codex gpt-5.6-sol，high reasoning effort**，只看到候选动作之前的原始学生消息，环境凭证已脱敏；它没有看到被替换的学生动作、后续轨迹、第2步诊断、官方失败条件、评估断言或ground truth。教师给出一个动作，随后由原 **Qwen3-8B + train90 LoRA第5轮adapter** 按temperature=0、seed=100、32,000上下文、每次最多3,000输出tokens、整题最多50步继续。

每题最后都由AppWorld官方评估器评分。达到3条成功后按预定停止规则结束，两个备选没有运行。

## 实际结果

| 顺序 | 任务 / 替换点 | 教师动作的作用 | 学生后续动作 | 官方评分 |
| --- | --- | --- | --- | --- |
| 1 | ccb4494_2 / 第6步 | 重新读取完整歌曲队列，为学生保留准确位置状态 | 4步：学生自己筛选已播放歌曲、点赞并完成任务 | 5/5，通过 |
| 2 | 302c169_2 / 第11步 | 提前Wake Up闹钟，并用更新接口停用其余启用闹钟 | 3步：学生检查最终闹钟状态并完成任务 | 8/8，通过 |
| 3 | 60d0b5b_1 / 第14步 | 精确筛选Robert的已批准请求，用最新一笔金额退款 | 2步：学生调用完成接口 | 7/7，通过 |

合计3次教师调用、9个学生续跑动作，官方断言20/20通过。三次均有学生在教师动作之后继续，因此不是教师独自跑完整条轨迹。所有教师审计事件都只有`agent_message`，没有命令、文件、MCP或网页工具调用；适配器权重SHA-256仍为`c8fdfd4f3bb198381b6f2e56d019589a3ed904241b0147b565ec540449a29938`。

这说明“恢复到真实错误前缀 → 提供一个教师动作 → 同一学生继续 → 官方成功”这条数据生产链已经跑通。它还不能说明训练这些动作会迁移到其他任务，也不能说明状态、参数、恢复三个标签已经构成独立能力。

## 产物怎么读

- [结果汇总](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/summary.json)：3条成功记录和官方分数。
- [前缀重放核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/prefix_validation.json)：5个候选、57步逐步对照。
- [最终一致性核验](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/validation.json)：53项证据、泄漏边界、预算和评分检查，全部通过。
- [第1条完整尝试](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/attempts/rank1_ccb4494_2/result.json)、[第2条完整尝试](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/attempts/rank2_302c169_2/result.json)、[第3条完整尝试](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/attempts/rank3_60d0b5b_1/result.json)：定位教师请求、学生请求/响应、逐步交互和官方报告。
- [产物校验值](/root/autodl-tmp/workspace-tw/experiments/2026-09-28_dynamic_cfst/step03_repair_validation/artifact_sha256.json)：除运行缓存和服务日志外的文件SHA-256。

下一步是扩大来源侧的已验证修复集合。当前按第2步暂定主标签计数为状态2条、参数1条、恢复0条；应继续从冻结的来源60题审查和验证，不使用检查30题生成训练答案。达到每类计划数量并重新核对标签之后，再整理训练组和等量随机对照。

[当前滚动待办](/root/autodl-tmp/workspace-tw/plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md)
