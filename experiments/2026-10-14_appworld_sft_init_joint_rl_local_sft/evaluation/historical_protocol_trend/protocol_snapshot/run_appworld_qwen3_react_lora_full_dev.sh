#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -lt 2 || $# -gt 5 ]]; then
  echo "Usage: $0 EVALUATION_EXPERIMENT_ROOT LORA_ADAPTER_PATH [MODEL_CONFIG_NAME] [TASK_ID] [REASONING_PARSER]" >&2
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
experiment_root="$1"
adapter_path="$2"
launcher="$experiment_root/scripts_snapshot/appworld_run_isolated_lora_config.py"
model_config_name="${3:-qwen3-8b-with-reasoning}"
task_id="${4:-}"
if [[ "$task_id" == "-" ]]; then
  task_id=""
fi
reasoning_parser="${5:-auto}"
if [[ "$reasoning_parser" == "auto" ]]; then
  reasoning_parser="deepseek_r1"
  if [[ "$model_config_name" == "qwen3-8b-without-reasoning" ]]; then
    reasoning_parser="none"
  fi
fi
if [[ "$reasoning_parser" != "deepseek_r1" && "$reasoning_parser" != "none" ]]; then
  echo "Unsupported reasoning parser: $reasoning_parser" >&2
  exit 2
fi
run_log="$experiment_root/logs/run.log"
status_file="$experiment_root/logs/run_exit_code.txt"
model_server_pattern="^${vllm_env}/bin/python ${vllm_env}/bin/vllm serve ${model_path} "

if [[ "$experiment_root" != "$workspace"/experiments/*_appworld_qwen3-8b_react_lora_* ]]; then
  echo "Refusing unexpected evaluation root: $experiment_root" >&2
  exit 2
fi
if [[ "$model_config_name" != "qwen3-8b-with-reasoning" && "$model_config_name" != "qwen3-8b-without-reasoning" ]]; then
  echo "Unsupported model config: $model_config_name" >&2
  exit 2
fi
if [[ "$adapter_path" != "$workspace"/experiments/*/artifacts/* ]]; then
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
printf 'experiment_root=%s\nadapter_path=%s\nmodel_config_name=%s\nreasoning_parser=%s\ntask_id=%s\n' \
  "$experiment_root" "$adapter_path" "$model_config_name" "$reasoning_parser" "$task_id"
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader

launcher_args=(
  --root "$experiment_root"
  --config-root "$experiment_root/config/agent_configs"
  --model-path "$model_path"
  --adapter-path "$adapter_path"
  --vllm-bin "$vllm_env/bin/vllm"
  --model-config-name "$model_config_name"
  --served-adapter-name "appworld-codex-rft-train90-epoch5"
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
