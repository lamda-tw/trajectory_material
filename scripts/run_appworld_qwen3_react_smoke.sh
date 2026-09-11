#!/usr/bin/env bash
set -euo pipefail

APPWORLD_ENV="/root/autodl-tmp/envs/appworld-0.2.0-py312"
VLLM_ENV="/root/autodl-tmp/envs/qwen3-vllm-py312"
APPWORLD_ROOT="/root/autodl-tmp/workspace-tw/experiments/2026-09-10_173848_appworld_qwen3-8b_react_oneshot_smoke"
MODEL_PATH="/root/autodl-tmp/models/Qwen3-8B"
RUN_LOG="${APPWORLD_ROOT}/logs/run.log"
VLLM_PROCESS_PATTERN="^/root/autodl-tmp/envs/qwen3-vllm-py312/bin/python /root/autodl-tmp/envs/qwen3-vllm-py312/bin/vllm serve /root/autodl-tmp/models/Qwen3-8B "
if pgrep -f "${VLLM_PROCESS_PATTERN}" >/dev/null; then echo "A matching Qwen3 vLLM server is already running; refusing to stop another run." >&2; exit 1; fi
cleanup_model_server() { pkill -TERM -f "${VLLM_PROCESS_PATTERN}" 2>/dev/null || true; }
trap cleanup_model_server EXIT

export APPWORLD_ROOT
export APPWORLD_CACHE="${APPWORLD_ROOT}/cache"
export CUDA_VISIBLE_DEVICES="0"
export HF_HOME="${APPWORLD_ROOT}/cache/huggingface"
export HF_HUB_OFFLINE="1"
export TRANSFORMERS_OFFLINE="1"
export TOKENIZERS_PARALLELISM="false"
export PYTHONUNBUFFERED="1"
export NO_API_KEY="none"
export OPENAI_API_KEY="none"
export VLLM_CACHE_ROOT="${APPWORLD_ROOT}/cache/vllm"
export TORCHINDUCTOR_CACHE_DIR="${APPWORLD_ROOT}/cache/torchinductor"
export XDG_CACHE_HOME="${APPWORLD_ROOT}/cache/xdg"

mkdir -p "${APPWORLD_CACHE}" "${HF_HOME}" "${APPWORLD_ROOT}/logs"
exec > >(tee -a "${RUN_LOG}") 2>&1

date --iso-8601=seconds
nvidia-smi --query-gpu=index,name,memory.total,memory.free --format=csv,noheader

MODEL_SERVER_COMMAND="${VLLM_ENV}/bin/vllm serve ${MODEL_PATH} --served-model-name Qwen/Qwen3-8B --reasoning-parser deepseek_r1 --max-num-seqs 3 --max-model-len 32000 --enable-auto-tool-choice --tool-call-parser hermes --port {port}"
OVERRIDE="{\"config\":{\"model_server\":{\"command\":\"${MODEL_SERVER_COMMAND}\",\"timeout\":1200,\"show_logs\":true}}}"

"${APPWORLD_ENV}/bin/appworld" run auto \
  --agent-name simplified_react_code_agent \
  --model-name qwen3-8b-with-reasoning \
  --dataset-name dev_smoke_50e1ac9 \
  --root "${APPWORLD_ROOT}" \
  --num-processes 1 \
  --with-evaluation \
  --override "${OVERRIDE}"

date --iso-8601=seconds
