#!/usr/bin/env bash
set -Eeuo pipefail

workspace="/root/autodl-tmp/workspace-tw"
model="/root/autodl-tmp/models/Qwen3-8B"
fold="$workspace/data/2026-09-08/folds/fold_05_holdout_0010"
python="$workspace/.conda-training/bin/python"
torchrun="$workspace/.conda-training/bin/torchrun"
experiment="${1:-$workspace/experiments/2026-09-09_minimal_qwen3-8b_lora_2gpu_fold05_smoke}"

if [[ "$experiment" != "$workspace"/experiments/* ]]; then
  echo "experiment directory must stay under $workspace/experiments" >&2
  exit 2
fi
if [[ -e "$experiment/STATUS.txt" ]]; then
  echo "refusing to overwrite an existing experiment: $experiment" >&2
  exit 3
fi

mkdir -p "$experiment"/{artifacts,data,logs,metrics,scripts_snapshot}
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
printf 'bash scripts/run_minimal_sft.sh %q\n' "$experiment" > "$experiment/command.txt"
cp scripts/prepare_minimal_sft.py scripts/ddp_probe.py scripts/minimal_sft_train.py \
  scripts/verify_minimal_sft.py scripts/build_minimal_sft_report.py \
  scripts/run_minimal_sft.sh "$experiment/scripts_snapshot/"

{
  echo "started_at=$(date --iso-8601=seconds)"
  echo "workspace=$workspace"
  echo "model=$model"
  echo "fold=$fold"
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

"$python" scripts/prepare_minimal_sft.py \
  --fold-dir "$fold" \
  --output-dir "$experiment/data" \
  --train-size 8 \
  --validation-size 4 \
  2>&1 | tee "$experiment/logs/01_prepare.log"

CUDA_VISIBLE_DEVICES=0,1 "$torchrun" --standalone --nproc_per_node=2 scripts/ddp_probe.py \
  2>&1 | tee "$experiment/logs/02_ddp_probe.log"

CUDA_VISIBLE_DEVICES=0,1 TORCH_DISTRIBUTED_DEBUG=DETAIL \
  "$torchrun" --standalone --nproc_per_node=2 scripts/minimal_sft_train.py \
  --model "$model" \
  --train-json "$experiment/data/train.jsonl" \
  --validation-json "$experiment/data/validation.jsonl" \
  --output-dir "$experiment/artifacts" \
  --max-length 8192 \
  --epochs 1 \
  --learning-rate 0.0002 \
  --lora-r 8 \
  --lora-alpha 16 \
  --seed 20260909 \
  2>&1 | tee "$experiment/logs/03_train.log"

CUDA_VISIBLE_DEVICES=0 "$python" scripts/verify_minimal_sft.py \
  --model "$model" \
  --adapter "$experiment/artifacts/adapter" \
  --validation-json "$experiment/data/validation.jsonl" \
  --output "$experiment/metrics/generation_smoke.json" \
  --max-input-length 8192 \
  --max-new-tokens 64 \
  2>&1 | tee "$experiment/logs/04_generation_verify.log"

cleanup_monitor
monitor_pid=""
"$python" scripts/build_minimal_sft_report.py --experiment-dir "$experiment" \
  2>&1 | tee "$experiment/logs/05_report.log"
(
  cd "$experiment"
  find . -type f ! -name artifacts.sha256 ! -name STATUS.txt -print0 \
    | sort -z \
    | xargs -0 sha256sum > artifacts.sha256
)
printf 'SUCCESS finished_at=%s\n' "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
echo "SUCCESS: $experiment"
