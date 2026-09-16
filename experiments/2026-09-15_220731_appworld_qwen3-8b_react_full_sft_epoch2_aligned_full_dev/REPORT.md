# full-SFT epoch2 AppWorld 完整 Dev 评测报告

## 1. 结论

本实验已覆盖 Dev 的 57 个唯一任务和 19 个场景。官方结果为 0/57 个任务成功，TGC=0.0，SGC=0.0。

逐题 evaluator 共通过 64/291 个测试项（22.0%）。

## 2. 官方指标与对照

| 实验 | 成功任务 | TGC | 成功场景 | SGC | 测试项通过率 |
|---|---:|---:|---:|---:|---:|
| 原始 Qwen3-8B | 5/57 | 8.8 | 0/19 | 0.0 | 114/291 (39.2%) |
| LoRA | 5/57 | 8.8 | 1/19 | 5.3 | 105/291 (36.1%) |
| full-SFT epoch5 | 0/57 | 0.0 | 0/19 | 0.0 | 86/291 (29.6%) |
| full-SFT epoch2 | 0/57 | 0.0 | 0/19 | 0.0 | 64/291 (22.0%) |

## 3. 逐题转移

### 相对 原始 Qwen3-8B

| 两者成功 | 对照独有成功 | 当前独有成功 | 两者失败 |
|---:|---:|---:|---:|
| 0 | 5 | 0 | 52 |

当前新增成功：无

当前退化：`23cf851_2`、`68ee2c9_3`、`6c2c621_1`、`6c2c621_2`、`fac291d_1`

### 相对 LoRA

| 两者成功 | 对照独有成功 | 当前独有成功 | 两者失败 |
|---:|---:|---:|---:|
| 0 | 5 | 0 | 52 |

当前新增成功：无

当前退化：`50e1ac9_1`、`6171bbc_1`、`d4e9306_1`、`d4e9306_2`、`d4e9306_3`

### 相对 full-SFT epoch5

| 两者成功 | 对照独有成功 | 当前独有成功 | 两者失败 |
|---:|---:|---:|---:|
| 0 | 0 | 0 | 57 |

当前新增成功：无

当前退化：无

当前成功任务：无

当前完整成功场景：无

## 4. 57 题完整性与唯一性

| 检查 | 结果 |
|---|---:|
| dataset 任务数/唯一数 | 57/57 |
| 官方 individual 任务数 | 57 |
| task_status 原始行数 | 57 |
| task_status 唯一任务数 | 57 |
| 每题严格一行 | True |
| 重复 task ID | 无 |
| 缺失 task ID | 无 |
| 多余 task ID | 无 |
| evaluator_error 任务 | 无 |
| 状态与官方结果不一致 | 无 |

若恢复运行导致同一任务出现多行，汇总使用文件中最后一行，同时保留重复行审计。官方 individual 与 Dev split 的集合必须严格一致，否则脚本拒绝生成报告。

## 5. 输出接口审计

| 指标 | 数量 |
|---|---:|
| LM 调用 | 1,461 |
| message.content 非空 | 1,461 |
| message.content=null | 0 |
| 无 Python code 的 LM 消息 | 13 |
| No code available observation | 0 |
| 受影响任务 | 13 |
| AppWorld API 调用 | 872 |
| 含 complete_task action 的任务 | 21/57 |
| Python 执行错误任务 | 57 |
| Python 语法错误任务 | 49 |
| 达到 50 次 LM 调用的任务 | 23 |

## 6. 运行与恢复审计

| 指标 | 值 |
|---|---:|
| run_started_at 记录数 | 1 |
| run_finished_at 记录数 | 1 |
| 检测到恢复/重试 | False |
| 最终退出码 | 0 |
| 历次退出码 | [0] |
| 首次开始至最终结束 | 1 小时 42 分 19 秒 |
| 任务内执行失败 observation | 746 |
| 任务内语法错误 observation | 373 |
| 上下文溢出终止事件 | 13 |
| 上下文溢出任务 | 13 |
| 运行/恢复异常 | 无 |

上下文溢出任务：`23cf851_1`、`23cf851_3`、`37a8675_1`、`37a8675_2`、`37a8675_3`、`383cbac_2`、`383cbac_3`、`4fab96f_1`、`4fab96f_2`、`4fab96f_3`、`6bdbc26_2`、`6bdbc26_3`、`6c2c621_2`

未记录额外恢复操作。

任务内 Python 错误属于 agent 轨迹质量统计；CUDA OOM、engine failure、连接失败、非零进程退出和恢复状态冲突才列为运行异常。

## 7. Checkpoint 元数据

```json
{
  "path": "/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/artifacts/checkpoints/epoch_2_model",
  "exists": true,
  "config.json_sha256": "c8594890253c8539bf90f33feb507d8b50e164a8379643e04e61e9b7ac0f531c",
  "model.safetensors.index.json_sha256": "060d3f0a55add8d530554c96fbb9ff7febc0a97edf833c278b2a5c4ef1128bf2",
  "tokenizer_config.json_sha256": "cd5c1909da4950a610a9e3a6cb6763cff0381d91c6f0838855db8d5ae83d6c9f",
  "safetensor_shard_count": 5,
  "safetensor_total_bytes": 16381516776,
  "label": "full-SFT epoch2",
  "epoch": 2,
  "weights_sha256": "cabbcef25a5022d26becdaf75588f6be37554bf73650b940dea26aa7d38864d8",
  "global_step": 640,
  "model_shard_manifest_fingerprint": "cabbcef25a5022d26becdaf75588f6be37554bf73650b940dea26aa7d38864d8",
  "all15_files_fingerprint": "c519ab99d35ff04372a3761aee4859baac0618248d967f42aa0a9934a736117b"
}
```

## 8. 产物

- `REPORT.md`：本报告。
- `summary.json`：机器可读指标、逐题转移与审计。
- `manifest.json`：代码、数据、checkpoint 与比较实验来源。
- `command.txt`：实际评测命令。
- `artifacts.sha256`：核心报告输入和输出的 SHA256。
- `task_status.jsonl`：逐题即时状态；恢复时可能追加重复任务。
- `experiments/outputs/.../evaluations/dev.json`：官方聚合与逐题评测。
