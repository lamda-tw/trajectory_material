#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "Usage: $0 EVALUATION_EXPERIMENT_ROOT LORA_ADAPTER_PATH" >&2
  exit 2
fi

workspace="/root/autodl-tmp/workspace-tw"
appworld_env="/root/autodl-tmp/envs/appworld-0.2.0-py312"
vllm_env="/root/autodl-tmp/envs/qwen3-vllm-py312"
model_path="$workspace/models/Qwen3-8B"
if [[ ! -d "$model_path" ]]; then
  model_path="/root/autodl-tmp/models/Qwen3-8B"
fi
source_data="/root/autodl-tmp/data/benchmarks/appworld/runtime/data"
source_tests="$workspace/experiments/2026-09-10_173848_appworld_qwen3-8b_react_oneshot_smoke/cache/tests"
installed_agent_configs="$appworld_env/lib/python3.12/site-packages/appworld_agents/configs"
launcher="$workspace/scripts/appworld_run_isolated_lora_config.py"
experiment_root="$1"
adapter_path="$2"
run_log="$experiment_root/logs/run.log"
status_file="$experiment_root/logs/run_exit_code.txt"
model_server_pattern="^${vllm_env}/bin/python ${vllm_env}/bin/vllm serve ${model_path} "

if [[ "$experiment_root" != "$workspace"/experiments/*_appworld_qwen3-8b_react_lora_full_dev ]]; then
  echo "Refusing unexpected evaluation root: $experiment_root" >&2
  exit 2
fi
if [[ "$adapter_path" != "$workspace"/experiments/*/artifacts/adapter ]]; then
  echo "Refusing adapter path outside a workspace experiment: $adapter_path" >&2
  exit 2
fi
for required in adapter_config.json adapter_model.safetensors tokenizer_config.json; do
  test -f "$adapter_path/$required" || { echo "Missing adapter file: $adapter_path/$required" >&2; exit 2; }
done
if pgrep -f "$model_server_pattern" >/dev/null; then
  echo "A matching Qwen3 vLLM server is already running; refusing to interfere." >&2
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
mkdir -p "$APPWORLD_CACHE" "$HF_HOME" "$VLLM_CACHE_ROOT" "$TORCHINDUCTOR_CACHE_DIR" "$XDG_CACHE_HOME"
exec > >(tee -a "$run_log") 2>&1

cleanup_model_server() {
  pkill -TERM -f "$model_server_pattern" 2>/dev/null || true
}
trap cleanup_model_server EXIT
printf 'run_started_at=%s\n' "$(date --iso-8601=seconds)"
printf 'experiment_root=%s\nadapter_path=%s\n' "$experiment_root" "$adapter_path"
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader

set +e
"$appworld_env/bin/python" "$launcher" \
  --root "$experiment_root" \
  --config-root "$experiment_root/config/agent_configs" \
  --model-path "$model_path" \
  --adapter-path "$adapter_path" \
  --vllm-bin "$vllm_env/bin/vllm"
run_status=$?
set -e
printf '%s\n' "$run_status" > "$status_file"
printf 'run_finished_at=%s\nrun_exit_code=%s\n' "$(date --iso-8601=seconds)" "$run_status"
exit "$run_status"
