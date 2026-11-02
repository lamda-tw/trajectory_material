"""Prepare whole-trajectory judge inputs and exact pre-action messages on CPU."""
from common import *
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, re, subprocess


def registry_task(task):
    # Isolated read-only simulator API query for redaction only; no agent actions,
    # ground truth, hidden evaluator or source-trajectory execution.
    runtime = R / "runtime/redaction" / task
    runtime.mkdir(parents=True, exist_ok=True)
    data = read(R / "config/source_evaluation.json")["paths"]["appworld_data"]
    if not (runtime / "data").exists():
        (runtime / "data").symlink_to(data, target_is_directory=True)
    os.environ.update(CPU_ENV)
    os.environ["APPWORLD_ROOT"] = str(runtime)
    os.environ["APPWORLD_CACHE"] = str(runtime / "cache")
    os.chdir(runtime)
    from appworld import AppWorld, update_root
    update_root(str(runtime))
    with AppWorld(task_id=task, experiment_name="redaction_only", load_ground_truth=False, random_seed=100) as world:
        values = sorted(set(x["password"] for x in world.apis.supervisor.show_account_passwords()))
    assert values and all(isinstance(x, str) and x for x in values)
    path = R / "runtime/redaction_credentials" / (task + ".json")
    write_json(path, values); path.chmod(0o600)


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, list):
        for item in value: yield from strings(item)
    elif isinstance(value, dict):
        for item in value.values(): yield from strings(item)


def sanitize(source, task):
    values = set(read(R / "runtime/redaction_credentials" / (task + ".json")))
    keyed = re.compile(r'''["'](?:(?:new_|old_|current_)?password|access_token|refresh_token|api_key|secret_key)["']\s*:\s*["']([^"'\n]+)["']''')
    keyword = re.compile(r'''\b(?:[A-Za-z_]\w*_)?(?:password|access_token|refresh_token|api_key|secret_key)\s*=\s*["']([^"'\n]+)["']''')
    jwt = re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b')
    source_strings = list(strings(source))
    for text in source_strings:
        values.update(m.group(1) for p in (keyed, keyword) for m in p.finditer(text))
        values.update(jwt.findall(text))
    values = {x for x in values if x not in ("", "string", "...") and not x.startswith("<CREDENTIAL_")}
    ordered = sorted(values, key=len, reverse=True)
    mapping = {x: "<CREDENTIAL_" + hashlib.sha256(x.encode()).hexdigest()[:24] + ">" for x in ordered}
    def replace(value):
        if isinstance(value, str):
            for secret in ordered: value = value.replace(secret, mapping[secret])
            return value
        if isinstance(value, list): return [replace(x) for x in value]
        if isinstance(value, dict): return {k: replace(v) for k, v in value.items()}
        return value
    clean = replace(source)
    assert all(not any(secret in text for secret in ordered) for text in strings(clean))
    assert all(not jwt.search(text) for text in strings(clean))
    audit = {"task_registry_used": True, "equality_preserved": True,
        "credential_values_replaced": sum(any(secret in text for text in source_strings) for secret in ordered),
        "hidden_evaluator_included": False, "official_success_included": False}
    return clean, audit, ordered


