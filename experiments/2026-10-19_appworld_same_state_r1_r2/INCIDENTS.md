2026-10-20 00:00:49（北京时间），队列在正式前缀的隔离 evaluator 核验停止；正式模型动作尚未生成。299 个前缀重放的原始反馈均一致，294 个 evaluator 已通过，5 个触发数据库指纹不一致。

原因是 SQL 变更日志恢复时重新组织 SQLite FTS5 全文索引的物理分段。5 例差异仅在 phone/gmail 的 `_fts_data`、`_fts_idx` 内部表；业务表一致。改用活跃数据库的完整 SQLite backup 保存快照，保留所有表的严格一致性检查。相同文件按内容哈希硬链接去重；evaluator 使用独立副本，验证后仅清理该临时副本，原快照保留。

2026-10-20T00:26:07.659434+08:00：5/5 修复验证通过；新重放的全部 before 指纹与原记录完全相同，原失败快照和诊断已保留。299/299 reference evaluator 已齐备。候选状态、prompt、rubric 和评分协议均未改变，未删除或替换状态。见 [修复审计](calibration/snapshot_fix/repair_audit.json)。
