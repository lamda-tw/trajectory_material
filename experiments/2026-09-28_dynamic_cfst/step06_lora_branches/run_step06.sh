#!/usr/bin/env bash
set -euo pipefail

ROOT="/root/autodl-tmp/workspace-tw"
STEP06="$ROOT/experiments/2026-09-28_dynamic_cfst/step06_lora_branches"
PYTHON="$ROOT/.conda-training/bin/python"
TORCHRUN="$ROOT/.conda-training/bin/torchrun"
export TOKENIZERS_PARALLELISM=false
export PYTHONUNBUFFERED=1
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1

"$PYTHON" "$STEP06/prepare_step06.py" > "$STEP06/prepare_output.json"
for branch in CFST-state CFST-Action CFST-Mixed; do
  "$TORCHRUN" --standalone --nproc_per_node=2 \
    "$STEP06/train_cfst_branch.py" \
    --config "$STEP06/$branch/training_config.json" \
    2>&1 | tee "$STEP06/$branch/train.log"
done
