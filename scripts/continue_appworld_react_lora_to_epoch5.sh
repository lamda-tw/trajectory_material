#!/usr/bin/env bash
set -Eeuo pipefail

workspace="/root/autodl-tmp/workspace-tw"
experiment="${1:?existing experiment directory is required}"
model="$workspace/models/Qwen3-8B"
if [[ ! -d "$model" ]]; then
  model="/root/autodl-tmp/models/Qwen3-8B"
fi
dataset="$workspace/data/2026-09-15_appworld_qwen3-8b_react_sft_67"
python="$workspace/.conda-training/bin/python"
torchrun="$workspace/.conda-training/bin/torchrun"

if [[ "$experiment" != "$workspace/experiments/2026-09-15_102913_appworld_qwen3_8b_react_lora_67" ]]; then
  echo "this continuation is pinned to the verified epoch-1 experiment" >&2
  exit 2
fi
if [[ -e "$experiment/CONTINUATION_STATUS.txt" ]]; then
  echo "refusing to overwrite an existing continuation status" >&2
  exit 3
fi
for required in "$experiment/artifacts/adapter/adapter_model.safetensors" \
                "$experiment/artifacts/metrics.json" \
                "$experiment/STATUS.txt" \
                "$dataset/train.jsonl"; do
  test -f "$required" || { echo "missing required input: $required" >&2; exit 2; }
done

mkdir -p "$experiment/artifacts/continuation" "$experiment/scripts_snapshot_epoch5" "$experiment/logs"
monitor_pid=""
cleanup_monitor() {
  if [[ -n "$monitor_pid" ]] && kill -0 "$monitor_pid" 2>/dev/null; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
}
on_error() {
  status=$?
  cleanup_monitor
  printf 'FAILED exit_code=%s finished_at=%s epoch1_preserved=true\n' "$status" "$(date --iso-8601=seconds)" > "$experiment/CONTINUATION_STATUS.txt"
  printf 'FAILED_CONTINUATION exit_code=%s epoch1_preserved=true\n' "$status" > "$experiment/STATUS.txt"
  exit "$status"
}
trap on_error ERR
trap cleanup_monitor EXIT

cd "$workspace"
cp -a "$experiment/artifacts/adapter" "$experiment/artifacts/adapter_epoch1"
cp "$experiment/artifacts/metrics.json" "$experiment/artifacts/metrics_epoch1.json"
cp "$experiment/REPORT.md" "$experiment/REPORT_EPOCH1.md"
cp "$experiment/STATUS.txt" "$experiment/STATUS_EPOCH1.txt"
cp "$experiment/artifacts.sha256" "$experiment/artifacts_epoch1.sha256"
cp "$experiment/metrics/generation_smoke.json" "$experiment/metrics/generation_smoke_epoch1.json"

cp scripts/continue_appworld_react_lora.py scripts/plot_appworld_lora_total_loss.py \
  scripts/build_appworld_lora_5epoch_report.py scripts/continue_appworld_react_lora_to_epoch5.sh \
  "$experiment/scripts_snapshot_epoch5/"

{
  echo "continuation_started_at=$(date --iso-8601=seconds)"
  echo "source_adapter=$experiment/artifacts/adapter_epoch1"
  echo "target_epochs=5"
  echo "optimizer_state_at_epoch2=reinitialized because epoch1 optimizer state was not saved"
  echo
  nvidia-smi
  echo
  git status --short --branch
  git rev-parse HEAD
} > "$experiment/environment_epoch2_5.txt" 2>&1

nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,memory.used,memory.total,power.draw \
  --format=csv -lms 1000 > "$experiment/logs/gpu_usage_epochs2_5.csv" &
monitor_pid=$!

CUDA_VISIBLE_DEVICES=0,1 "$torchrun" --standalone --nproc_per_node=2 scripts/ddp_probe.py \
  2>&1 | tee "$experiment/logs/08_ddp_probe_epoch2_5.log"

PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=0,1 \
  "$torchrun" --standalone --nproc_per_node=2 scripts/continue_appworld_react_lora.py \
  --model "$model" \
  --resume-adapter "$experiment/artifacts/adapter_epoch1" \
  --train-json "$dataset/train.jsonl" \
  --validation-json "$dataset/splits/task_holdout_60_7/validation.jsonl" \
  --output-dir "$experiment/artifacts/continuation" \
  --max-length 32768 \
  --initial-epoch 1 \
  --target-epochs 5 \
  --initial-global-step 320 \
  --learning-rate 0.0002 \
  --weight-decay 0 \
  --seed 20260915 \
  2>&1 | tee "$experiment/logs/09_train_epochs2_5.log"

CUDA_VISIBLE_DEVICES=0 "$python" scripts/verify_appworld_react_adapter.py \
  --model "$model" \
  --adapter "$experiment/artifacts/continuation/adapter_epoch5" \
  --sample-json "$dataset/splits/task_holdout_60_7/validation.jsonl" \
  --output "$experiment/metrics/generation_smoke_epoch5.json" \
  --max-input-length 32768 \
  --max-new-tokens 512 \
  2>&1 | tee "$experiment/logs/10_generation_verify_epoch5.log"

cleanup_monitor
monitor_pid=""
"$python" scripts/plot_appworld_lora_total_loss.py --experiment-dir "$experiment" --window 50 \
  2>&1 | tee "$experiment/logs/11_plot_total_loss.log"
"$python" scripts/build_appworld_lora_5epoch_report.py --experiment-dir "$experiment" \
  2>&1 | tee "$experiment/logs/12_report_epoch5.log"

ln -sfn continuation/adapter_epoch5 "$experiment/artifacts/adapter_final"
(
  cd "$experiment"
  find . -type f ! -name artifacts.sha256 ! -name STATUS.txt ! -name CONTINUATION_STATUS.txt \
    ! -name continuation_launcher.log -print0 | sort -z | xargs -0 sha256sum > artifacts.sha256
)
printf 'SUCCESS total_epochs=5 finished_at=%s\n' "$(date --iso-8601=seconds)" > "$experiment/CONTINUATION_STATUS.txt"
printf 'SUCCESS total_epochs=5 finished_at=%s\n' "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
echo "SUCCESS_TOTAL_EPOCHS_5: $experiment"
