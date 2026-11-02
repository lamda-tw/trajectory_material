"""Summarize source scoring and prepare cached candidate prompts on CPU only."""
from common import *
import argparse, collections, io, re
from validate_v7_feedback import feedback_text


def csv_write(path, records):
    if not records:return
    buffer=io.StringIO(newline="")
    writer=csv.DictWriter(buffer,fieldnames=list(records[0]),lineterminator="\n")
    writer.writeheader();writer.writerows(records)
    Path(path).parent.mkdir(parents=True,exist_ok=True);Path(path).write_text(buffer.getvalue())


def result_for(sample,stage,variant="feedback"):
    path=R/"phase_a/judging"/stage/sample["public_state_id"]/variant/"judgement.json"
    return read(path) if path.exists() else None


def summarize_calibration(samples,tokenizer):
    records=[];disagreements=[];packets=[]
    equal=total=step_equal=step_total=0
    for s in samples:
        base=result_for(s,"calibration","base");extended=result_for(s,"calibration")
        if not base or not extended:raise ValueError("Calibration scoring is incomplete")
        b={row[0]:row for row in base["steps"]};e={row[0]:row for row in extended["steps"]}
        payload=read(R/s["input"]);steps={x["id"]:x for x in payload["steps"]}
        for step in b:
            step_total+=1;step_equal+=b[step][1]==e[step][1]
            for i,(before,after) in enumerate(zip(b[step][1],e[step][1]),1):
                total+=1;equal+=before==after
                if before!=after:
                    disagreements.append({"state_id":s["public_state_id"],"target_step":s["target_step"],
                        "step":step,"rule":f"R{i}","base":before,"feedback":after,
                        "base_reason":b[step][2],"feedback_reason":e[step][2]})
        target=s["target_step"];feedback=extended["feedback"]
        f=feedback[0] if feedback else None
        count=len(tokenizer.encode(feedback_text(f),add_special_tokens=False).ids) if f else 0
        records.append({"state_id":s["public_state_id"],"task_id":s["task_id"],"target_step":target,
            "historical_v6":s["labels"],"base_v7":b[target][1],"feedback_v7":e[target][1],
            "target_labels_identical":b[target][1]==e[target][1],"feedback_present":bool(f),
            "feedback_tokens":count,"feedback_usable":bool(f and f["usable"] and count<=256),
            "uses_later_evidence":bool(f and f["uses_later_evidence"]),
            "diagnosis":f["diagnosis"] if f else "","correction":f["correction"] if f else ""})
        evidence=set(f["evidence_steps"] if f else [])|{target}
        packets.append({"state":records[-1],"base_target":b[target],"feedback_target":e[target],
            "feedback":f,"task":payload["task"],"agent_instructions":payload["agent_instructions"],
            "referenced_steps":[steps[x] for x in sorted(evidence)],"full_input":s["input"]})
    folder=R/"phase_a/calibration"
    csv_write(folder/"target_comparison.csv",records)
    csv_write(folder/"label_disagreements.csv",disagreements)
    write_json(folder/"review_packet.json",packets)
    summary={"created_at":now(),"source_trajectories":len(samples),"scored_steps_per_variant":step_total,
        "label_cells":total,"equal_label_cells":equal,"label_cell_agreement":equal/total,
        "equal_step_label_strings":step_equal,"step_label_agreement":step_equal/step_total,
        "target_labels_identical":sum(x["target_labels_identical"] for x in records),
        "usable_target_feedback":sum(x["feedback_usable"] for x in records),
        "new_feedback_effectiveness_tested":False,
        "limitation":"One call per prompt variant; label changes conflate prompt effects and judge stochasticity; semantic review required."}
    write_json(folder/"comparison_summary.json",summary)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def render_message(arm,rules,text,original,clean_control=False):
    template=(R/"plan_snapshot/prompts/teacher_reprompt_v2.txt").read_text()
    heading="C2_feedback for clean controls ONLY" if clean_control else arm
    marker="--- "+heading+" ---\n"
    content=template.split(marker,1)[1].split("\n---",1)[0].strip()
    definitions=(R/"config/scoring_prompt_v7_en.txt").read_text()
    names={int(n):name for n,name in re.findall(r"^R([1-8]) ([^:\n]+):",definitions,re.M)}
    labels="\n".join(f"- {rule} {names[int(rule[1:])]}" for rule in rules)
    content=content.replace("{{V7_FAIL_RULE_IDS_AND_NAMES}}",labels)
    content=content.replace("{{FEEDBACK_TEXT}}",text)
    content=content.replace("{{JSON_ESCAPED_FULL_ORIGINAL_ASSISTANT_ANSWER}}",json.dumps(original,ensure_ascii=False))
    assert not any(slot in content for slot in ("{{V7_FAIL_RULE_IDS_AND_NAMES}}", "{{FEEDBACK_TEXT}}", "{{JSON_ESCAPED_FULL_ORIGINAL_ASSISTANT_ANSWER}}"))
    return content


