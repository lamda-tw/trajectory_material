"""Shared CPU-only preparation utilities. Importing this module launches nothing."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv, hashlib, json, os, sys

R = Path(__file__).resolve().parents[1]
W = R.parents[1]
sys.path.insert(0, str(R / "runtime_code"))
CPU_ENV = dict(os.environ, CUDA_VISIBLE_DEVICES="", HIP_VISIBLE_DEVICES="",
               OMP_NUM_THREADS="1", MKL_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
               HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1", USE_TORCH="0", USE_TF="0",
               TOKENIZERS_PARALLELISM="false", PYTHONUNBUFFERED="1")

def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()

def read(path):
    return json.loads(Path(path).read_text())

def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()

def write_json(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)

def frozen_json(path, value):
    path = Path(path)
    if path.exists():
        if read(path) != value:
            raise ValueError(f"Refusing to overwrite different frozen data: {path}")
    else:
        write_json(path, value)

def rows():
    result = []
    for name in ("states_selected.csv", "calibration_states.csv"):
        with (R / "plan_snapshot" / name).open() as handle:
            result.extend(csv.DictReader(handle))
    return result

def check_frozen():
    for name, expected in read(R / "config/frozen_source_manifest.json")["sha256"].items():
        if sha(R / name) != expected:
            raise ValueError(f"Frozen dependency changed: {name}")

def record_status(stage, **details):
    write_json(R / "STATUS.json", {"updated_at": now(), "stage": stage,
        "gpu_allowed": False, "local_model_generation_started": False,
        "training_started": False, "automatic_gpu_resume": False, **details})
