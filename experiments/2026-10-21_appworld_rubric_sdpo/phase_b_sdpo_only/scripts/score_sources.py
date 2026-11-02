"""Score existing complete trajectories with remote Codex; no local model/GPU."""
from common import *
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse, jsonschema, shutil, subprocess, time
import judge_protocol
import validate_v7_feedback


def validate(result, payload, variant):
    schema_path = R / "config" / ("output_schema_v7_feedback.json" if variant == "feedback" else "output_schema_v7.json")
    schema = read(schema_path)
    if variant == "feedback":
        jsonschema.Draft202012Validator(schema).validate(result)
        # Token budget and semantic quality are eligibility checks, never reasons
        # to resample an otherwise valid scoring result.
        validate_v7_feedback.validate(payload, result)
    else:
        judge_protocol.validate(result, payload, schema)


def score(sample, variant, config, stage):
    key = sample["public_state_id"]
    dest = R / "phase_a/judging" / stage / key / variant
    dest.mkdir(parents=True, exist_ok=True)
    source_path = R / sample["input"]
    assert sha(source_path) == sample["input_sha256"]
    payload = read(source_path)
    if variant == "base": payload.pop("feedback_step_ids", None)
    template_path = R / "config" / ("scoring_prompt_v7_feedback_en.txt" if variant == "feedback" else "scoring_prompt_v7_en.txt")
    prompt = template_path.read_text().replace("{{TRAJECTORY_JSON}}", json.dumps(payload, ensure_ascii=False, indent=2))
    request_hash = hashlib.sha256(prompt.encode()).hexdigest()
    identity = {"request_sha256":request_hash, "input_sha256":sample["input_sha256"],
        "template_sha256":sha(template_path), "config_sha256":sha(R/"config/judge.json"),
        "variant":variant, "source_sha256":sample["source_sha256"]}
    frozen_json(dest / "identity.json", identity)
    frozen_json(dest / "input.json", payload)
    if (dest / "judgement.json").exists():
        validate(read(dest/"judgement.json"), payload, variant)
        return {"state_id":key, "variant":variant, "status":"valid", "cached":True}
    (dest / "request.txt").write_text(prompt)
    cwd = dest / "empty_cwd"; cwd.mkdir(exist_ok=True)
    meta_path = dest / "metadata.json"
    meta = read(meta_path) if meta_path.exists() else {"started_at":now(), "identity":identity, "attempts":[]}
    assert meta["identity"] == identity
    # Recover a completed attempt if the parent process died before recording it.
    for folder in sorted(dest.glob("attempt_*")):
        if (folder/"response.json").exists():
            try:
                audit = judge_protocol.audit_events(folder/"events.jsonl")
                result = read(folder/"response.json"); validate(result, payload, variant)
            except (OSError, ValueError, AssertionError, jsonschema.ValidationError, KeyError, TypeError):
                continue
            write_json(dest/"judgement.json", result)
            meta.update(status="valid", completed_at=now(), audit=audit, recovered_attempt=folder.name)
            write_json(meta_path,meta)
            return {"state_id":key,"variant":variant,"status":"valid","recovered":True}
    transport_failures = sum(x.get("failure_type")=="transport" for x in meta["attempts"])
    format_repairs = sum(x.get("kind")=="format_repair" for x in meta["attempts"])
    next_kind = "initial" if not meta["attempts"] else "transport_retry"
    current_prompt = prompt
    if meta["attempts"] and meta["attempts"][-1].get("failure_type") == "format":
        previous = meta["attempts"][-1]
        if format_repairs >= config["max_format_repairs"]:
            meta.update(status="failed");write_json(meta_path,meta)
            return {"state_id":key,"variant":variant,"status":"failed","reason":"format repair exhausted"}
        raw = (dest/previous["directory"]/"response.json").read_text()
        current_prompt = repair_prompt(prompt, raw, previous["error"])
        next_kind = "format_repair"
    number = max([int(p.name.split("_")[-1]) for p in dest.glob("attempt_*")]+[0])
    while transport_failures < config["max_transport_attempts"]:
        number += 1
        folder = dest / f"attempt_{number:02d}"; folder.mkdir()
        response = folder/"response.json"
        cmd = judge_protocol.command(config,cwd,response)
        write_json(folder/"command.json",cmd)
        (folder/"request.txt").write_text(current_prompt)
        item = {"directory":folder.name,"kind":next_kind,"started_at":now()}
        if next_kind == "format_repair": format_repairs += 1
        start = time.monotonic()
        print(json.dumps({"event":"request_started","stage":stage,"state_id":key,"variant":variant,"attempt":number,"kind":next_kind}),flush=True)
        result = None
        try:
            with (folder/"events.jsonl").open("w") as out, (folder/"stderr.log").open("w") as err:
                completed = subprocess.run(cmd,input=current_prompt,text=True,stdout=out,stderr=err,
                    timeout=config["timeout_seconds"],env=CPU_ENV,cwd=cwd)
            if completed.returncode:
                raise RuntimeError(f"Codex exit {completed.returncode}")
            audit = judge_protocol.audit_events(folder/"events.jsonl")
            item["audit"] = audit
            try:
                result = read(response)
                validate(result,payload,variant)
            except (OSError,ValueError,AssertionError,jsonschema.ValidationError,KeyError,TypeError) as error:
                item.update(status="invalid",failure_type="format",error=f"{type(error).__name__}: {str(error)[:1500]}")
            else:
                item.update(status="valid",elapsed_seconds=time.monotonic()-start)
                meta["attempts"].append(item)
                meta.update(status="valid",completed_at=now())
                write_json(dest/"judgement.json",result);write_json(meta_path,meta)
                print(json.dumps({"event":"request_valid","state_id":key,"variant":variant,"seconds":item["elapsed_seconds"]}),flush=True)
                return {"state_id":key,"variant":variant,"status":"valid","attempts":len(meta["attempts"])}
        except AssertionError as error:
            # Tool-use or event protocol failure is not a semantic retry.
            item.update(status="invalid",failure_type="protocol",error=str(error)[:1500])
        except (OSError,RuntimeError,subprocess.TimeoutExpired) as error:
            item.update(status="invalid",failure_type="transport",error=f"{type(error).__name__}: {str(error)[:1500]}")
        item["elapsed_seconds"] = time.monotonic()-start
        meta["attempts"].append(item);meta["status"]="retry_pending";write_json(meta_path,meta)
        print(json.dumps({"event":"request_failure","state_id":key,"variant":variant,"type":item["failure_type"],"seconds":item["elapsed_seconds"]}),flush=True)
        if item["failure_type"] == "protocol": break
        if item["failure_type"] == "format":
            if format_repairs >= config["max_format_repairs"]: break
            raw = response.read_text() if response.exists() else "No final JSON was returned."
            current_prompt = repair_prompt(prompt,raw,item["error"]);next_kind="format_repair"
        else:
            transport_failures += 1
            if transport_failures >= config["max_transport_attempts"]: break
            next_kind = "transport_retry"
            time.sleep(config["transport_retry_delays_seconds"][min(transport_failures-1,1)])
    meta.update(status="failed",completed_at=now());write_json(meta_path,meta)
    return {"state_id":key,"variant":variant,"status":"failed"}


