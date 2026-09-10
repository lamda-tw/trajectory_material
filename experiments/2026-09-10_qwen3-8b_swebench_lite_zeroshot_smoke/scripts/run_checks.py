#!/usr/bin/env python3
"""Apply official test patches after inference and run non-authoritative local checks."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq


EXPERIMENT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((EXPERIMENT / "config.json").read_text(encoding="utf-8"))
PYTHON = Path("/root/autodl-tmp/workspace-tw/.conda-training/bin/python")


def run(
    command: list[str],
    *,
    cwd: Path,
    input_text: str | None = None,
    timeout: int = 240,
) -> dict:
    started = datetime.now(timezone.utc)
    try:
        result = subprocess.run(
            command,
            cwd=cwd,
            input=input_text,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env={
                **os.environ,
                "PYTHONPATH": str(cwd),
                "PYTHONDONTWRITEBYTECODE": "1",
                "XDG_CACHE_HOME": str(EXPERIMENT / "cache" / "xdg"),
            },
        )
        return {
            "command": command,
            "started_at_utc": started.isoformat(),
            "exit_code": result.returncode,
            "output": result.stdout,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        if isinstance(output, bytes):
            output = output.decode(errors="replace")
        return {
            "command": command,
            "started_at_utc": started.isoformat(),
            "exit_code": None,
            "output": output,
            "timed_out": True,
        }


def main() -> None:
    checks_dir = EXPERIMENT / "checks"
    logs_dir = EXPERIMENT / "logs"
    checks_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)

    selected = {
        json.loads(line)["instance_id"]
        for line in (EXPERIMENT / "data" / "selected_tasks.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    raw_rows = {
        row["instance_id"]: row
        for row in pq.read_table(CONFIG["raw_parquet"]).to_pylist()
        if row["instance_id"] in selected
    }
    predictions = {
        row["instance_id"]: row
        for row in (
            json.loads(line)
            for line in (EXPERIMENT / "predictions.jsonl").read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    }

    all_results: list[dict] = []
    for instance_id in CONFIG["instance_ids"]:
        repo = EXPERIMENT / "worktrees" / instance_id
        raw = raw_rows[instance_id]
        prediction = predictions[instance_id]
        result: dict = {
            "instance_id": instance_id,
            "authoritative": False,
            "environment": "shared host Python 3.12, not the official SWE-bench Docker image",
            "model_patch_nonempty": bool(prediction["model_patch"].strip()),
            "test_patch_applied": False,
            "fail_to_pass": None,
            "pass_to_pass": None,
            "smoke_resolved": False,
        }
        if not result["model_patch_nonempty"]:
            result["note"] = "No applicable model patch was produced; tests skipped."
            all_results.append(result)
            continue

        patch_check = run(
            ["git", "apply", "--check", "--whitespace=nowarn", "-"],
            cwd=repo,
            input_text=raw["test_patch"],
        )
        if patch_check["exit_code"] != 0:
            result["note"] = "Official test patch could not be applied after the model patch."
            result["test_patch_error"] = patch_check["output"]
            all_results.append(result)
            continue
        patch_apply = run(
            ["git", "apply", "--whitespace=nowarn", "-"],
            cwd=repo,
            input_text=raw["test_patch"],
        )
        if patch_apply["exit_code"] != 0:
            result["note"] = "Official test patch application failed."
            result["test_patch_error"] = patch_apply["output"]
            all_results.append(result)
            continue
        result["test_patch_applied"] = True

        fail_command = [str(PYTHON), "-m", "pytest", "-q", *raw["FAIL_TO_PASS"]]
        pass_command = [str(PYTHON), "-m", "pytest", "-q", *raw["PASS_TO_PASS"]]
        result["fail_to_pass"] = run(fail_command, cwd=repo)
        result["pass_to_pass"] = run(pass_command, cwd=repo)
        result["smoke_resolved"] = (
            result["fail_to_pass"]["exit_code"] == 0
            and result["pass_to_pass"]["exit_code"] == 0
        )
        result["note"] = (
            "Local smoke tests passed, but this is not an official score."
            if result["smoke_resolved"]
            else "Local checks failed or hit an environment incompatibility; inspect the logs."
        )

        for group in ("fail_to_pass", "pass_to_pass"):
            payload = result[group]
            (logs_dir / f"{instance_id}.{group}.log").write_text(
                payload["output"], encoding="utf-8"
            )
            payload["output_log"] = f"logs/{instance_id}.{group}.log"
            del payload["output"]
        all_results.append(result)

    output = {
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "authoritative": False,
        "reason": "Official per-instance Docker images/harness are unavailable on this host.",
        "results": all_results,
    }
    (checks_dir / "local_checks.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
