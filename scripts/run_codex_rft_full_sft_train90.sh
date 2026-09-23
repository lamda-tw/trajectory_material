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
dataset="$workspace/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90"
lora_experiment="$workspace/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5"
experiment="$(realpath -m "$1")"

if [[ "$experiment" != "$workspace"/experiments/*_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5 ]]; then
  echo "Refusing unexpected experiment path: $experiment" >&2
  exit 2
fi
if [[ -e "$experiment" ]]; then
  echo "Refusing existing experiment path: $experiment" >&2
  exit 2
fi
for required in   "$base_model/config.json"   "$dataset/train.jsonl"   "$dataset/manifest.json"   "$dataset/validation.json"   "$workspace/scripts/full_sft_train_fsdp_scheduled.py"   "$workspace/scripts/prepare_codex_rft_full_sft_experiment.py"   "$workspace/scripts/build_codex_rft_full_sft_report.py"   "$workspace/scripts/plot_appworld_full_sft_loss.py"   "$workspace/scripts/verify_appworld_full_sft_model.py"   "$workspace/scripts/ddp_probe.py"; do
  test -f "$required" || { echo "Missing required input: $required" >&2; exit 2; }
done

mkdir -p "$experiment"/{artifacts,config,logs,metrics,probe,scripts_snapshot}
exec > >(tee -a "$experiment/logs/launcher.log") 2>&1

stage="initializing"
monitor_pid=""
cleanup() {
  status=$?
  if [[ -n "$monitor_pid" ]]; then
    kill "$monitor_pid" 2>/dev/null || true
    wait "$monitor_pid" 2>/dev/null || true
  fi
  if [[ $status -ne 0 ]]; then
    printf 'FAILED stage=%s exit_code=%s finished_at=%s\n' "$stage" "$status" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
  fi
  exit "$status"
}
trap cleanup EXIT

cp   "$workspace/scripts/full_sft_train_fsdp_scheduled.py"   "$workspace/scripts/prepare_codex_rft_full_sft_experiment.py"   "$workspace/scripts/build_codex_rft_full_sft_report.py"   "$workspace/scripts/plot_appworld_full_sft_loss.py"   "$workspace/scripts/verify_appworld_full_sft_model.py"   "$workspace/scripts/ddp_probe.py"   "$workspace/scripts/run_codex_rft_full_sft_train90.sh"   "$experiment/scripts_snapshot/"

stage="preparing_data"
printf 'RUNNING stage=%s started_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
"$python_bin" "$workspace/scripts/prepare_codex_rft_full_sft_experiment.py"   --dataset-dir "$dataset"   --model "$base_model"   --output-dir "$experiment/config"   --max-length 40960   --epochs 5   --learning-rate 1e-5   --weight-decay 0   --warmup-ratio 0.03   --min-lr-ratio 0.1   --max-grad-norm 1.0   --activation-offload-threshold 24576   --seed 20260922   2>&1 | tee "$experiment/logs/01_prepare.log"

{
  printf 'created_at=%s\n' "$(date --iso-8601=seconds)"
  printf 'workspace_commit=%s\n' "$(git -C "$workspace" rev-parse HEAD)"
  printf 'workspace_status_begin\n'
  git -C "$workspace" status --short
  printf 'workspace_status_end\n'
  printf 'hostname=%s\n' "$(hostname)"
  printf 'python=%s\n' "$("$python_bin" --version 2>&1)"
  "$python_bin" -c "import torch, transformers, accelerate; print('torch='+torch.__version__); print('transformers='+transformers.__version__); print('accelerate='+accelerate.__version__)"
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv,noheader
  df -h /root/autodl-tmp
  printf 'train_sha256=%s\n' "$(sha256sum "$dataset/train.jsonl" | cut -d' ' -f1)"
  printf 'manifest_sha256=%s\n' "$(sha256sum "$dataset/manifest.json" | cut -d' ' -f1)"
  printf 'validation_sha256=%s\n' "$(sha256sum "$dataset/validation.json" | cut -d' ' -f1)"
} > "$experiment/environment.txt"

cat > "$experiment/command.txt" <<EOF
CUDA_VISIBLE_DEVICES=0,1 PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True \
$torchrun_bin --standalone --nproc_per_node=2 scripts/full_sft_train_fsdp_scheduled.py \
  --model $base_model \
  --train-json $dataset/train.jsonl \
  --validation-json $experiment/config/diagnostic_last_step_per_task.jsonl \
  --experiment-dir $experiment \
  --max-length 40960 --epochs 5 --learning-rate 1e-5 --weight-decay 0 \
  --warmup-ratio 0.03 --min-lr-ratio 0.1 --max-grad-norm 1.0 --activation-cpu-offload --activation-offload-threshold 24576 \
  --seed 20260922 --save-every-epoch
EOF

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

stage="ddp_probe"
printf 'RUNNING stage=%s updated_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/ddp_probe.py"   2>&1 | tee "$experiment/logs/02_ddp_probe.log"

stage="longest_sample_probe"
printf 'RUNNING stage=%s updated_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/full_sft_train_fsdp_scheduled.py"   --model "$base_model"   --train-json "$experiment/config/probe_optimizer_state_then_longest.jsonl"   --validation-json "$experiment/config/probe_optimizer_state_then_longest.jsonl"   --experiment-dir "$experiment/probe"   --max-length 40960   --epochs 1   --learning-rate 1e-5   --weight-decay 0   --warmup-ratio 0   --min-lr-ratio 1   --max-grad-norm 1 --activation-cpu-offload --activation-offload-threshold 24576   --seed 20260922   --max-steps 2   --skip-validation   --skip-model-save   2>&1 | tee "$experiment/logs/03_longest_full_sft_probe.log"
"$python_bin" -c "import json; from pathlib import Path; p=Path('$experiment/probe/metrics/metrics.json'); m=json.loads(p.read_text()); assert m['status']=='PROBE_SUCCESS'; print(json.dumps(m['distributed']['ranks'], ensure_ascii=False))"

stage="training"
printf 'RUNNING stage=%s updated_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/full_sft_train_fsdp_scheduled.py"   --model "$base_model"   --train-json "$dataset/train.jsonl"   --validation-json "$experiment/config/diagnostic_last_step_per_task.jsonl"   --experiment-dir "$experiment"   --max-length 40960   --epochs 5   --learning-rate 1e-5   --weight-decay 0   --warmup-ratio 0.03   --min-lr-ratio 0.1   --max-grad-norm 1 --activation-cpu-offload --activation-offload-threshold 24576   --seed 20260922   --save-every-epoch   2>&1 | tee "$experiment/logs/04_train_full_sft.log"
"$python_bin" -c "import json; from pathlib import Path; m=json.loads(Path('$experiment/metrics/metrics.json').read_text()); assert m['status']=='SUCCESS' and m['training']['epochs_completed']==5 and m['training']['global_steps']==2925"

stage="generation_verify"
printf 'RUNNING stage=%s updated_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
set +e
CUDA_VISIBLE_DEVICES=0 "$python_bin" "$workspace/scripts/verify_appworld_full_sft_model.py"   --model "$experiment/artifacts/model"   --sample-json "$experiment/config/diagnostic_last_step_per_task.jsonl"   --output "$experiment/metrics/generation_smoke.json"   --max-input-length 40960   --max-new-tokens 512   > "$experiment/logs/05_generation_verify.log" 2>&1
verify_status=$?
set -e
printf '%s\n' "$verify_status" > "$experiment/metrics/generation_verify_exit_code.txt"

stage="finalizing"
printf 'RUNNING stage=%s updated_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
"$python_bin" "$workspace/scripts/plot_appworld_full_sft_loss.py"   --experiment "$experiment"   --expected-steps 2925   --steps-per-epoch 585   --moving-average 50   > "$experiment/logs/06_plot_loss.log" 2>&1

find "$experiment/artifacts/model" -maxdepth 1 -name '*.safetensors' -type f -print0   | sort -z | xargs -0 sha256sum > "$experiment/metrics/final_model_weights.sha256"

"$python_bin" "$workspace/scripts/build_codex_rft_full_sft_report.py"   --experiment "$experiment"   --lora-experiment "$lora_experiment"   > "$experiment/logs/07_report.log" 2>&1

if [[ -n "$monitor_pid" ]]; then
  kill "$monitor_pid" 2>/dev/null || true
  wait "$monitor_pid" 2>/dev/null || true
  monitor_pid=""
fi

if [[ $verify_status -eq 0 ]]; then
  final_status="SUCCESS"
else
  final_status="SUCCESS_WITH_GENERATION_WARNING"
fi
printf '%s epochs=5 steps=2925 generation_verify_exit_code=%s finished_at=%s\n'   "$final_status" "$verify_status" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"

find "$experiment/config" "$experiment/metrics" "$experiment/scripts_snapshot"   -type f -print0 | sort -z | xargs -0 sha256sum > "$experiment/artifacts.sha256"
sha256sum "$experiment/REPORT.md" "$experiment/EVAL_READY.md"   "$experiment/STATUS.txt" "$experiment/command.txt" "$experiment/environment.txt"   >> "$experiment/artifacts.sha256"
sha256sum -c "$experiment/artifacts.sha256" > "$experiment/logs/08_hash_verify.log"

trap - EXIT
echo "Full-parameter SFT completed: $experiment"
