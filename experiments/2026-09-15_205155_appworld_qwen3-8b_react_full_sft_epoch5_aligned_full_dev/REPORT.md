# full-SFT epoch5 AppWorld 完整 Dev 评测报告

## 1. 结论

本实验已覆盖 Dev 的 57 个唯一任务和 19 个场景。官方结果为 0/57 个任务成功，TGC=0.0，SGC=0.0。

逐题 evaluator 共通过 86/291 个测试项（29.6%）。

## 2. 官方指标与对照

| 实验 | 成功任务 | TGC | 成功场景 | SGC | 测试项通过率 |
|---|---:|---:|---:|---:|---:|
| 原始 Qwen3-8B | 5/57 | 8.8 | 0/19 | 0.0 | 114/291 (39.2%) |
| LoRA | 5/57 | 8.8 | 1/19 | 5.3 | 105/291 (36.1%) |
| full-SFT epoch5 | 0/57 | 0.0 | 0/19 | 0.0 | 86/291 (29.6%) |

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
| LM 调用 | 742 |
| message.content 非空 | 742 |
| message.content=null | 0 |
| 无 Python code 的 LM 消息 | 5 |
| No code available observation | 1 |
| 受影响任务 | 4 |
| AppWorld API 调用 | 1,401 |
| 含 complete_task action 的任务 | 49/57 |
| Python 执行错误任务 | 56 |
| Python 语法错误任务 | 38 |
| 达到 50 次 LM 调用的任务 | 5 |

## 6. 运行与恢复审计

| 指标 | 值 |
|---|---:|
| run_started_at 记录数 | 2 |
| run_finished_at 记录数 | 2 |
| 检测到恢复/重试 | True |
| 最终退出码 | 0 |
| 历次退出码 | [1, 0] |
| 首次开始至最终结束 | 1 小时 5 分 9 秒 |
| 任务内执行失败 observation | 491 |
| 任务内语法错误 observation | 83 |
| 运行/恢复异常 | `prior_nonzero_run_exit_detected`、`recovered_recursion_error` |

首次运行因 RecursionError 退出（退出码 1）；清除单个不完整任务 df61dc5_3 后恢复运行，最终退出码 0。

任务内 Python 错误属于 agent 轨迹质量统计；CUDA OOM、engine failure、连接失败、非零进程退出和恢复状态冲突才列为运行异常。

## 7. Checkpoint 元数据

