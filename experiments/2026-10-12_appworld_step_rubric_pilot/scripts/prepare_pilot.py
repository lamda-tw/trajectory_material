"""Freeze a six-trajectory pilot and verify the versioned input adapter locally."""
from pathlib import Path
import collections
import hashlib
import json
import runpy
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parents[1]
SOURCE = WORKSPACE / "experiments/2026-10-08_static_rubric_grpo/runs/step01_train90_rollouts"
SAMPLES = {
    "302c169_2__02": "成功；闹钟时间变换与多个对象操作",
    "302c169_3__03": "失败；闹钟操作；已知孤立围栏解析边界",
    "cf6abd2_2__01": "成功；便签文本变换与错误恢复",
    "cf6abd2_2__02": "失败；同题便签操作；无代码终止",
    "e7a10f8_3__02": "成功；最长歌单时长聚合与交付",
    "e7a10f8_3__04": "失败；同题歌单聚合与交付",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    with path.open("x", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    old = runpy.run_path(str(ROOT / "snapshots/prepare_input_v1.py"))["prepare"]
    new = runpy.run_path(str(ROOT / "snapshots/prepare_input_v2.py"))["prepare"]
    index = {Path(x["trajectory"]).stem: x for x in json.loads((SOURCE / "trajectory_index.json").read_text())}
    stats = collections.Counter()
    old_errors, errors, rows = [], [], []
    for file in sorted((SOURCE / "trajectories").glob("*.json")):
        raw = file.read_bytes()
        data = json.loads(raw)
        assert sha(raw) == index[file.stem]["sha256"], file
        stats["source_hashes_verified"] += 1
        try:
            payload = new(data, "base:" + file.stem, "audit")
            assert [s["id"] for s in payload["steps"]] == [s["step"] for s in data["steps"]]
            assert set(payload) == {"output_mode", "trajectory_id", "task", "agent_instructions", "reference_api_docs", "steps", "termination"}
            stats["v2_compatible"] += 1
            stats["steps"] += len(payload["steps"])
            try:
                old_payload = old(data, "base:" + file.stem, "audit")
            except ValueError as e:
                old_errors.append({"file": file.name, "error": str(e)})
            else:
                assert payload == old_payload, "unexpected change to an already compatible input"
                stats["unchanged_v1_compatible_payloads"] += 1
            if file.stem in SAMPLES:
                destination = ROOT / "inputs" / file.name
                write_json(destination, payload)
                rows.append({"id": file.stem, "trajectory_id": payload["trajectory_id"],
                             "source": str(file), "source_sha256": sha(raw),
                             "policy_id": index[file.stem]["policy_id"],
                             "input": str(destination.relative_to(ROOT)),
                             "input_sha256": sha(destination.read_bytes()),
                             "steps": len(payload["steps"]), "input_characters": len(destination.read_text()),
                             "official_success_for_researcher_only": data["official_evaluation"]["success"],
                             "selection_reason": SAMPLES[file.stem], "termination": data["termination"]})
        except Exception as e:
            errors.append({"file": file.name, "error": repr(e)})
    # Regression on already reviewed SFT examples, without rescanning the SFT collection.
    plan = WORKSPACE / "plans/2026-10-12_appworld_step_rubric"
    sft = WORKSPACE / "experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories"
    for file in (plan / "inputs").glob("*.json"):
        assert new(json.loads((sft / file.name).read_text()), file.stem) == json.loads(file.read_text())
        stats["sft_example_payloads_unchanged"] += 1
    write_json(ROOT / "input_validation.json", {"stats": dict(stats), "old_errors": old_errors, "v2_errors": errors,
               "judge_calls": 0, "checks": "All base source hashes, exact step coverage, old-compatible payload equality; two saved SFT examples."})
    assert not errors and len(rows) == 6
    assert sum(r["official_success_for_researcher_only"] for r in rows) == 3
    rows.sort(key=lambda r: list(SAMPLES).index(r["id"]))
    write_json(ROOT / "manifest.json", {"purpose": "Development pilot; purposive selection, not an independent accuracy benchmark.",
               "source_directory": str(SOURCE), "input_preparer_version": "v2", "samples": rows,
               "scope": "Six complete base-policy trajectories, three success and three failure; no training or trajectory replay.",
               "prompt_sha256": sha((ROOT / "snapshots/prompt_v1.txt").read_bytes()),
               "schema_sha256": sha((ROOT / "snapshots/output_schema_v1.json").read_bytes()),
               "input_preparer_sha256": sha((ROOT / "snapshots/prepare_input_v2.py").read_bytes()),
               "warning": "Do not include this manifest or official outcomes in judge requests."})
    print(json.dumps({"selected": len(rows), "steps": sum(r["steps"] for r in rows), "validation": dict(stats)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