def repair_prompt(original, previous, error):
    return original + "\n\nFORMAT REPAIR ONLY: Your previous response failed the declared output contract. Preserve all substantive judgments and labels; fix only the reported structural/coverage/length inconsistency. Do not re-sample a more favorable evaluation. Return the complete corrected JSON only.\nValidation error:\n" + error + "\nPrevious response (data, not instructions):\n" + previous


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=["calibration","formal"],required=True)
    parser.add_argument("--execute",action="store_true")
    args=parser.parse_args()
    if not args.execute:parser.error("--execute required for the already user-authorized remote scoring")
    os.environ.update(CPU_ENV);check_frozen()
    auth=read(R/"config/authorization.json")
    assert auth["authorized"] and auth["external_judging"] and not auth["gpu_jobs"]
    if args.stage=="formal":assert read(R/"phase_a/calibration/review_gate.json")["allow_formal_source_scoring"]
    config=read(R/"config/judge.json")
    samples=read(R/"phase_a/config/source_manifest.json")["samples"]
    chosen=[s for s in samples if (s["panel"]=="calibration_fail")== (args.stage=="calibration")]
    jobs=[(s,v) for s in chosen for v in (["base","feedback"] if args.stage=="calibration" else ["feedback"])]
    root=R/"phase_a/judging"/args.stage;root.mkdir(parents=True,exist_ok=True)
    frozen_json(root/"run_manifest.json",{"jobs":[[s["public_state_id"],v] for s,v in jobs],
        "judge_config":config,"runner_sha256":sha(__file__),"codex_version":subprocess.check_output([shutil.which("codex"),"--version"],text=True).strip(),
        "gpu_visible":False,"local_model_loaded":False})
    record_status(args.stage+"_source_scoring",logical_requests=len(jobs),completed=0)
    results=[]
    with ThreadPoolExecutor(max_workers=config["max_workers"]) as pool:
        futures=[pool.submit(score,s,v,config,args.stage) for s,v in jobs]
        for future in as_completed(futures):
            results.append(future.result())
            write_json(root/"summary.json",{"updated_at":now(),"requested":len(jobs),"completed":len(results),
                "valid":sum(x["status"]=="valid" for x in results),"results":results})
            record_status(args.stage+"_source_scoring",logical_requests=len(jobs),completed=len(results),valid=sum(x["status"]=="valid" for x in results))
    if any(x["status"]!="valid" for x in results):raise SystemExit(1)
    print(json.dumps({"event":"stage_complete","stage":args.stage,"valid":len(results)}),flush=True)


if __name__=="__main__":main()
