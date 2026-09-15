# AppWorld 67-task Qwen3-8B LoRA training report

Status: **SUCCESS**. The adapter was trained on all 67 verified
AppWorld train tasks (640 completion-only decision samples) with two
NCCL/DDP ranks and reloaded successfully for an AppWorld ReAct-format generation check.

## Training

- Base model: `/root/autodl-tmp/models/Qwen3-8B`
- Method: LoRA r=8, alpha=16; q/k/v/o and gate/up/down projections
- Precision/attention: bfloat16 / sdpa
- Context: 32768 tokens; truncated train samples: 0
- Epochs / optimizer steps: 1 / 320
- Per-GPU batch / global batch: 1 / 2
- Learning rate: 0.0002
- First 20-step mean loss: 0.946417
- Last 20-step mean loss: 0.634202
- Training plus diagnostic validation time: 1040.28 seconds

The recorded validation loss (0.409828) is a runtime diagnostic. Its seven
tasks are included in the all-67 training input, so it is not a generalization estimate. The held-out
AppWorld Dev evaluator is the model-quality test.

## Dual-GPU evidence

| rank | GPU | peak allocated | peak reserved |
|---:|---|---:|---:|
| 0 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 63.52 GiB | 71.58 GiB |
| 1 | NVIDIA RTX PRO 6000 Blackwell Server Edition | 66.04 GiB | 74.43 GiB |

The full time series is stored in `logs/gpu_usage.csv`.

## Adapter verification

- Reload status: PASS
- Sample: `229360a_2::assistant-0001`
- Generated tokens: 188
- Non-empty fenced Python blocks: 1
- Adapter weights: `/root/autodl-tmp/workspace-tw/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67/artifacts/adapter/adapter_model.safetensors`
- Adapter SHA-256: `a1d2a7fa48a6d9fedd7561b5fbe89857004156c1a867d2b43e56caee712a415e`

The adapter and tokenizer under `artifacts/adapter/` can be loaded with PEFT for AppWorld Dev, or
served by a LoRA-capable vLLM process with the unchanged local Qwen3-8B base model. This experiment
did not run the full Dev benchmark.
