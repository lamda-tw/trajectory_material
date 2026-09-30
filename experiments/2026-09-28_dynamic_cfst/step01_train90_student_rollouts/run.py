#!/usr/bin/env python3
"""Run the existing LoRA evaluator in this stage's isolated AppWorld root."""
from pathlib import Path
import datetime, fcntl, json, os, subprocess, sys
stage = Path(__file__).resolve().parent
manifest_path = stage / "manifest.json"
lock_file = open(stage / "logs/run.lock", "w")
fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
manifest = json.loads(manifest_path.read_text())
if manifest.get("status") == "completed":
    raise SystemExit("Already completed; refusing to run twice.")
if manifest.get("run_started_at") and "--resume" not in sys.argv:
    raise SystemExit("Previous attempt exists; inspect it before using --resume.")
env = os.environ.copy()
env.update({"APPWORLD_ROOT": str(stage), "APPWORLD_CACHE": str(stage / "cache"),
    "CUDA_VISIBLE_DEVICES": "0", "HF_HOME": str(stage / "cache/huggingface"),
    "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "TOKENIZERS_PARALLELISM": "false",
    "PYTHONUNBUFFERED": "1", "PYTHONDONTWRITEBYTECODE": "1", "NO_API_KEY": "none", "OPENAI_API_KEY": "none",
    "VLLM_CACHE_ROOT": str(stage / "cache/vllm"), "TORCHINDUCTOR_CACHE_DIR": str(stage / "cache/torchinductor"),
    "XDG_CACHE_HOME": str(stage / "cache/xdg")})
for name in ["HF_HOME", "VLLM_CACHE_ROOT", "TORCHINDUCTOR_CACHE_DIR", "XDG_CACHE_HOME"]:
    Path(env[name]).mkdir(parents=True, exist_ok=True)
python = "/root/autodl-tmp/envs/appworld-0.2.0-py312/bin/python"
cmd = [python, str(stage / "scripts_snapshot/appworld_run_isolated_lora_config.py"),
    "--root", str(stage), "--config-root", str(stage / "config/agent_configs"),
    "--model-path", manifest["model"], "--adapter-path", manifest["adapter"],
    "--vllm-bin", "/root/autodl-tmp/envs/qwen3-vllm-py312/bin/vllm",
    "--served-adapter-name", manifest["served_adapter_name"],
    "--model-config-name", manifest["model_config"], "--reasoning-parser", "none",
    "--dataset-name", "train", "--per-task-status-path", str(stage / "task_status.jsonl")]
manifest["status"] = "running"
manifest["run_started_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
manifest["supervisor_pid"] = os.getpid()
manifest["command_argv"] = cmd
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
(stage / "config/command_argv.json").write_text(json.dumps(cmd, ensure_ascii=False, indent=2) + "\n")
with open(stage / "logs/run.log", "a", buffering=1) as log:
    log.write("run_started_at=" + manifest["run_started_at"] + "\n")
    result = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, cwd=stage)
    manifest["run_finished_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    manifest["exit_code"] = result.returncode
    manifest["status"] = "awaiting_validation" if result.returncode == 0 else "run_error"
    log.write("run_finished_at=" + manifest["run_finished_at"] + "\nrun_exit_code=" + str(result.returncode) + "\n")
(stage / "logs/run_exit_code.txt").write_text(str(result.returncode) + "\n")
manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"status": manifest["status"], "exit_code": result.returncode}, ensure_ascii=False), flush=True)
sys.exit(result.returncode)
