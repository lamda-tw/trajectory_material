"""Run a frozen prompt on the selected inputs. Explicit --execute is required."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path
import argparse
import hashlib
import json
import shutil
import subprocess
import time

import jsonschema

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def dump(path, data):
    with path.open("x", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def validate(result, payload, schema):
    jsonschema.Draft202012Validator(schema).validate(result)
    assert result["trajectory_id"] == payload["trajectory_id"], "trajectory ID mismatch"
    assert result["output_mode"] == payload["output_mode"], "mode mismatch"
    ids = [s["id"] for s in payload["steps"]]
    assert [row[0] for row in result["steps"]] == ids, "step coverage/order mismatch"
    covered = set()
    for target, rubrics, evidence, reason in result["notes"]:
        assert target in ids and set(evidence) <= set(ids), "invalid evidence ID"
        for rubric in rubrics.split(","):
            covered.add((target, rubric))
    if result["output_mode"] == "audit":
        missing = [(step, f"R{i+1}") for step, labels in result["steps"]
                   for i, label in enumerate(labels) if label in "FU" and (step, f"R{i+1}") not in covered]
        assert not missing, f"unexplained F/U: {missing}"


def audit_events(path):
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    completed = [e for e in events if e.get("type") == "turn.completed"]
    assert completed, "no completed turn"
    assert not any(e.get("type") == "turn.failed" for e in events), "failed turn"
    forbidden = [e.get("item", {}).get("type") for e in events
                 if "item" in e and e["item"].get("type") not in {"agent_message", "reasoning", "todo_list"}]
    assert not forbidden, f"forbidden tool events: {forbidden}"
    return {"usage": completed[-1].get("usage"), "event_types": [e.get("type") for e in events],
            "tool_items": forbidden, "nonfatal_error_events": [e for e in events if e.get("type") == "error"]}


def command(config, cwd, response):
    cmd = [shutil.which("codex"), "exec", "--ephemeral", "--ignore-user-config", "--ignore-rules",
           "--skip-git-repo-check", "--color", "never", "--sandbox", "read-only"]
    for feature in ["shell_tool", "unified_exec", "apps", "plugins", "multi_agent", "browser_use",
                    "browser_use_external", "computer_use", "image_generation", "view_image", "sleep_tool",
                    "skill_search", "code_mode_host"]:
        cmd += ["--disable", feature]
    return cmd + ["-c", 'web_search="disabled"', "--cd", str(cwd), "--output-last-message", str(response),
                  "--model", config["model"], "-c", f'model_reasoning_effort="{config["reasoning_effort"]}"', "--json", "-"]


def score(sample, run, config, template, schema):
    destination = run / sample["id"]
    destination.mkdir(exist_ok=False)
    payload_path = ROOT / sample["input"]
    raw = payload_path.read_bytes()
    assert sha(raw) == sample["input_sha256"]
    payload = json.loads(raw)
    prompt = template.replace("{{TRAJECTORY_JSON}}", raw.decode())
    (destination / "request.txt").write_text(prompt)
    (destination / "input.json").write_bytes(raw)
    cwd = destination / "empty_cwd"
    cwd.mkdir()
    start = time.monotonic()
    metadata = {"started_at": now(), "input_sha256": sha(raw), "request_sha256": sha(prompt.encode()),
                "source_sha256": sample["source_sha256"], "policy_id": sample["policy_id"],
                "prompt_sha256": sha(template.encode()), "model": config["model"],
                "reasoning_effort": config["reasoning_effort"], "attempts": []}
    print(json.dumps({"event": "started", "id": sample["id"], "time": now()}, ensure_ascii=False), flush=True)
    for number in range(1, config["max_attempts"] + 1):
        attempt = destination / f"attempt_{number}"
        attempt.mkdir()
        response = attempt / "response.json"
        cmd = command(config, cwd, response)
        dump(attempt / "command.json", cmd)
        began = time.monotonic()
        record = {"attempt": number, "started_at": now()}
        try:
            with (attempt / "events.jsonl").open("w") as stdout, (attempt / "stderr.log").open("w") as stderr:
                completed = subprocess.run(cmd, input=prompt, text=True, stdout=stdout, stderr=stderr,
                                           timeout=config["timeout_seconds"])
            record["returncode"] = completed.returncode
            assert completed.returncode == 0, f"Codex exit {completed.returncode}"
            audit = audit_events(attempt / "events.jsonl")
            result = json.loads(response.read_text())
            validate(result, payload, schema)
            record.update({"status": "valid", "elapsed_seconds": time.monotonic()-began, "audit": audit})
            metadata["attempts"].append(record)
            metadata.update({"status": "valid", "elapsed_seconds": time.monotonic()-start, "completed_at": now()})
            dump(destination / "judgement.json", result)
            dump(destination / "metadata.json", metadata)
            print(json.dumps({"event": "valid", "id": sample["id"], "seconds": metadata["elapsed_seconds"], "usage": audit["usage"]}, ensure_ascii=False), flush=True)
            return {"id": sample["id"], "status": "valid", "steps": len(result["steps"]), "metadata": metadata}
        except (AssertionError, OSError, ValueError, subprocess.TimeoutExpired, jsonschema.ValidationError) as e:
            record.update({"status": "invalid", "error": f"{type(e).__name__}: {e}", "elapsed_seconds": time.monotonic()-began})
            metadata["attempts"].append(record)
            dump(attempt / "failure.json", record)
            print(json.dumps({"event": "attempt_failed", "id": sample["id"], **record}, ensure_ascii=False), flush=True)
    metadata.update({"status": "failed", "elapsed_seconds": time.monotonic()-start, "completed_at": now()})
    dump(destination / "metadata.json", metadata)
    return {"id": sample["id"], "status": "failed", "metadata": metadata}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--run", required=True)
    parser.add_argument("--prompt", default="snapshots/prompt_v1.txt")
    parser.add_argument("--schema", default="snapshots/output_schema_v1.json")
    parser.add_argument("--ids", nargs="*")
    args = parser.parse_args()
    if not args.execute:
        parser.error("Real scoring requires --execute")
    assert Path(args.run).name == args.run and args.run not in {".", ".."}
    config = json.loads((ROOT / "judge_config.json").read_text())
    manifest = json.loads((ROOT / "manifest.json").read_text())
    samples = manifest["samples"]
    if args.ids:
        assert set(args.ids) <= {s["id"] for s in samples}
        samples = [s for s in samples if s["id"] in args.ids]
    template = (ROOT / args.prompt).read_text()
    assert template.count("{{TRAJECTORY_JSON}}") == 1
    schema = json.loads((ROOT / args.schema).read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    config["prompt_version"] = schema["properties"]["rubric_version"]["const"]
    run = ROOT / "runs" / args.run
    run.mkdir(exist_ok=False)
    (run / "prompt.txt").write_text(template)
    dump(run / "schema.json", schema)
    dump(run / "config.json", config)
    dump(run / "run_manifest.json", {"started_at": now(), "ids": [s["id"] for s in samples],
         "prompt_sha256": sha(template.encode()), "schema_sha256": sha((ROOT / args.schema).read_bytes()),
         "runner_sha256": sha(Path(__file__).read_bytes()), "config_sha256": sha((ROOT / "judge_config.json").read_bytes()),
         "manifest_sha256": sha((ROOT / "manifest.json").read_bytes()),
         "codex_version": subprocess.check_output([shutil.which("codex"), "--version"], text=True).strip()})
    results = []
    with ThreadPoolExecutor(max_workers=config["max_workers"]) as pool:
        futures = [pool.submit(score, sample, run, config, template, schema) for sample in samples]
        for future in as_completed(futures):
            results.append(future.result())
    dump(run / "summary.json", {"completed_at": now(), "results": results,
         "valid": sum(r["status"] == "valid" for r in results), "requested": len(samples)})
    if any(r["status"] != "valid" for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
