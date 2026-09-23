#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 2 || $# -gt 6 ]]; then
  echo "Usage: $0 EVALUATION_EXPERIMENT_ROOT FULL_MODEL_PATH [MODEL_LABEL] [MODEL_CONFIG_NAME] [TASK_ID] [REASONING_PARSER]" >&2
  exit 2
fi

workspace="/root/autodl-tmp/workspace-tw"
appworld_env="/root/autodl-tmp/envs/appworld-0.2.0-py312"
vllm_env="/root/autodl-tmp/envs/qwen3-vllm-py312"
source_data="/root/autodl-tmp/data/benchmarks/appworld/runtime/data"
source_tests="$workspace/experiments/2026-09-10_173848_appworld_qwen3-8b_react_oneshot_smoke/cache/tests"
installed_agent_configs="$appworld_env/lib/python3.12/site-packages/appworld_agents/configs"
launcher="$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/appworld_run_isolated_full_model_config.py"
experiment_root="$1"
model_path="$2"
model_label="${3:-full-sft}"
model_config_name="${4:-qwen3-8b-with-reasoning}"
task_id="${5:-}"
[[ "$task_id" != "-" ]] || task_id=""
reasoning_parser="${6:-none}"
run_log="$experiment_root/logs/run.log"
status_file="$experiment_root/logs/run_exit_code.txt"
served_model_name="appworld-qwen3-8b-$model_label"
model_server_pattern="^${vllm_env}/bin/python ${vllm_env}/bin/vllm serve ${model_path} "

if [[ "$experiment_root" != "$workspace"/experiments/*_appworld_qwen3-8b_react_full_sft_* ]]; then
  echo "Refusing unexpected evaluation root: $experiment_root" >&2
  exit 2
fi
model_path="$(realpath -e "$model_path")"
if [[ "$model_path" != "$workspace"/experiments/*/artifacts/model && "$model_path" != "$workspace"/experiments/*/artifacts/checkpoints/epoch_*_model ]]; then
  echo "Refusing model path outside workspace experiment artifacts: $model_path" >&2
  exit 2
fi
if [[ "$(realpath -m "$experiment_root")" != "$experiment_root" ]]; then
  echo "Refusing a non-canonical evaluation root: $experiment_root" >&2
  exit 2
fi
if [[ "$model_config_name" != "qwen3-8b-with-reasoning" && "$model_config_name" != "qwen3-8b-without-reasoning" ]]; then
  echo "Unsupported model config: $model_config_name" >&2
  exit 2
fi
if [[ "$reasoning_parser" != "deepseek_r1" && "$reasoning_parser" != "none" ]]; then
  echo "Unsupported reasoning parser: $reasoning_parser" >&2
  exit 2
fi
for required in config.json tokenizer_config.json model.safetensors.index.json; do
  test -f "$model_path/$required" || { echo "Missing model file: $model_path/$required" >&2; exit 2; }
done
if pgrep -f "$model_server_pattern" >/dev/null; then
  echo "A matching full-model vLLM server is already running; refusing to interfere." >&2
  exit 1
fi

mkdir -p "$experiment_root/data/datasets" "$experiment_root/logs" "$experiment_root/config/agent_configs" "$experiment_root/cache"
if [[ ! -d "$experiment_root/cache/tests/package/apps" ]]; then
  cp -a "$source_tests" "$experiment_root/cache/tests"
fi
if [[ ! -e "$experiment_root/config/agent_configs/_generator" ]]; then
  ln -s "$installed_agent_configs/_generator" "$experiment_root/config/agent_configs/_generator"
fi
for item in CHANGELOG.md LICENSE api_docs base_dbs tasks version.txt; do
  if [[ ! -e "$experiment_root/data/$item" ]]; then
    ln -s "$source_data/$item" "$experiment_root/data/$item"
  fi
done
if [[ ! -e "$experiment_root/data/datasets/dev.txt" ]]; then
  ln -s "$source_data/datasets/dev.txt" "$experiment_root/data/datasets/dev.txt"
fi

export APPWORLD_ROOT="$experiment_root"
export APPWORLD_CACHE="$experiment_root/cache"
export CUDA_VISIBLE_DEVICES="0"
export HF_HOME="$experiment_root/cache/huggingface"
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"
export TOKENIZERS_PARALLELISM="false"
export PYTHONUNBUFFERED="1"
export PYTHONDONTWRITEBYTECODE="1"
export NO_API_KEY="none"
export OPENAI_API_KEY="none"
export VLLM_CACHE_ROOT="$experiment_root/cache/vllm"
export TORCHINDUCTOR_CACHE_DIR="$experiment_root/cache/torchinductor"
export XDG_CACHE_HOME="$experiment_root/cache/xdg"
# Unix-domain socket paths must fit within 107 bytes, including a UUID.
export TMPDIR="$workspace/tmp/aw-$(printf '%s' "$experiment_root" | sha256sum | cut -c1-12)"
export TMP="$TMPDIR"
export TEMP="$TMPDIR"
export TRITON_CACHE_DIR="$experiment_root/cache/triton"
export CUDA_CACHE_PATH="$experiment_root/cache/cuda"
export NUMBA_CACHE_DIR="$experiment_root/cache/numba"
export MPLCONFIGDIR="$experiment_root/cache/matplotlib"
mkdir -p "$TMPDIR" "$TRITON_CACHE_DIR" "$CUDA_CACHE_PATH" "$NUMBA_CACHE_DIR" "$MPLCONFIGDIR" "$workspace/tmp"
exec 9>"$workspace/tmp/full_sft_gpu.lock"
flock -n 9 || { echo 'Another full SFT training or evaluation holds the GPU lock'; exit 2; }
mkdir -p "$APPWORLD_CACHE" "$HF_HOME" "$VLLM_CACHE_ROOT" "$TORCHINDUCTOR_CACHE_DIR" "$XDG_CACHE_HOME"
exec > >(tee -a "$run_log") 2>&1

cleanup_model_server() {
  pkill -TERM -f "$model_server_pattern" 2>/dev/null || true
}
trap cleanup_model_server EXIT
printf 'run_started_at=%s\n' "$(date --iso-8601=seconds)"
printf 'experiment_root=%s\nmodel_path=%s\nmodel_label=%s\nmodel_config_name=%s\nreasoning_parser=%s\ntask_id=%s\n' \
  "$experiment_root" "$model_path" "$model_label" "$model_config_name" "$reasoning_parser" "$task_id"
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader

launcher_args=(
  --root "$experiment_root"
  --config-root "$experiment_root/config/agent_configs"
  --model-path "$model_path"
  --vllm-bin "$vllm_env/bin/vllm"
  --served-model-name "$served_model_name"
  --model-config-name "$model_config_name"
  --reasoning-parser "$reasoning_parser"
  --per-task-status-path "$experiment_root/task_status.jsonl"
)
if [[ -n "$task_id" ]]; then
  launcher_args+=(--task-id "$task_id")
fi

set +e
"$appworld_env/bin/python" "$launcher" "${launcher_args[@]}"
run_status=$?
set -e
printf '%s\n' "$run_status" > "$status_file"
printf 'run_finished_at=%s\nrun_exit_code=%s\n' "$(date --iso-8601=seconds)" "$run_status"
exit "$run_status"
