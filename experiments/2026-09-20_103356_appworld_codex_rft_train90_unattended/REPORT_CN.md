# AppWorld Codex RFT 全量 90 题无人值守实验

## 实验配置

- 数据范围：`train.txt` 全部 90 题，顺序与集合均已独立核对一致
- 策略模型：`gpt-5.6-sol`，reasoning effort 为 `high`，未设置 temperature
- 并发：4 个任务 worker
- 停止规则：每题获得首条官方 evaluator 成功轨迹即停止；否则最多累计 10 条语义失败轨迹
- 单条轨迹：最多 40 次 AppWorld 交互；本次实际最大值为 28
- thread：每条 attempt 新建独立 Codex thread，attempt 内以同一 thread 续接 observation

## 结论

- 终态任务：90 / 90
- 成功任务：90
- 连续 10 次失败后放弃：0
- 成功轨迹：90
- 语义失败轨迹：1
- 基础设施事件：0（不计入十次失败）
- 尝试次数分布：1次:89题、2次:1题
- 成功轨迹中包含执行错误后恢复：9
- 语义轨迹总交互步：1177

唯一的拒绝采样发生在 `afc0fce_2`：第 1 条轨迹执行 7 步后通过
7/9 个官方测试，判定失败；第 2 条轨迹使用全新 thread，执行 11 步后通过
9/9 个测试并立即停止。两条轨迹都已保留。

## 数据边界与审计

模型只看到公开 ReAct 提示、公开任务信息、本条 attempt 的历史动作，以及
凭据脱敏后的 observation。ground truth 只由官方 evaluator 用于最终 reward，
不会进入策略上下文。

- 审计状态：passed
- Codex 事件类型：['agent_message']
- 禁止的工具事件：[]
- 检查的实际敏感值：147
- 模型可见 observation 中的敏感值泄漏：0
- 独立 Codex threads：91 / 91

独立交叉审计还确认：91 条轨迹的 91 个 thread ID 全部唯一；每个 attempt
的逐回合 `thread.started` ID 均与轨迹声明 ID 一致；所有 Codex 事件 item
均为 `agent_message`，没有 shell、文件、web 或 MCP 工具事件。

敏感值审计排除了 API schema 中 `string/integer/null` 等 116 个类型占位符，
检查了 147 次真实敏感值出现（118 个不同值）：模型可见 observation 中命中
0 次。额外的敏感字段赋值、JWT 与未脱敏 Bearer 模式检查也均为 0。

## 错误与恢复

- 基础设施错误：0；因此本次没有实际触发基础设施重试，但控制器已实现中断租约识别、原子状态恢复和不计入 10 次失败的重试路径
- 官方 evaluator 语义失败：1；已通过新的独立 attempt/thread 成功恢复
- 成功轨迹中包含 AppWorld 执行错误后自然恢复：9
- worker 崩溃：0

## Codex 用量

- input tokens: 185861351
- cached input tokens: 162208768
- output tokens: 1175525
- reasoning output tokens: 377878

## 主要文件

- accepted_trajectories.jsonl：成功轨迹
- failed_attempts.jsonl：完整语义失败轨迹
- infrastructure_events.jsonl：不计入失败上限的基础设施事件
- task_results.jsonl：90 题终态
- summary.json：汇总
- AUDIT.json：机器可读审计
- shards/<task_id>/：逐题状态、原始轨迹和逐回合 Codex 事件