def main():
    os.environ.update(CPU_ENV)
    check_frozen()
    selected = rows()
    tasks = sorted({row["task_id"] for row in selected})
    appworld_python = read(R / "config/source_evaluation.json")["paths"]["appworld_python"]
    def registry(task):
        dest = R / "runtime/redaction_credentials" / (task + ".json")
        if not dest.exists():
            log = R / "logs/redaction" / (task + ".log"); log.parent.mkdir(parents=True, exist_ok=True)
            with log.open("a") as handle:
                subprocess.run([appworld_python, str(Path(__file__).resolve()), "--registry-task", task],
                    env=CPU_ENV, cwd=R, stdout=handle, stderr=subprocess.STDOUT, check=True, timeout=300)
        return {"task_id": task, "credential_count": len(read(dest)), "registry_sha256": sha(dest)}
    registries = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        for future in as_completed([pool.submit(registry, t) for t in tasks]):
            registries.append(future.result())
            if len(registries) % 10 == 0:
                print(json.dumps({"event": "redaction_registry", "done": len(registries), "total": len(tasks)}), flush=True)
    write_json(R / "phase_a/config/redaction_audit.json", {"tasks": sorted(registries, key=lambda x:x["task_id"]),
        "purpose": "local replacement only; no credentials or account metadata added to judge evidence"})
    from transformers import AutoTokenizer
    from prepare_input_v3 import prepare
    base = Path(read(R / "config/source_evaluation.json")["paths"]["base_model"])
    tokenizer = AutoTokenizer.from_pretrained(str(base), local_files_only=True)
    manifest = []
    for n, row in enumerate(selected, 1):
        source = Path(row["source"])
        assert sha(source) == row["source_sha256"], row["id"]
        trajectory = read(source); step = int(row["step"]); original = trajectory["steps"][step-1]
        assert digest(original["prompt_ids"]) == row["prompt_ids_sha256"]
        assert digest(original["response_ids"]) == row["original_response_ids_sha256"]
        assert hashlib.sha256(original["text"].encode()).hexdigest() == row["original_text_sha256"]
        messages = [dict(m) for m in trajectory["initial_messages"]]
        for prior in trajectory["steps"][:step-1]:
            messages.append({"role":"assistant", "content": prior["history_assistant_text"] + "\n\n"})
            if prior["code"]:
                messages.append({"role":"user", "content":"Output:\n```\n" + prior["observation"].rstrip() + "\n```\n\n"})
        ids = tokenizer.apply_chat_template(messages, tools=None, tokenize=True, add_generation_prompt=True, enable_thinking=False)
        assert ids == original["prompt_ids"], row["id"]
        clean, redaction, secrets = sanitize(trajectory, row["task_id"])
        # v3 may normalize already-redacted credential placeholders again; this
        # remains equality-preserving across the complete prepared trajectory.
        payload = prepare(clean, row["public_state_id"])
        assert set(payload) == {"trajectory_id","task","agent_instructions","reference_api_docs","steps","termination"}
        assert all(not any(secret in text for secret in secrets) for text in strings(payload))
        payload["feedback_step_ids"] = [step]
        input_path = R / "phase_a/inputs/judge" / (row["public_state_id"] + ".json")
        frozen_json(input_path, payload)
        original_path = R / "phase_a/inputs/policy" / (row["public_state_id"] + ".json")
        frozen_json(original_path, {"state": row, "messages": messages, "prompt_ids": ids,
            "original_response_ids": original["response_ids"], "original_answer": original["text"],
            "source": str(source), "history_steps": step-1, "credential_scope":"local policy input only"})
        manifest.append({**row, "target_step": step, "trajectory_steps":len(payload["steps"]),
            "input": str(input_path.relative_to(R)), "input_sha256":sha(input_path),
            "policy_input":str(original_path.relative_to(R)), "policy_input_sha256":sha(original_path),
            "exact_prompt_tokens":True, "redaction":redaction})
        if n % 20 == 0: print(json.dumps({"event":"inputs", "done":n, "total":len(selected)}), flush=True)
    frozen_json(R / "phase_a/config/source_manifest.json", {"samples":manifest,
        "model_path":str(base), "tokenizer_sha256":sha(base/"tokenizer.json"),
        "tokenizer_config_sha256":sha(base/"tokenizer_config.json"),
        "source_trajectories":len(manifest), "tasks":len(tasks),
        "full_source_step_rows":sum(x["trajectory_steps"] for x in manifest),
        "all_prompt_tokens_exact":True, "model_weights_loaded":False,
        "gpu_touched":False, "trajectory_replay_performed":False})
    record_status("cpu_inputs_ready", states=len(manifest), tasks=len(tasks), source_scoring="not_started")
    print(json.dumps({"event":"ready", "states":len(manifest), "tasks":len(tasks), "gpu_touched":False}), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry-task")
    args = parser.parse_args()
    if args.registry_task: registry_task(args.registry_task)
    else: main()
