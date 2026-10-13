"""Prepare and hash all base inputs; never call a judge or execute a trajectory."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import hashlib
import json
import runpy

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT.parent / "2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, data):
    with path.open("x") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    prepare = runpy.run_path(str(ROOT / "snapshots/prepare_input_v3.py"))["prepare"]
    index = json.loads((SOURCE / "trajectory_index.json").read_text())
    destination = ROOT / "inputs_v4_corpus"
    destination.mkdir(exist_ok=False)
    samples = []
    for row in index:
        source = Path(row["trajectory"])
        raw = source.read_bytes()
        assert sha(raw) == row["sha256"], source
        sid = source.stem
        payload = prepare(json.loads(raw), "base:"+sid)
        assert len(payload["steps"]) == row["steps"]
        path = destination / (sid+".json")
        save(path, payload)
        samples.append({"id": sid, "trajectory_id": payload["trajectory_id"], "task_id": row["task_id"],
                        "source": str(source), "source_sha256": sha(raw), "policy_id": row["policy_id"],
                        "input": str(path.relative_to(ROOT)), "input_sha256": sha(path.read_bytes()),
                        "steps": row["steps"], "input_characters": len(path.read_text()),
                        "official_success_for_researcher_only": row["success"], "termination": row["termination"]})
    manifest = {"purpose": "Prepared full corpus for v4; preparation does not authorize or launch full scoring.",
                "prepared_at": datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(),
                "input_preparer_version": "v3", "input_preparer_sha256": sha((ROOT / "snapshots/prepare_input_v3.py").read_bytes()),
                "prompt_sha256": sha((ROOT / "snapshots/prompt_v4.txt").read_bytes()),
                "schema_sha256": sha((ROOT / "snapshots/output_schema_v4.json").read_bytes()),
                "warning": "Never include manifest or official outcomes in a judge input.", "samples": samples}
    save(ROOT / "manifest_v4_corpus.json", manifest)
    sizes = sorted(s["input_characters"] for s in samples)
    stats = {"trajectories": len(samples), "tasks": len({s["task_id"] for s in samples}),
             "steps": sum(s["steps"] for s in samples), "input_characters_total": sum(sizes),
             "size_quantiles_characters": {str(q): sizes[round((len(sizes)-1)*q)] for q in [0, .5, .9, .95, .99, 1]},
             "largest": sorted(samples, key=lambda s: s["input_characters"], reverse=True)[:5]}
    save(ROOT / "v4_corpus_preflight.json", stats)
    print(json.dumps({k: v for k, v in stats.items() if k != "largest"}, ensure_ascii=False))
    for s in stats["largest"]:
        print(s["id"], s["steps"], s["input_characters"])


if __name__ == "__main__":
    main()
