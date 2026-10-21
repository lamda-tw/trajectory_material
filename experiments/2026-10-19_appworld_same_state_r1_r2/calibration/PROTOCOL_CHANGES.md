# 正式生成前的校准修订

初版8状态卡片/动作评分均保留在 judge_runs/calibration_cards、calibration_actions；完整原prompt与结果另存 protocol_draft_1。未产生正式候选，未查看三组候选输赢。

证据复核发现：

- 6c2c621_2:before_step_04 的首次 file_system 文档发现是有用信息，但没有处理此前 Simple Note 认证问题。初版将它标为必要恢复证据/R6=P，混淆了普通推进和恢复。修订要求恢复明确对应特定既有问题，独立子目标首次推进可计 evidence_gain、R6=N；反馈固定分母不改。
- 396c5a2_3:before_step_15 没有查文档，却被 documentation=unnecessary_given_known_specs 标记。修订限定该标签只用于实际多余文档查询；重复数据读取归 repetition，无缺失规格时 documentation=not_applicable。

以上是统一适用性澄清，不更改v7八项原文或按组别调标准。统一重评全部8个校准状态，存 calibration_cards_v2、calibration_actions_v2；第一份合法结构结果保留，不因语义不满意重抽。
