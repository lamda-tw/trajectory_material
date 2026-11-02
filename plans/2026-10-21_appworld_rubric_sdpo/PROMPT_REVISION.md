# v2 修订：整轨迹评分，v7 只扩展反馈输出

本修订落实用户意见，并取代 [上一版计划](archive/v1/PLAN.md)中的局部反馈生成器与新写的单步评审 prompt。当前执行方案见 [PLAN.md](PLAN.md)。没有调用 judge 或训练。

## 保留什么

以 [原英文 v7](../2026-10-12_appworld_step_rubric/prompt_v7_en.txt) 为基础，评分器角色、评价证据、P/F/U/N 规则、R1–R8 定义逐字保持不变；中文版本也保留对应原文。输入仍是一整条实际轨迹，一次返回每个 step 的标签。旧三列 steps 与短理由长度上限保持不变。

v7 目录的早期 provenance 写着“候选、尚未评分验证”；后来同状态机制实验的计划引用了 v7 的八项定义。两件事不矛盾，但都不能证明本次新增反馈有用，也不能把新扩展称为已经验证过的 prompt。

## 只扩展输出

输出增加 `feedback_version` 和 `feedback`，每个需要反馈的 F 步骤包含：

```json
{
  "step_id": 12,
  "failed_rules": ["R2"],
  "diagnosis": "The conclusion treated the records already retrieved as complete, but later observations establish that relevant records were omitted.",
  "correction": "Complete the relevant pagination and verify the required scope before relying on an all-records conclusion.",
  "evidence_steps": [12, 15],
  "uses_later_evidence": true,
  "usable": true,
  "unusable_reason": ""
}
```

这只是输出示例，不对应真实任务。具体 `failed_rules` 必须与该次评分的 F 维度完全一致。保留原三列的代价是 schema 需要增加两个顶层字段；旧 validator 不能直接吃扩展对象，但提取 `trajectory_id/rubric_version/steps` 后仍符合原 v7 输出契约。配套 [新 schema](output_schema_v7_feedback.json) 和 [本地校验器](validate_v7_feedback.py)检查覆盖、对应关系、引用步骤与长度。

可选输入字段 `feedback_step_ids` 控制反馈范围，不改变评分范围：A 只为选中目标步写反馈，B/C 为全部含 F 步骤写反馈。无 F 不编造反馈。所有评分和反馈在同一次整轨迹调用中返回。

## 修正原计划中的两个限制

1. **评分时机与评分粒度不同。** 每个 step 有标签，不意味着每执行一步就调用一次 Codex。B/C 让一条轨迹先结束，再一次性评分；一批 5 条轨迹对应 5 个正常逻辑评分请求，随后按步骤构造损失。
2. **事后反馈与当时已知信息不同。** 教师可以接收训练轨迹的事后诊断；评分不能把后来发现的信息倒算成学生当时已经知道。反馈要指出该补什么证据或改什么约束，不能假装后来创建的变量/写入已存在。来源 F 不再因引用后续观察而被剔除，相关样本另行分组报告。

## 用户确认的阶段 A 范围

新纠错候选只执行一步，然后统一离线评审。原来源轨迹完整输入 v7-feedback；纠错候选只能输入该分支真实的“前缀＋候选＋实际 observation”，并标明诊断预算结束。用原 v7 评分，未知后果为 U；绝不拼接旧分支的未来。

因此主指标改为“局部违规修复率”，不再用一个新增 progress judge 声称全部候选都有效推进了任务。固定人工复核检查停滞/回避工作，最终任务收益留到后续训练评估。

## 先验证，再使用

先在独立的 8 条调试完整轨迹上各运行一次原 v7 和 v7-feedback；检查标签/F-U 转换及反馈可执行性，不能凭本地格式通过宣称语义有效。本轮只完成本地检查。

```bash
python plans/2026-10-21_appworld_rubric_sdpo/build_v7_feedback.py --check
python plans/2026-10-21_appworld_rubric_sdpo/prepare_plan.py --check
```

生成器仅扩展 Output，逐字校验前面的所有模块。来源文件和已有实验 prompt 没有被覆盖；固定抽样清单保持不变。
