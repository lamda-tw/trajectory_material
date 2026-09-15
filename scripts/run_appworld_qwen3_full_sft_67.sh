#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 EXPERIMENT_DIR" >&2
  exit 2
fi

workspace="/root/autodl-tmp/workspace-tw"
python_bin="$workspace/.conda-training/bin/python"
torchrun_bin="$workspace/.conda-training/bin/torchrun"
base_model="/root/autodl-tmp/models/Qwen3-8B"
dataset="$workspace/data/2026-09-15_appworld_qwen3-8b_react_sft_67"
lora_experiment="$workspace/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67"
experiment="$(realpath -m "$1")"

if [[ "$experiment" != "$workspace"/experiments/*_appworld_qwen3_8b_react_full_sft_67 ]]; then
  echo "Refusing unexpected experiment path: $experiment" >&2
  exit 2
fi
if [[ -e "$experiment" ]]; then
  echo "Refusing existing experiment path: $experiment" >&2
  exit 2
fi
for required in \
  "$base_model/config.json" \
  "$dataset/train.jsonl" \
  "$dataset/splits/task_holdout_60_7/validation.jsonl" \
  "$lora_experiment/data/probe_longest.jsonl"; do
  test -f "$required" || { echo "Missing required input: $required" >&2; exit 2; }
done

mkdir -p "$experiment"/{artifacts,config,data,logs,metrics,probe,scripts_snapshot}
cp "$lora_experiment/data/probe_longest.jsonl" "$experiment/data/probe_longest.jsonl"
cp \
  "$workspace/scripts/full_sft_train_fsdp.py" \
  "$workspace/scripts/verify_appworld_full_sft_model.py" \
  "$workspace/scripts/plot_appworld_full_sft_loss.py" \
  "$workspace/scripts/build_appworld_full_sft_report.py" \
  "$workspace/scripts/run_appworld_qwen3_full_sft_67.sh" \
  "$workspace/scripts/appworld_run_isolated_full_sft_config.py" \
  "$workspace/scripts/run_appworld_qwen3_react_full_sft_full_dev.sh" \
  "$experiment/scripts_snapshot/"

cat > "$experiment/config/training_config.json" <<EOF
{
  "source_base_model": "$base_model",
  "initialization": "original_base_model_only_no_lora",
  "method": "full_parameter_sft",
  "distributed": "two_gpu_fsdp_full_shard",
  "train_json": "$dataset/train.jsonl",
  "diagnostic_validation_json": "$dataset/splits/task_holdout_60_7/validation.jsonl",
  "train_tasks": 67,
  "train_decision_samples": 640,
  "epochs": 5,
  "steps_per_epoch": 320,
  "global_steps": 1600,
  "per_gpu_batch_size": 1,
  "global_batch_size": 2,
  "gradient_accumulation_steps": 1,
  "learning_rate": 0.0002,
  "weight_decay": 0.0,
  "optimizer": "fused AdamW",
  "dtype": "bfloat16",
  "attention": "sdpa",
  "gradient_checkpointing": true,
  "max_length": 32768,
  "enable_thinking": false,
  "loss_policy": "assistant_completion_only",
  "seed": 20260915,
  "validation_policy": "diagnostic subset overlaps all-data training; AppWorld Dev is held out"
}
EOF

{
  printf 'created_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'workspace_commit=%s\n' "$(git -C "$workspace" rev-parse HEAD)"
  printf 'hostname=%s\n' "$(hostname)"
  printf 'python=%s\n' "$($python_bin --version 2>&1)"
  "$python_bin" -c "import torch, transformers, accelerate; print('torch='+torch.__version__); print('transformers='+transformers.__version__); print('accelerate='+accelerate.__version__)"
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader
  printf 'train_sha256=%s\n' "$(sha256sum "$dataset/train.jsonl" | cut -d' ' -f1)"
  printf 'validation_sha256=%s\n' "$(sha256sum "$dataset/splits/task_holdout_60_7/validation.jsonl" | cut -d' ' -f1)"
} > "$experiment/environment.txt"

cat > "$experiment/command.txt" <<EOF
CUDA_VISIBLE_DEVICES=0,1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \\
$torchrun_bin --standalone --nproc_per_node=2 scripts/full_sft_train_fsdp.py \\
  --model $base_model \\
  --train-json $dataset/train.jsonl \\
  --validation-json $dataset/splits/task_holdout_60_7/validation.jsonl \\
  --experiment-dir $experiment \\
  --max-length 32768 --epochs 5 --learning-rate 0.0002 --weight-decay 0 \\
  --seed 20260915 --save-every-epoch
EOF

printf 'RUNNING started_at=%s\n' "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
monitor_pid=""
cleanup() {
  status=$?
  if [[ -n "$monitor_pid" ]]; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ $status -ne 0 ]]; then
    printf 'FAILED exit_code=%s finished_at=%s\n' "$status" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
  fi
  exit "$status"
}
trap cleanup EXIT

(
  printf 'timestamp,gpu_index,memory_used_mib,memory_total_mib,utilization_gpu_percent\n'
  while true; do
    nvidia-smi --query-gpu=timestamp,index,memory.used,memory.total,utilization.gpu --format=csv,noheader,nounits
    sleep 5
  done
) > "$experiment/logs/gpu_usage.csv" &
monitor_pid=$!

export CUDA_VISIBLE_DEVICES="0,1"
export PYTORCH_CUDA_ALLOC_CONF="expandable_segments:True"
export TORCH_NCCL_ASYNC_ERROR_HANDLING="1"
export TOKENIZERS_PARALLELISM="false"
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"

"$torchrun_bin" --standalone --nproc_per_node=2 scripts/ddp_probe.py \
  2>&1 | tee "$experiment/logs/01_ddp_probe.log"

"$torchrun_bin" --standalone --nproc_per_node=2 scripts/full_sft_train_fsdp.py \
  --model "$base_model" \
  --train-json "$experiment/data/probe_longest.jsonl" \
  --validation-json "$experiment/data/probe_longest.jsonl" \
  --experiment-dir "$experiment/probe" \
  --max-length 32768 \
  --epochs 1 \
  --learning-rate 0.0002 \
  --weight-decay 0 \
  --seed 20260915 \
  --max-steps 1 \
  --skip-validation \
  --skip-model-save \
  2>&1 | tee "$experiment/logs/02_longest_full_sft_probe.log"

"$torchrun_bin" --standalone --nproc_per_node=2 scripts/full_sft_train_fsdp.py \
  --model "$base_model" \
  --train-json "$dataset/train.jsonl" \
  --validation-json "$dataset/splits/task_holdout_60_7/validation.jsonl" \
  --experiment-dir "$experiment" \
  --max-length 32768 \
  --epochs 5 \
  --learning-rate 0.0002 \
  --weight-decay 0 \
  --seed 20260915 \
  --save-every-epoch \
  2>&1 | tee "$experiment/logs/03_train_full_sft.log"

set +e
CUDA_VISIBLE_DEVICES=0 "$python_bin" scripts/verify_appworld_full_sft_model.py \
  --model "$experiment/artifacts/model" \
  --sample-json "$dataset/splits/task_holdout_60_7/validation.jsonl" \
  --output "$experiment/metrics/generation_smoke.json" \
  --max-input-length 32768 \
  --max-new-tokens 512 \
  > "$experiment/logs/04_generation_verify.log" 2>&1
verify_status=$?
set -e
printf '%s\n' "$verify_status" > "$experiment/metrics/generation_verify_exit_code.txt"

"$python_bin" scripts/plot_appworld_full_sft_loss.py \
  --experiment "$experiment" \
  > "$experiment/logs/05_plot_loss.log" 2>&1

"$python_bin" scripts/build_appworld_full_sft_report.py \
  --experiment "$experiment" \
  --lora-experiment "$lora_experiment" \
  > "$experiment/logs/06_report.log" 2>&1

# Freeze GPU telemetry before it is included in the immutable hash manifest.
if [[ -n "$monitor_pid" ]]; then
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
  monitor_pid=""
fi

find "$experiment/artifacts/model" -maxdepth 1 -name '*.safetensors' -type f -print0 \
  | sort -z | xargs -0 sha256sum > "$experiment/metrics/final_model_weights.sha256"

printf 'SUCCESS epochs=5 steps=1600 generation_verify_exit_code=%s finished_at=%s\n' \
  "$verify_status" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"

find "$experiment" -type f \
  ! -path "$experiment/artifacts.sha256" \
  ! -path "$experiment/logs/launcher.log" \
  ! -path "$experiment/logs/07_hash_verify.log" \
  -print0 | sort -z | xargs -0 sha256sum > "$experiment/artifacts.sha256"
sha256sum -c "$experiment/artifacts.sha256" > "$experiment/logs/07_hash_verify.log"

trap - EXIT

if [[ -n "$monitor_pid" ]]; then
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
fi
echo "Full-parameter SFT experiment completed: $experiment"
