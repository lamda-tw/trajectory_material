#!/usr/bin/env bash
set -Eeuo pipefail

workspace="/root/autodl-tmp/workspace-tw"
model="$workspace/models/Qwen3-8B"
if [[ ! -d "$model" ]]; then
  model="/root/autodl-tmp/models/Qwen3-8B"
fi
dataset="$workspace/data/2026-09-15_appworld_qwen3-8b_react_sft_67"
python="$workspace/.conda-training/bin/python"
torchrun="$workspace/.conda-training/bin/torchrun"
experiment="${1:?experiment directory is required}"
max_length=32768

if [[ "$experiment" != "$workspace"/experiments/* ]]; then
  echo "experiment directory must stay under $workspace/experiments" >&2
  exit 2
fi
if [[ -e "$experiment/STATUS.txt" ]]; then
  echo "refusing to overwrite an existing experiment: $experiment" >&2
  exit 3
fi
mkdir -p "$experiment"/{artifacts,config,data,logs,metrics,probe,scripts_snapshot}
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
  printf 'FAILED exit_code=%s finished_at=%s\n' "$status" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
  exit "$status"
}
trap on_error ERR
trap cleanup_monitor EXIT

cd "$workspace"
printf 'bash scripts/run_appworld_react_lora_67.sh %q\n' "$experiment" > "$experiment/command.txt"
cp scripts/prepare_appworld_lora_experiment.py scripts/ddp_probe.py scripts/minimal_sft_train.py \
  scripts/verify_appworld_react_adapter.py scripts/build_appworld_lora_report.py \
  scripts/run_appworld_react_lora_67.sh "$experiment/scripts_snapshot/"

{
  echo "started_at=$(date --iso-8601=seconds)"
  echo "workspace=$workspace"
  echo "model=$model"
  echo "dataset=$dataset"
  echo "experiment=$experiment"
  echo
  uname -a
  echo
  nvidia-smi
  echo
  "$python" --version
  "$python" -m pip freeze
  echo
  git status --short --branch
  git rev-parse HEAD
} > "$experiment/environment.txt" 2>&1

nvidia-smi --query-gpu=timestamp,index,name,utilization.gpu,memory.used,memory.total,power.draw \
  --format=csv -lms 1000 > "$experiment/logs/gpu_usage.csv" &
monitor_pid=$!

"$python" scripts/prepare_appworld_lora_experiment.py \
  --dataset-dir "$dataset" \
  --model "$model" \
  --output-dir "$experiment/config" \
  --max-length "$max_length" \
  2>&1 | tee "$experiment/logs/01_prepare.log"

ln -s "$dataset/train.jsonl" "$experiment/data/train.jsonl"
ln -s "$dataset/splits/task_holdout_60_7/validation.jsonl" "$experiment/data/diagnostic_validation.jsonl"
cp "$experiment/config/probe_longest.jsonl" "$experiment/data/probe_longest.jsonl"

CUDA_VISIBLE_DEVICES=0,1 "$torchrun" --standalone --nproc_per_node=2 scripts/ddp_probe.py \
  2>&1 | tee "$experiment/logs/02_ddp_probe.log"

PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=0,1 \
  "$torchrun" --standalone --nproc_per_node=2 scripts/minimal_sft_train.py \
  --model "$model" \
  --train-json "$experiment/data/probe_longest.jsonl" \
  --validation-json "$experiment/data/probe_longest.jsonl" \
  --output-dir "$experiment/probe/artifacts" \
  --max-length "$max_length" \
  --epochs 1 \
  --learning-rate 0.0002 \
  --lora-r 8 \
  --lora-alpha 16 \
  --seed 20260915 \
  2>&1 | tee "$experiment/logs/03_longest_probe.log"

PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True CUDA_VISIBLE_DEVICES=0,1 \
  "$torchrun" --standalone --nproc_per_node=2 scripts/minimal_sft_train.py \
  --model "$model" \
  --train-json "$experiment/data/train.jsonl" \
  --validation-json "$experiment/data/diagnostic_validation.jsonl" \
  --output-dir "$experiment/artifacts" \
  --max-length "$max_length" \
  --epochs 1 \
  --learning-rate 0.0002 \
  --lora-r 8 \
  --lora-alpha 16 \
  --seed 20260915 \
  2>&1 | tee "$experiment/logs/04_train.log"

CUDA_VISIBLE_DEVICES=0 "$python" scripts/verify_appworld_react_adapter.py \
  --model "$model" \
  --adapter "$experiment/artifacts/adapter" \
  --sample-json "$experiment/data/diagnostic_validation.jsonl" \
  --output "$experiment/metrics/generation_smoke.json" \
  --max-input-length "$max_length" \
  --max-new-tokens 512 \
  2>&1 | tee "$experiment/logs/05_generation_verify.log"

cleanup_monitor
monitor_pid=""
"$python" scripts/build_appworld_lora_report.py --experiment-dir "$experiment" \
  2>&1 | tee "$experiment/logs/06_report.log"
(
  cd "$experiment"
  find . -type f ! -name artifacts.sha256 ! -name STATUS.txt -print0 \
    | sort -z \
    | xargs -0 sha256sum > artifacts.sha256
)
printf 'SUCCESS finished_at=%s\n' "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
echo "SUCCESS: $experiment"
