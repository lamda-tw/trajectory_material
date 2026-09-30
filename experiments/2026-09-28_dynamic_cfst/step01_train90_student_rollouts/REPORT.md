# 第一步结果：Qwen3-8B LoRA epoch5 的 train90 学生轨迹

本轮完成 90 道训练任务的记录整理。官方成功 **46/90（51.1%）**，失败 **44**，运行或评分产物不完整 **0**。完整性核验：**通过**。

## 本次运行做了什么

使用现有 Qwen3-8B 和 train90 LoRA 第 5 轮 adapter，按原 LoRA Dev 评测协议运行全部 train90。只采集学生轨迹与官方评分；没有训练新模型，没有调用 Codex 修复，没有根据结果重跑失败任务。

这些任务已用于原模型 SFT，本轮用于获取学生真实行为和失败现场，不作为未见任务泛化成绩。

- 开始：2026-09-28T07:44:55.540230+00:00。
- 结束：2026-09-28T08:28:41.320603+00:00。
- 含模型服务启动的总耗时：43.8 分钟。
- 基座：/root/autodl-tmp/models/Qwen3-8B。
- Adapter：/root/autodl-tmp/workspace-tw/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter。
- 原协议：temperature=0、seed=100、每题最多50步、单次最多3000输出 tokens、上下文32000、无 reasoning parser、单 GPU 顺序执行。
- 固定提示词、任务顺序、运行配置和来源校验保存在 config/；实际每次模型请求均检查协议字段。

## 官方结果

| 项目 | 结果 |
| --- | --- |
| 成功任务 | 46/90 |
| 失败任务 | 44/90 |
| 完整成功场景 | 9/30 |
| TGC / SGC | 51.1 / 30.0 |
| 通过官方测试项 | 373/492 |
| 模型请求次数 | 1505 |
| 实际执行步骤 | 1496 |
| 上下文超限涉及任务 | 9 |
| 基础设施或评分产物异常 | 0 |

上下文超限保留为原协议下的实际结果，不扩窗重试，也不把它混同为服务崩溃。模型生成代码的执行报错仍保留在轨迹中，供下一步审查；本次不做能力标签或错误根因标注。

## 从哪里查看

- **逐题总表：** [task_results.csv](task_results.csv)，含成功/失败、官方断言数、执行步数、模型调用数、耗时和轨迹路径。
- **成功清单：** [success_task_ids.txt](success_task_ids.txt)。
- **失败清单：** [failed_task_ids.txt](failed_task_ids.txt)。
- **运行/评分异常清单：** [infrastructure_error_task_ids.txt](infrastructure_error_task_ids.txt)。
- **机器可读汇总：** [summary.json](summary.json)。
- **逐题轨迹索引：** [trajectory_index.jsonl](trajectory_index.jsonl)。
- **原始逐题即时评分：** [task_status.jsonl](task_status.jsonl)，与官方最终聚合逐题核对，保留原记录。
- **官方聚合评分：** [train.json](experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/evaluations/train.json)。
- **最终核验：** [final_validation.json](metrics/final_validation.json)。

每个任务的目录位于 experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/tasks/任务号/，其中：

| 文件 | 内容 |
| --- | --- |
| logs/lm_calls.jsonl | 每次真实模型请求（完整历史）与原始响应 |
| logs/environment_io.md | 按步骤排列的执行代码与环境返回 |
| logs/api_calls.jsonl | 实际工具/API 调用 |
| logs/logger.jsonl | 结构化 agent 交互及步骤编号 |
| dbs/ | 本轮任务环境产生的数据库状态 |
| misc/finished | 任务运行结束标记，成功与失败均可能有此标记 |
| evaluation/report.md | 官方逐题评估报告 |

原始轨迹、数据库、缓存和模型日志只保留本地。下一步在并列的 step02_error_analysis/ 下执行，本次尚未开始。
