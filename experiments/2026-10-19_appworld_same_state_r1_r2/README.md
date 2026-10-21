# 全规则1358 / DropR1 / DropR2 同状态动作比较

实验节点更新时间（北京时间）：2026-10-20T06:28:12.549959+08:00

**当前节点：evaluator与报告；complete。** 第一阶段已完成；结果见 REPORT.md。未运行旧ZeroFail3、可选续跑。

9个已有adapter：全规则1358（DropR5）、DropR1、DropR2，各seed 20261015/16/17。299个正式状态：主面板171，E/R/D/S各32。校准8状态不入正式统计。仅物理GPU1；无新训练，不运行旧ZeroFail3或可选续跑。

| 节点 | 状态 | 说明 |
| --- | --- | --- |
| 授权与GPU1核对 | complete | 物理GPU1显存0MiB，无计算进程；UUID已冻结。 |
| 输入token核验 | complete | 299正式+8校准状态全部逐token等于原轨迹。 |
| 双重重放校准 | complete | 8状态双重重放通过。 |
| 评分校准与协议冻结 | complete | 8/8重放、评分语义校准通过；协议已冻结。隔离evaluator变更探针捕获答案检查0→1；校准不并入正式结果。 |
| 299张正式前缀卡 | complete | 299/299卡片已冻结；机会分母不随候选变化。 |
| 正式状态重放核验 | complete | 299/299已核验；299可执行，失败状态不替换。 |
| 正式单步生成与执行 | complete | 9模型全部完成生成、配对执行核验和隔离after-evaluator。 |
| 行为评分与72条复核 | complete | 完成2691行评分，1473种证据；重复复核72/72，共同缺失不替换。 |
| evaluator与报告 | complete | 第一阶段已完成；结果见 REPORT.md。未运行旧ZeroFail3、可选续跑。 |

## 无人值守检查

最近检查（北京时间）：2026-10-20T06:29:08.694707+08:00；监控状态：**complete**。
实验、评分和最终报告已完成；守护进程自动退出。
动作生成 2691/2691；配对执行 2691/2691；有效配对 2691；不同证据评分 1473；重复复核 72/72。
预计剩余：已完成或正在写最终报告。
工作盘空闲 128.5 GiB；pipeline PID：None；监控 PID：419013。
每5分钟检查进程、产物、磁盘和GPU；网络/进程暂态异常按断点重启，已成功的动作和评分不重采。完成后监控自动退出；未知一致性/协议错误会停止并保留错误记录。
- [机器可读检查状态](HEALTH.json) / [监控事件](MONITOR_EVENTS.jsonl) / [监控日志](logs/watchdog.log)。

## 异常与修复

2026-10-20 00:00:49（北京时间），队列在正式前缀的隔离 evaluator 核验停止；正式模型动作尚未生成。299 个前缀重放的原始反馈均一致，294 个 evaluator 已通过，5 个触发数据库指纹不一致。

原因是 SQL 变更日志恢复时重新组织 SQLite FTS5 全文索引的物理分段。5 例差异仅在 phone/gmail 的 `_fts_data`、`_fts_idx` 内部表；业务表一致。改用活跃数据库的完整 SQLite backup 保存快照，保留所有表的严格一致性检查。相同文件按内容哈希硬链接去重；evaluator 使用独立副本，验证后仅清理该临时副本，原快照保留。

2026-10-20T00:26:07.659434+08:00：5/5 修复验证通过；新重放的全部 before 指纹与原记录完全相同，原失败快照和诊断已保留。299/299 reference evaluator 已齐备。候选状态、prompt、rubric 和评分协议均未改变，未删除或替换状态。见 [修复审计](calibration/snapshot_fix/repair_audit.json)。

- [实时状态](STATUS.json) / [全部节点记录](EVENTS.jsonl)。
- [冻结计划](plan_snapshot/SAME_STATE_PLAN.md) / [评价协议](plan_snapshot/STATE_JUDGING.md) / [状态清单](plan_snapshot/states_selected.csv)。
- [本次授权](config/authorization.json) 覆盖快照中启动前“未授权”说明；[运行配置](config/runtime.json)。
- 原始重放/评分/生成文件本地保存在 calibration/raw、inputs、results、judge_runs；含任务数据，默认不进入git。

实时终端查看：`cat STATUS.json`、`cat HEALTH.json` 或 `tail -f EVENTS.jsonl`（在本目录执行）。
