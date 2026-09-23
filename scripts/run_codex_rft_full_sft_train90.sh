#!/usr/bin/env bash
set -Eeuo pipefail
workspace="/root/autodl-tmp/workspace-tw"
[[ $# -ge 1 && $# -le 2 ]] || { echo "Usage: $0 EXPERIMENT_DIR [--resume]" >&2; exit 2; }
resume=false
if [[ $# -eq 2 ]]; then [[ "$2" == --resume ]] || exit 2; resume=true; fi
experiment="$(realpath -e "$1")"
[[ "$experiment" == "$workspace"/experiments/*_appworld_qwen3-8b_full_sft_codex_rft_train90_epoch5 ]] || exit 2
[[ -f "$experiment/config/training_config.json" ]] || exit 2
if [[ "$resume" == true ]]; then
  [[ -f "$experiment/artifacts/restart/latest.json" ]] || { echo 'No completed restart state found.' >&2; exit 2; }
else
  [[ ! -f "$experiment/metrics/training_history.jsonl" ]] || { echo 'Use --resume for an existing run.' >&2; exit 2; }
fi
python_bin="$workspace/.conda-training/bin/python"
torchrun_bin="$workspace/.conda-training/bin/torchrun"
base_model="/root/autodl-tmp/models/Qwen3-8B"
dataset="$workspace/data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90"
export TMPDIR="$experiment/tmp"
export XDG_CACHE_HOME="$experiment/cache"
export HF_HOME="$experiment/cache/huggingface"
export TORCH_HOME="$experiment/cache/torch"
export TRITON_CACHE_DIR="$experiment/cache/triton"
export TORCHINDUCTOR_CACHE_DIR="$experiment/cache/inductor"
export CUDA_CACHE_PATH="$experiment/cache/cuda"
export MPLCONFIGDIR="$experiment/cache/matplotlib"
export CUDA_VISIBLE_DEVICES=0,1
export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True
export TORCH_NCCL_ASYNC_ERROR_HANDLING=1
export TOKENIZERS_PARALLELISM=false
export HF_HUB_OFFLINE=1
export TRANSFORMERS_OFFLINE=1
export OMP_NUM_THREADS=4
mkdir -p "$TMPDIR" "$XDG_CACHE_HOME"
exec 9>"$workspace/tmp/full_sft_gpu.lock"
flock -n 9 || { echo 'Another full SFT launcher holds the GPU lock'; exit 2; }
exec > >(tee -a "$experiment/logs/launcher.log") 2>&1
stage=initializing
monitor_pid=''
cleanup() {
  code=$?
  trap - EXIT
  if [[ -n "$monitor_pid" ]]; then kill "$monitor_pid" 2>/dev/null || true; wait "$monitor_pid" 2>/dev/null || true; fi
  if [[ $code -ne 0 ]]; then printf 'FAILED stage=%s exit_code=%s finished_at=%s\n' "$stage" "$code" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"; fi
  exit "$code"
}
trap cleanup EXIT
set_stage() { stage="$1"; printf 'RUNNING stage=%s updated_at=%s\n' "$stage" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"; }
cp "$workspace/scripts/"{full_sft_train_fsdp_scheduled.py,full_sft_runtime.py,prepare_codex_rft_full_sft_experiment.py,test_full_sft_runtime.py,test_full_sft_distributed_resume.py,monitor_full_sft_resources.py,run_codex_rft_full_sft_train90.sh,ddp_probe.py} "$experiment/scripts_snapshot/"
environment_file="$experiment/environment.txt"
if [[ "$resume" == true ]]; then environment_file="$experiment/environment_resume.txt"; fi
{
  printf 'workspace_commit=%s\n' "$(git -C "$workspace" rev-parse HEAD)"
  "$python_bin" -c 'import torch,transformers; print("torch="+torch.__version__); print("transformers="+transformers.__version__)'
  nvidia-smi --query-gpu=index,name,driver_version,memory.total --format=csv
  df -h "$workspace"
} > "$environment_file"
git -C "$workspace" diff > "$experiment/scripts_snapshot/workspace.patch"
"$python_bin" "$workspace/scripts/monitor_full_sft_resources.py" --experiment "$experiment" &
monitor_pid=$!
common=(--model "$base_model" --max-length 40960 --learning-rate 1e-5 --weight-decay 0 --max-grad-norm 1 --seed 20260921)
if [[ "$resume" == false ]]; then
set_stage ddp_probe
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/ddp_probe.py" 2>&1 | tee "$experiment/logs/02_ddp_probe.log"
probe=("${common[@]}" --train-json "$experiment/config/probe_stress_40.jsonl" --validation-json "$experiment/config/probe_stress_40.jsonl" --experiment-dir "$experiment/probe" --epochs 1 --warmup-ratio 0 --min-lr-ratio 1 --sequential-sampler --checkpoint-every 10 --skip-model-save)
if [[ ! -f "$experiment/probe/artifacts/restart/latest.json" ]]; then
set_stage stress_probe_save
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/full_sft_train_fsdp_scheduled.py" "${probe[@]}" --stop-after-step 10 2>&1 | tee "$experiment/logs/03a_stress_probe.log"
cp "$experiment/probe/metrics/metrics.json" "$experiment/probe/metrics/before_restart.json"
fi
set_stage stress_probe_resume
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/full_sft_train_fsdp_scheduled.py" "${probe[@]}" --resume "$experiment/probe/artifacts/restart" --resume-allow-code-change 2>&1 | tee "$experiment/logs/03b_stress_resume.log"
"$python_bin" - "$experiment" <<'PY'
import json, shutil, sys
from pathlib import Path
exp=Path(sys.argv[1])
m=json.loads((exp/'probe/metrics/metrics.json').read_text())
assert m['status']=='SUCCESS' and m['training']['global_steps']==20 and m['training']['epochs_completed']==1
assert m['model']['trainable_percent']==100
assert m['validation']['completion_target_tokens']>0
assert all(r['peak_allocated_gib']<90 for r in m['distributed']['ranks']),m['distributed']['ranks']
# This disposable probe is never the source of the formal model/optimizer.
shutil.rmtree(exp/'probe/artifacts/restart')
assert shutil.disk_usage(exp).free>192*1024**3
print('PASS: 20-update dual-GPU stress, validation and real checkpoint reload; probe state removed.')
PY
fi
set_stage training
train=("${common[@]}" --train-json "$dataset/train.jsonl" --validation-json "$experiment/config/diagnostic_last_step_per_task.jsonl" --experiment-dir "$experiment" --epochs 5 --warmup-ratio 0.03 --min-lr-ratio 0.1 --checkpoint-every 585)
command_file="$experiment/command.txt"
training_log="$experiment/logs/04_train_full_sft.log"
if [[ "$resume" == true ]]; then
  train+=(--resume "$experiment/artifacts/restart")
  command_file="$experiment/command_resume.txt"
  training_log="$experiment/logs/04b_train_full_sft_resume.log"
fi
printf '%q ' "$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/full_sft_train_fsdp_scheduled.py" "${train[@]}" > "$command_file"
printf '\n' >> "$command_file"
"$torchrun_bin" --standalone --nproc_per_node=2 "$workspace/scripts/full_sft_train_fsdp_scheduled.py" "${train[@]}" 2>&1 | tee -a "$training_log"
"$python_bin" - "$experiment" <<'PY'
import json,sys
from pathlib import Path
m=json.loads((Path(sys.argv[1])/'metrics/metrics.json').read_text())
assert m['status']=='SUCCESS' and m['training']['epochs_completed']==5 and m['training']['global_steps']==2925
PY
set_stage generation_verify
set +e
CUDA_VISIBLE_DEVICES=0 "$python_bin" "$workspace/scripts/verify_appworld_full_sft_model.py" --model "$experiment/artifacts/model" --sample-json "$experiment/config/diagnostic_last_step_per_task.jsonl" --output "$experiment/metrics/generation_smoke.json" --max-input-length 40960 --max-new-tokens 512 > "$experiment/logs/05_generation_verify.log" 2>&1
verify_status=$?
set -e
printf '%s\n' "$verify_status" > "$experiment/metrics/generation_verify_exit_code.txt"
set_stage finalizing
"$python_bin" "$workspace/scripts/plot_appworld_full_sft_loss.py" --experiment "$experiment" --expected-steps 2925 --steps-per-epoch 585 --moving-average 50 > "$experiment/logs/06_plot_loss.log" 2>&1
"$python_bin" "$workspace/scripts/compare_appworld_full_sft_loss.py" --experiment "$experiment" > "$experiment/logs/06b_compare_loss.log" 2>&1
find "$experiment/artifacts/model" -maxdepth 1 -name '*.safetensors' -type f -print0 | sort -z | xargs -0 sha256sum > "$experiment/metrics/final_model_weights.sha256"
"$python_bin" "$workspace/scripts/build_codex_rft_full_sft_report.py" --experiment "$experiment" --lora-experiment "$workspace/experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5" > "$experiment/logs/07_report.log" 2>&1
cp "$workspace/scripts/"{plot_appworld_full_sft_loss.py,compare_appworld_full_sft_loss.py,build_codex_rft_full_sft_report.py,verify_appworld_full_sft_model.py} "$experiment/scripts_snapshot/"
if [[ $verify_status -eq 0 ]]; then final_status=SUCCESS; else final_status=SUCCESS_WITH_GENERATION_WARNING; fi
printf '%s epochs=5 steps=2925 generation_verify_exit_code=%s finished_at=%s\n' "$final_status" "$verify_status" "$(date --iso-8601=seconds)" > "$experiment/STATUS.txt"
find "$experiment/config" "$experiment/metrics" "$experiment/scripts_snapshot" -type f -print0 | sort -z | xargs -0 sha256sum > "$experiment/artifacts.sha256"
sha256sum "$experiment/REPORT.md" "$experiment/EVAL_READY.md" "$experiment/STATUS.txt" "$experiment/command.txt" >> "$experiment/artifacts.sha256"
if [[ -f "$experiment/command_resume.txt" ]]; then sha256sum "$experiment/command_resume.txt" >> "$experiment/artifacts.sha256"; fi
sha256sum -c "$experiment/artifacts.sha256" > "$experiment/logs/08_hash_verify.log"
echo "Full SFT completed: $experiment"