```json
{
  "status": "SUCCESS",
  "finished_at_utc": "2026-09-15T06:31:25.116166+00:00",
  "hostname": "autodl-container-65d14488ce-cd05d5ef",
  "arguments": {
    "model": "/root/autodl-tmp/models/Qwen3-8B",
    "train_json": "/root/autodl-tmp/workspace-tw/data/2026-09-15_appworld_qwen3-8b_react_sft_67/train.jsonl",
    "validation_json": "/root/autodl-tmp/workspace-tw/data/2026-09-15_appworld_qwen3-8b_react_sft_67/splits/task_holdout_60_7/validation.jsonl",
    "experiment_dir": "/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67",
    "max_length": 32768,
    "epochs": 5,
    "learning_rate": 0.0002,
    "weight_decay": 0.0,
    "seed": 20260915,
    "max_steps": 0,
    "skip_validation": false,
    "skip_model_save": false,
    "save_every_epoch": true
  },
  "distributed": {
    "backend": "nccl",
    "world_size": 2,
    "sharding": "FSDP FULL_SHARD",
    "ranks": [
      {
        "rank": 0,
        "local_rank": 0,
        "device_name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
        "device_capability": [
          12,
          0
        ],
        "peak_allocated_gib": 76.40076065063477,
        "peak_reserved_gib": 92.603515625
      },
      {
        "rank": 1,
        "local_rank": 1,
        "device_name": "NVIDIA RTX PRO 6000 Blackwell Server Edition",
        "device_capability": [
          12,
          0
        ],
        "peak_allocated_gib": 76.4006576538086,
        "peak_reserved_gib": 92.703125
      }
    ]
  },
  "model": {
    "source_base_model": "/root/autodl-tmp/models/Qwen3-8B",
    "method": "full_parameter_sft",
    "dtype": "bfloat16",
    "attention": "sdpa",
    "trainable_parameters": 8190735360,
    "total_parameters": 8190735360,
    "trainable_percent": 100.0,
    "final_model": "/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/artifacts/model"
  },
  "data": {
    "train": {
      "count": 640,
      "samples": {
        "collection_omitted": true,
        "item_count": 640
      },
      "tokens": {
        "min": 3277,
        "max": 25070,
        "mean": 4877.6453125
      },
      "prompt_tokens": {
        "min": 3145,
        "max": 25008,
        "mean": 4710.7375
      },
      "completion_tokens": {
        "min": 38,
        "max": 1971,
        "mean": 166.9078125
      },
      "original_tokens": {
        "min": 3277,
        "max": 25070,
        "mean": 4877.6453125
      },
      "truncated_samples": 0,
      "truncated_prompt_tokens_total": 0
    },
    "validation": {
      "count": 71,
      "samples": {
        "collection_omitted": true,
        "item_count": 71
      },
      "tokens": {
        "min": 3304,
        "max": 16203,
        "mean": 5870.422535211268
      },
      "prompt_tokens": {
        "min": 3165,
        "max": 16161,
        "mean": 5701.957746478874
      },
      "completion_tokens": {
        "min": 41,
        "max": 782,
        "mean": 168.46478873239437
      },
      "original_tokens": {
        "min": 3304,
        "max": 16203,
        "mean": 5870.422535211268
      },
      "truncated_samples": 0,
      "truncated_prompt_tokens_total": 0
    }
  },
  "training": {
    "epochs_requested": 5,
    "epochs_completed": 5,
    "global_steps": 1600,
    "per_gpu_batch_size": 1,
    "global_batch_size": 2,
    "gradient_accumulation_steps": 1,
    "learning_rate": 0.0002,
    "weight_decay": 0.0,
    "optimizer": "fused AdamW",
    "loss_policy": "assistant_completion_only",
    "enable_thinking": false,
    "gradient_checkpointing": true,
    "max_length": 32768,
    "elapsed_seconds": 5376.78849697113,
    "epoch_summaries": [
      {
        "epoch": 1,
        "steps": 320,
        "mean_loss": 1.166161174606532,
        "first_20_mean_loss": 1.7849091649055482,
        "last_20_mean_loss": 1.066573628783226,
        "min_loss": 0.2899523377418518,
        "max_loss": 3.2837631702423096
      },
      {
        "epoch": 2,
        "steps": 320,
        "mean_loss": 0.6290379266720265,
        "first_20_mean_loss": 0.6120167389512062,
        "last_20_mean_loss": 0.7075821489095688,
        "min_loss": 0.1414947211742401,
        "max_loss": 1.338860034942627
      },
      {
        "epoch": 3,
        "steps": 320,
        "mean_loss": 0.3716761443763971,
        "first_20_mean_loss": 0.3821850627660751,
        "last_20_mean_loss": 0.3663049012422562,
        "min_loss": 0.11870376765727997,
        "max_loss": 0.8715250492095947
      },
      {
        "epoch": 4,
        "steps": 320,
        "mean_loss": 0.2393895993824117,
        "first_20_mean_loss": 0.2252083569765091,
        "last_20_mean_loss": 0.24982265718281269,
        "min_loss": 0.04999905452132225,
        "max_loss": 0.8413100242614746
      },
      {
        "epoch": 5,
        "steps": 320,
        "mean_loss": 0.1669180854165461,
        "first_20_mean_loss": 0.17414458822458984,
        "last_20_mean_loss": 0.1347834937274456,
        "min_loss": 0.01540694572031498,
        "max_loss": 0.4771343469619751
      }
    ],
    "history": {
      "collection_omitted": true,
      "item_count": 1600
    }
  },
  "validation": {
    "scope": "diagnostic subset overlapping all-data training",
    "loss": 0.07892354130516303,
    "perplexity": 1.0821215813034681,
    "completion_target_tokens": 12139
  },
  "omitted_large_collections": {
    "data.train.samples": 640,
    "data.validation.samples": 71,
    "training.history": 1600
  },
  "metadata_file": "/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/metrics/metrics.json",
  "metadata_file_sha256": "d5c45150157b041790420c132325cac4e4a1b9410e0e71c080586cc7f0910f6e",
  "path": "/root/autodl-tmp/workspace-tw/experiments/2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67/artifacts/model",
  "exists": true,
  "config.json_sha256": "c8594890253c8539bf90f33feb507d8b50e164a8379643e04e61e9b7ac0f531c",
  "model.safetensors.index.json_sha256": "060d3f0a55add8d530554c96fbb9ff7febc0a97edf833c278b2a5c4ef1128bf2",
  "tokenizer_config.json_sha256": "cd5c1909da4950a610a9e3a6cb6763cff0381d91c6f0838855db8d5ae83d6c9f",
  "safetensor_shard_count": 5,
  "safetensor_total_bytes": 16381516776,
  "label": "full-SFT epoch5",
  "epoch": 5,
  "global_step": 1600,
  "recovery_cause": "RecursionError",
  "recovery_incomplete_task": "df61dc5_3",
  "recovery_action": "cleared_single_incomplete_task_then_resumed",
  "first_run_exit_code": 1,
  "resumed_run_exit_code": 0
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
