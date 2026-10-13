"""Resumable, bounded-concurrency v5 scoring. Evaluation runs separately."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
import argparse
import fcntl
import hashlib
import heapq
import json
import os
import random
import signal
import subprocess
import threading
import time

from judge_protocol import audit_events, command, validate

ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.RLock()
ACTIVE = {}
TIMING = {}
PROMPT_HASH = "df4e8fb406551f2d90e38bbe83838db181bda18e01d947b236ee10a05c633109"


def now():
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()


def read(path):
    return json.loads(path.read_text())


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def atomic(path, data):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    os.replace(temporary, path)


def event(kind, **kwargs):
    with LOCK:
        value = {"event": kind, "at": now(), **kwargs}
        line = json.dumps(value, ensure_ascii=False)
        with (ROOT / "logs/scoring_events.jsonl").open("a") as f:
            f.write(line + "\n")
        print(line, flush=True)


def auth_fingerprint():
    auth = read(Path(os.environ.get("CODEX_HOME", "/root/.codex")) / "auth.json")
    assert auth.get("auth_mode") == "chatgpt" and not auth.get("OPENAI_API_KEY"), "Authentication mode changed"
    for key in ["OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"]:
        assert not os.environ.get(key), f"Unexpected {key} override"
    return sha(str(auth.get("tokens", {}).get("account_id", "")).encode())[:12]


def classify(errors):
    message = errors.lower()
    if any(s in message for s in ["usage limit", "usage_limit", "limit resets", "credits remaining", "insufficient_quota"]):
        return "usage_limit"
    if any(s in message for s in ["401 unauthorized", "refresh_token_reused", "not logged in", "authentication token", "invalid api key"]):
        return "authentication"
    if any(s in message for s in ["at capacity", "rate limit", "429", "overloaded"]):
        return "capacity_or_rate_limit"
    if any(s in message for s in ["context length", "context window", "too many tokens"]):
        return "context_limit"
    return "other"


def failure_detail(attempt):
    errors = []
    path = attempt / "events.jsonl"
    if path.exists():
        for line in path.read_text().splitlines():
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get("type") in {"error", "turn.failed"}:
                errors.append(e)
    return errors


def prior_attempts(folder):
    records = []
    for attempt in sorted(folder.glob("attempt_*")):
        if (attempt / "record.json").exists():
            records.append(read(attempt / "record.json"))
    return records


def commit(folder, sample, payload, schema, record, result, config):
    validate(result, payload, schema)
    atomic(folder / "judgement.json", result)
    atomic(folder / "metadata.json", {
        "id": sample["id"], "status": "valid", "completed_at": now(),
        "accepted_attempt": record["attempt"], "input_sha256": sample["input_sha256"],
        "source_sha256": sample["source_sha256"], "prompt_sha256": PROMPT_HASH,
        "model": config["model"], "reasoning_effort": config["reasoning_effort"],
        "attempts": prior_attempts(folder), "selection": "First valid response; no best-of selection",
    })


def attempt_score(sample, config, template, schema, expected_account):
    sid = sample["id"]
    folder = ROOT / "runs/scoring" / sid
    folder.mkdir(parents=True, exist_ok=True)
    raw = (ROOT / sample["input"]).read_bytes()
    assert sha(raw) == sample["input_sha256"]
    payload = json.loads(raw)
    request = template.replace("{{TRAJECTORY_JSON}}", raw.decode())
    for filename, content in [("input.json", raw), ("request.txt", request.encode())]:
        path = folder / filename
        if path.exists():
            assert path.read_bytes() == content
        else:
            path.write_bytes(content)
    cwd = folder / "empty_cwd"
    cwd.mkdir(exist_ok=True)
    old = sorted(folder.glob("attempt_*"))
    # A process may have finished before the parent persisted acceptance.
    for prior in old:
        if (prior / "record.json").exists() and read(prior / "record.json").get("status") == "valid":
            result = read(prior / "response.json")
            audit_events(prior / "events.jsonl")
            commit(folder, sample, payload, schema, read(prior / "record.json"), result, config)
            return {"id": sid, "status": "valid", "recovered_without_call": True}
    number = max([int(p.name.split('_')[-1]) for p in old], default=0) + 1
    attempt = folder / f"attempt_{number:03d}"
    attempt.mkdir()
    record = {"attempt": number, "started_at": now(), "start_epoch": time.time()}
    if auth_fingerprint() != expected_account:
        raise RuntimeError("Server scoring account changed; refusing to switch account silently")
    cmd = command(config, cwd, attempt / "response.json")
    atomic(attempt / "command.json", cmd)
    began = time.monotonic()
    with LOCK:
        if not TIMING.get("scoring_started_at"):
            TIMING.update(scoring_started_at=now(), scoring_start_epoch=time.time(), phase="scoring")
            atomic(ROOT / "TIMING.json", TIMING)
        ACTIVE[sid] = {"attempt": number, "started_at": record["started_at"], "start_epoch": record["start_epoch"]}
    event("attempt_started", id=sid, attempt=number)
    proc = None
    try:
        with (attempt / "events.jsonl").open("w") as stdout, (attempt / "stderr.log").open("w") as stderr:
            proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, text=True, stdout=stdout, stderr=stderr, start_new_session=True)
            atomic(attempt / "RUNNING.json", {**record, "pid": proc.pid, "pgid": proc.pid})
            try:
                proc.communicate(request, timeout=config["timeout_seconds"])
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                raise
        record["returncode"] = proc.returncode
        assert proc.returncode == 0, f"Codex exit {proc.returncode}"
        audit = audit_events(attempt / "events.jsonl")
        result = read(attempt / "response.json")
        validate(result, payload, schema)
        record.update(status="valid", audit=audit, elapsed_seconds=time.monotonic()-began, completed_at=now())
        atomic(attempt / "record.json", record)
        commit(folder, sample, payload, schema, record, result, config)
        event("valid", id=sid, attempt=number, seconds=record["elapsed_seconds"], usage=audit.get("usage"))
        return {"id": sid, "status": "valid"}
    except Exception as exc:
        details = failure_detail(attempt)
        message = f"{type(exc).__name__}: {exc}"
        category = classify(message + json.dumps(details))
        record.update(status="invalid", error=message, category=category, service_errors=details,
                      elapsed_seconds=time.monotonic()-began, completed_at=now())
        atomic(attempt / "record.json", record)
        atomic(folder / "metadata.json", {"id": sid, "status": "pending_retry", "attempts": prior_attempts(folder)})
        event("attempt_failed", id=sid, attempt=number, category=category, error=message, service_errors=details)
        return {"id": sid, "status": "invalid", "category": category}
    finally:
        with LOCK:
            ACTIVE.pop(sid, None)
        if (attempt / "RUNNING.json").exists():
            (attempt / "RUNNING.json").unlink()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true", required=True)
    args = parser.parse_args()
    lockfile = (ROOT / "logs/scoring.lock").open("a")
    fcntl.flock(lockfile, fcntl.LOCK_EX | fcntl.LOCK_NB)
    atomic(ROOT / "logs/scoring_process.json", {"pid": os.getpid(), "started_at": now()})
    config = read(ROOT / "judge_config.json")
    manifest = read(ROOT / "manifest.json")
    schema = read(ROOT / "assets/output_schema_v6.json")
    template = (ROOT / "assets/prompt_v6_en.txt").read_text()
    assert sha(template.encode()) == PROMPT_HASH
    assert config["model"] == "gpt-6.1-sol" and config["reasoning_effort"] == "high"
    expected_account = read(ROOT / "AUTH_PROVENANCE.json")["account_fingerprint"]
    assert auth_fingerprint() == expected_account
    (ROOT / "runs/scoring").mkdir(exist_ok=True)
    snapshot = ROOT / "runs/scoring/runner_snapshot.py"
    if not snapshot.exists():
        snapshot.write_bytes(Path(__file__).read_bytes())
    if (ROOT / "TIMING.json").exists():
        TIMING.update(read(ROOT / "TIMING.json"))
    else:
        TIMING.update(experiment_prepared_at=read(ROOT / "STATUS.json")["prepared_at"], phase="prepared")
    invocations = TIMING.setdefault("invocations", [])
    invocations.append({"started_at": now(), "runner_sha256": sha(Path(__file__).read_bytes())})
    atomic(ROOT / "TIMING.json", TIMING)
    by_id = {s["id"]: s for s in manifest["samples"]}
    assert len(by_id) == 540
    valid, pending, exhausted = set(), [], {}
    for sid, sample in by_id.items():
        folder = ROOT / "runs/scoring" / sid
        if (folder / "judgement.json").exists():
            validate(read(folder / "judgement.json"), read(ROOT / sample["input"]), schema)
            meta = read(folder / "metadata.json")
            assert meta["prompt_sha256"] == PROMPT_HASH
            valid.add(sid)
        else:
            pending.append(sid)
    random.Random(config["sample_order_seed"]).shuffle(pending)
    queue = [(0, i, sid) for i, sid in enumerate(pending)]
    heapq.heapify(queue)
    retries, futures = {}, {}
    sequence = len(queue)
    global_wait_until = 0.0
    last_heartbeat = 0.0
    concurrency = config.get("initial_workers", config["max_workers"])
    last_throttle_valid = len(valid)
    if len(valid) == 540 and TIMING.get("scoring_finished_at"):
        event("already_complete", wall_seconds=TIMING["scoring_wall_seconds"])
        return

    def heartbeat(phase="scoring"):
        with LOCK:
            atomic(ROOT / "STATUS.json", {
                "updated_at": now(), "phase": phase, "pid": os.getpid(), "valid": len(valid), "total": 540,
                "steps_valid": sum(by_id[s]["steps"] for s in valid), "total_steps": 11254,
                "queued": len(queue), "active": dict(ACTIVE), "exhausted": exhausted,
                "concurrency_limit": concurrency,
                "scoring_started_at": TIMING.get("scoring_started_at"),
                "scoring_elapsed_seconds": time.time()-TIMING["scoring_start_epoch"] if TIMING.get("scoring_start_epoch") else 0,
                "global_wait_until_epoch": global_wait_until, "prompt_sha256": PROMPT_HASH,
            })

    event("invocation_started", already_valid=len(valid), new_pending=len(pending))
    with ThreadPoolExecutor(max_workers=config["max_workers"]) as pool:
        while queue or futures:
            wall = time.time()
            while queue and len(futures) < concurrency and queue[0][0] <= wall and global_wait_until <= wall:
                _, _, sid = heapq.heappop(queue)
                future = pool.submit(attempt_score, by_id[sid], config, template, schema, expected_account)
                futures[future] = sid
            if futures:
                done, _ = wait(futures, timeout=5, return_when=FIRST_COMPLETED)
                for future in done:
                    sid = futures.pop(future)
                    try:
                        result = future.result()
                    except Exception as exc:
                        result = {"id": sid, "status": "invalid", "category": "driver_error", "error": str(exc)}
                        event("driver_sample_error", **result)
                    if result["status"] == "valid":
                        valid.add(sid)
                        if len(valid)-last_throttle_valid >= config.get("ramp_after_valid", 12) and concurrency < config["max_workers"]:
                            concurrency = min(config["max_workers"], concurrency*2)
                            last_throttle_valid = len(valid)
                            event("concurrency_changed", limit=concurrency, reason="stable_completed_calls")
                    else:
                        retries[sid] = retries.get(sid, 0)+1
                        category = result["category"]
                        if category == "capacity_or_rate_limit":
                            concurrency = max(1, concurrency//2)
                            last_throttle_valid = len(valid)
                            global_wait_until = max(global_wait_until, time.time()+60)
                            event("concurrency_changed", limit=concurrency, reason="capacity_or_rate_limit")
                        if category == "authentication":
                            global_wait_until = max(global_wait_until, time.time()+900)
                        elif category == "usage_limit":
                            global_wait_until = max(global_wait_until, time.time()+1800)
                        if retries[sid] >= config["max_attempts"] or category in {"authentication", "context_limit", "driver_error"}:
                            exhausted[sid] = result
                            event("sample_needs_recovery", **result)
                        else:
                            delay = config["retry_delays_seconds"][min(retries[sid]-1, len(config["retry_delays_seconds"])-1)]
                            heapq.heappush(queue, (time.time()+delay, sequence, sid))
                            sequence += 1
            else:
                time.sleep(5)
            if time.monotonic()-last_heartbeat >= 30:
                heartbeat()
                last_heartbeat = time.monotonic()
        if len(valid) == 540:
            with LOCK:
                end = time.time()
                TIMING.update(phase="scoring_complete", scoring_finished_at=now(), scoring_end_epoch=end,
                              scoring_wall_seconds=end-TIMING["scoring_start_epoch"])
                atomic(ROOT / "TIMING.json", TIMING)
            heartbeat("scoring_complete")
            event("scoring_complete", trajectories=540, steps=11254, wall_seconds=TIMING["scoring_wall_seconds"])
        else:
            heartbeat("scoring_needs_recovery")
            event("scoring_incomplete", valid=len(valid), exhausted=exhausted)
            raise SystemExit(1)


if __name__ == "__main__":
    main()
