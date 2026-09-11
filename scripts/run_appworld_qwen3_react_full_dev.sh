#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 EXPERIMENT_ROOT" >&2
  exit 2
fi

APPWORLD_ENV="/root/autodl-tmp/envs/appworld-0.2.0-py312"
VLLM_ENV="/root/autodl-tmp/envs/qwen3-vllm-py312"
MODEL_PATH="/root/autodl-tmp/models/Qwen3-8B"
SOURCE_DATA="/root/autodl-tmp/data/benchmarks/appworld/runtime/data"
SOURCE_TESTS="/root/autodl-tmp/workspace-tw/experiments/2026-09-10_173848_appworld_qwen3-8b_react_oneshot_smoke/cache/tests"
INSTALLED_AGENT_CONFIGS="/root/autodl-tmp/envs/appworld-0.2.0-py312/lib/python3.12/site-packages/appworld_agents/configs"
LAUNCHER="/root/autodl-tmp/workspace-tw/scripts/appworld_run_isolated_config.py"
EXPERIMENT_ROOT="$1"
RUN_LOG="${EXPERIMENT_ROOT}/logs/run.log"
STATUS_FILE="${EXPERIMENT_ROOT}/logs/run_exit_code.txt"
MODEL_SERVER_PATTERN="^${VLLM_ENV}/bin/python ${VLLM_ENV}/bin/vllm serve ${MODEL_PATH} "

if [[ "${EXPERIMENT_ROOT}" != /root/autodl-tmp/workspace-tw/experiments/*_appworld_qwen3-8b_react_oneshot_full_dev ]]; then
  echo "Refusing unexpected experiment root: ${EXPERIMENT_ROOT}" >&2
  exit 2
fi

if pgrep -f "${MODEL_SERVER_PATTERN}" >/dev/null; then
  echo "A matching Qwen3 vLLM server is already running; refusing to interfere." >&2
  exit 1
fi

mkdir -p "${EXPERIMENT_ROOT}/data/datasets" "${EXPERIMENT_ROOT}/logs" "${EXPERIMENT_ROOT}/config/agent_configs"

# APPWORLD_CACHE must include evaluator test assets. Copy the small verified
# cache so Python cannot mutate the prior experiment through a directory link.
if [[ ! -d "${EXPERIMENT_ROOT}/cache/tests/package/apps" ]]; then
  cp -a "${SOURCE_TESTS}" "${EXPERIMENT_ROOT}/cache/tests"
fi

if [[ ! -e "${EXPERIMENT_ROOT}/config/agent_configs/_generator" && ! -L "${EXPERIMENT_ROOT}/config/agent_configs/_generator" ]]; then
  ln -s "${INSTALLED_AGENT_CONFIGS}/_generator" "${EXPERIMENT_ROOT}/config/agent_configs/_generator"
fi

for item in CHANGELOG.md LICENSE api_docs base_dbs tasks version.txt; do
  if [[ ! -e "${EXPERIMENT_ROOT}/data/${item}" && ! -L "${EXPERIMENT_ROOT}/data/${item}" ]]; then
    ln -s "${SOURCE_DATA}/${item}" "${EXPERIMENT_ROOT}/data/${item}"
  fi
done

if [[ ! -e "${EXPERIMENT_ROOT}/data/datasets/dev.txt" && ! -L "${EXPERIMENT_ROOT}/data/datasets/dev.txt" ]]; then
  ln -s "${SOURCE_DATA}/datasets/dev.txt" "${EXPERIMENT_ROOT}/data/datasets/dev.txt"
fi

export APPWORLD_ROOT="${EXPERIMENT_ROOT}"
export APPWORLD_CACHE="${EXPERIMENT_ROOT}/cache"
export CUDA_VISIBLE_DEVICES="0"
export HF_HOME="${EXPERIMENT_ROOT}/cache/huggingface"
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"
export TOKENIZERS_PARALLELISM="false"
export PYTHONUNBUFFERED="1"
export PYTHONDONTWRITEBYTECODE="1"
export NO_API_KEY="none"
export OPENAI_API_KEY="none"
export VLLM_CACHE_ROOT="${EXPERIMENT_ROOT}/cache/vllm"
export TORCHINDUCTOR_CACHE_DIR="${EXPERIMENT_ROOT}/cache/torchinductor"
export XDG_CACHE_HOME="${EXPERIMENT_ROOT}/cache/xdg"

mkdir -p "${APPWORLD_CACHE}" "${HF_HOME}" "${VLLM_CACHE_ROOT}" "${TORCHINDUCTOR_CACHE_DIR}" "${XDG_CACHE_HOME}"
exec > >(tee -a "${RUN_LOG}") 2>&1

cleanup_model_server() {
  pkill -TERM -f "${MODEL_SERVER_PATTERN}" 2>/dev/null || true
}
trap cleanup_model_server EXIT

printf 'run_started_at=%s\n' "$(date --iso-8601=seconds)"
printf 'experiment_root=%s\n' "${EXPERIMENT_ROOT}"
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader

set +e
"${APPWORLD_ENV}/bin/python" "${LAUNCHER}" \
  --root "${EXPERIMENT_ROOT}" \
  --config-root "${EXPERIMENT_ROOT}/config/agent_configs" \
  --model-path "${MODEL_PATH}" \
  --vllm-bin "${VLLM_ENV}/bin/vllm"
run_status=$?
set -e

printf '%s\n' "${run_status}" > "${STATUS_FILE}"
printf 'run_finished_at=%s\n' "$(date --iso-8601=seconds)"
printf 'run_exit_code=%s\n' "${run_status}"
exit "${run_status}"