def export_candidates(samples,tokenizer,fast_tokenizer,stage="formal"):
    records=[];ready=[];step_records=[]
    summary_source=R/"phase_a/judging"/stage/"summary.json"
    expected=len(samples)*(2 if stage=="calibration" else 1)
    if not summary_source.exists() or read(summary_source)["valid"]!=expected:
        raise ValueError("All selected source scoring must finish before candidate input export")
    repeats=1 if stage=="calibration" else 2
    output_folder=R/("phase_a/calibration" if stage=="calibration" else "phase_a/analysis")
    for s in samples:
        scored=result_for(s,stage)
        if scored is None:raise ValueError(f"Missing source result {s['public_state_id']}")
        target=s["target_step"];labels={x[0]:x for x in scored["steps"]}[target][1]
        for step,label,reason in scored["steps"]:
            step_records.append({"state_id":s["public_state_id"],"trajectory_id":s["trajectory_id"],
                "task_id":s["task_id"],"step":step,"labels_v7":label,"reason":reason,"is_selected_target":step==target})
        f=scored["feedback"][0] if scored["feedback"] else None
        text=feedback_text(f) if f and f["usable"] else ""
        tokens=len(fast_tokenizer.encode(text,add_special_tokens=False).ids)
        good=s["panel"]=="formal_good"
        issues=[]
        if good:
            if not (labels.count("F")==0 and labels.count("P")>=3 and labels.count("U")==0):issues.append("clean_control_changed_under_v7")
        else:
            if "F" not in labels:issues.append("historical_fail_not_F_under_v7")
            elif not f or not f["usable"]:issues.append("feedback_unusable")
            elif tokens>256:issues.append("feedback_over_256_tokens")
        record={"state_id":s["public_state_id"],"panel":s["panel"],"task_id":s["task_id"],
            "family":s["family"],"stratum_v6":s["stratum"],"trajectory_id":s["trajectory_id"],
            "target_step":target,"labels_v6":s["labels"],"labels_v7":labels,
            "target_labels_changed":labels!=s["labels"],"feedback_present":bool(f),
            "feedback_tokens":tokens,"uses_later_evidence":bool(f and f["uses_later_evidence"]),
            "failed_rules_v7":";".join(f["failed_rules"]) if f else "",
            "diagnosis":f["diagnosis"] if f else "","correction":f["correction"] if f else "",
            "feedback_usable_raw":bool(f and f["usable"]),"unusable_reason":f["unusable_reason"] if f else "",
            "preparation_eligible":False,"c3_available":False,"shared_output_budget":0,
            "c0_tokens":0,"c1_tokens":0,"c2_tokens":0,"c3_tokens":0,"skip_reasons":""}
        if not issues:
            original=read(R/s["policy_input"])
            messages=original["messages"]
            arms=["C0_original","C2_feedback"] if good else ["C0_original","C1_fail_labels","C2_feedback","C3_feedback_and_original_answer"]
            prompts={};lengths={}
            for arm in arms:
                augmented=list(messages)
                if arm!="C0_original":
                    augmented=messages+[{"role":"user","content":render_message(arm,f["failed_rules"] if f else [],text,original["original_answer"],good)}]
                ids=tokenizer.apply_chat_template(augmented,tools=None,tokenize=True,add_generation_prompt=True,enable_thinking=False)
                if arm=="C0_original":assert ids==original["prompt_ids"]
                prompts[arm]={"messages":augmented,"prompt_ids":ids};lengths[arm]=len(ids)
            common=[a for a in arms if a!="C3_feedback_and_original_answer"]
            budget=min(3000,32000-max(lengths[a] for a in common))
            record["shared_output_budget"]=budget
            for arm,n in lengths.items():record[arm[:2].lower()+"_tokens"]=n
            if budget<128:issues.append("shared_context_budget_under_128")
            else:
                c3="C3_feedback_and_original_answer"
                c3_available=c3 in lengths and lengths[c3]+budget<=32000
                record["c3_available"]=c3_available
                if c3 in prompts and not c3_available:del prompts[c3]
                package={"state":s,"source_labels_v7":labels,"feedback":f,"feedback_text":text,
                    "prompts":prompts,"max_new_tokens":budget,"samples_per_arm":repeats,
                    "sampling_seeds":{arm:[int(digest(["20261021:rubric_sdpo_A:v1",s["public_state_id"],arm,i])[:8],16)%(2**31) for i in range(repeats)] for arm in prompts},
                    "state_replay_validated":False,"execution_gate":"waiting_for_explicit_user_start",
                    "all_gpu_operations_disabled":True}
                path=R/"phase_a/ready"/(s["public_state_id"]+".json")
                frozen_json(path,package)
                ready.append({"state_id":s["public_state_id"],"path":str(path.relative_to(R)),
                    "sha256":sha(path),"arms":list(prompts),"candidate_ceiling":repeats*len(prompts)})
                record["preparation_eligible"]=True
        record["skip_reasons"]=";".join(issues)
        records.append(record)
    csv_write(output_folder/"target_feedback_inventory.csv",records)
    csv_write(output_folder/"all_source_step_scores_v7.csv",step_records)
    manifest_name="calibration_manifest.json" if stage=="calibration" else "manifest.json"
    write_json(R/"phase_a/ready"/manifest_name,{"states":ready,"requires_user_start":True,"state_replay_pending":True})
    fail=[x for x in records if x["panel"]!="formal_good"]
    good=[x for x in records if x["panel"]=="formal_good"]
    summary={"created_at":now(),"stage":stage,"source_trajectories":len(samples),"all_source_steps_scored":len(step_records),
        "fail_targets":len(fail),"fail_targets_still_F_v7":sum("F" in x["labels_v7"] for x in fail),
        "fail_targets_feedback_ready":sum(x["preparation_eligible"] for x in fail),
        "good_targets_ready":sum(x["preparation_eligible"] for x in good),
        "ready_fail_by_historical_stratum":dict(collections.Counter(x["stratum_v6"] for x in fail if x["preparation_eligible"])),
        "later_evidence_ready_fail":sum(x["uses_later_evidence"] for x in fail if x["preparation_eligible"]),
        "skip_reasons":dict(collections.Counter(reason for x in records for reason in x["skip_reasons"].split(";") if reason)),
        "c3_available_fail":sum(x["c3_available"] for x in fail),
        "ready_candidate_ceiling":sum(x["candidate_ceiling"] for x in ready),
        "gpu_used":False,"model_weights_loaded":False,"candidate_actions_generated":0,
        "state_replay_validated":False,"training_updates":0,"next_gate":"explicit user start; then replay/calibration checks before formal Qwen generation"}
    write_json(output_folder/"preparation_summary.json",summary)
    if stage=="formal":
        record_status("cpu_and_source_feedback_preparation_complete_waiting_for_user_start",**{k:v for k,v in summary.items() if k not in ("created_at","stage")})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage",choices=["calibration","formal"],required=True)
    parser.add_argument("--prepare-candidates",action="store_true",help="Also prepare CPU-only candidate inputs for calibration")
    args=parser.parse_args();os.environ.update(CPU_ENV);check_frozen()
    from tokenizers import Tokenizer
    fast=Tokenizer.from_file(str(Path(read(R/"config/source_evaluation.json")["paths"]["base_model"])/"tokenizer.json"))
    samples=read(R/"phase_a/config/source_manifest.json")["samples"]
    chosen=[s for s in samples if (s["panel"]=="calibration_fail")== (args.stage=="calibration")]
    if args.stage=="calibration":summarize_calibration(chosen,fast)
    if args.stage=="formal" or args.prepare_candidates:
        from transformers import AutoTokenizer
        tok=AutoTokenizer.from_pretrained(read(R/"config/source_evaluation.json")["paths"]["base_model"],local_files_only=True)
        export_candidates(chosen,tok,fast,args.stage)


if __name__=="__main__":main()
