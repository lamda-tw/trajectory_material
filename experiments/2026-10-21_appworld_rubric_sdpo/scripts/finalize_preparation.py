"""Audit completed source scoring/CPU packages and write a preparation report."""
from common import *
import collections, re, statistics
import judge_protocol


def main():
    check_frozen()
    gate=read(R/"config/execution_gate.json")
    assert not any(gate[k] for k in ["gpu_allowed","qwen_generation_allowed","candidate_execution_allowed","training_allowed","automatic_gpu_resume"])
    summary=read(R/"phase_a/analysis/preparation_summary.json")
    assert summary["source_trajectories"]==130 and not summary["gpu_used"] and not summary["state_replay_validated"]
    calls=0;logical=0;retries=collections.Counter();usage=collections.Counter()
    for stage,n in [("calibration",16),("formal",130)]:
        root=R/"phase_a/judging"/stage
        scored=read(root/"summary.json")
        assert scored["requested"]==scored["completed"]==scored["valid"]==n
        logical+=n
        run_manifest=read(root/"run_manifest.json")
        assert run_manifest["runner_sha256"]==sha(R/"scripts/score_sources.py")
        assert run_manifest["judge_config"]==read(R/"config/judge.json")
        for state,variant in run_manifest["jobs"]:
            dest=root/state/variant
            assert (dest/"judgement.json").exists()
            meta=read(dest/"metadata.json");assert meta["status"]=="valid"
            identity=read(dest/"identity.json")
            assert identity==meta["identity"]
            assert identity["request_sha256"]==sha(dest/"request.txt")
            calls+=len(meta["attempts"])
            for a in meta["attempts"]:
                if a.get("failure_type"):retries[a["failure_type"]]+=1
                if a["status"]=="valid":
                    audit=judge_protocol.audit_events(dest/a["directory"]/"events.jsonl")
                    assert not audit["tool_items"]
                    for k,v in (audit.get("usage") or {}).items():
                        if isinstance(v,(int,float)):usage[k]+=v
    packages=[]
    for filename in ["calibration_manifest.json","manifest.json"]:
        ready=read(R/"phase_a/ready"/filename)
        assert ready["requires_user_start"] and ready["state_replay_pending"]
        for item in ready["states"]:
            path=R/item["path"];assert sha(path)==item["sha256"]
            package=read(path)
            assert not package["state_replay_validated"] and package["all_gpu_operations_disabled"]
            budget=package["max_new_tokens"];assert 128<=budget<=3000
            for arm,prompt in package["prompts"].items():
                assert len(prompt["prompt_ids"])+budget<=32000
                assert len(package["sampling_seeds"][arm])==package["samples_per_arm"]
            original=read(R/"phase_a/inputs/policy"/(item["state_id"]+".json"))
            assert package["prompts"]["C0_original"]["prompt_ids"]==original["prompt_ids"]
            packages.append(item)
    inventory=list(csv.DictReader((R/"phase_a/analysis/target_feedback_inventory.csv").open()))
    assert len(inventory)==130
    repair_audit=read(R/"phase_a/analysis/format_repair_audit.json")
    assert repair_audit["normalized_entire_response_identical_to_format_repair"]
    fail=[x for x in inventory if x["panel"]=="formal_fail"]
    controls=[x for x in inventory if x["panel"]=="formal_good"]
    lengths=sorted(int(x["feedback_tokens"]) for x in fail if x["feedback_present"]=="True")
    audit={"created_at":now(),"logical_source_requests":logical,"actual_codex_calls":calls,
        "failed_attempts_by_type":dict(retries),"successful_call_usage":dict(usage),
        "all_valid_call_tool_audits_passed":True,"ready_packages_checked":len(packages),
        "format_repair_preserved_substantive_response":True,
        "formal_target_label_changes":sum(x["target_labels_changed"]=="True" for x in inventory),
        "formal_fail_target_label_changes":sum(x["target_labels_changed"]=="True" for x in fail),
        "formal_control_target_label_changes":sum(x["target_labels_changed"]=="True" for x in controls),
        "feedback_token_min":min(lengths) if lengths else None,"feedback_token_max":max(lengths) if lengths else None,
        "feedback_token_median":statistics.median(lengths) if lengths else None,
        "frozen_sources_verified":True,"gpu_started":False,"model_weights_loaded":False,
        "candidate_actions_generated":0,"trajectory_replay_started":False,"training_started":False,
        "independent_human_gold_validation":False}
    write_json(R/"phase_a/analysis/final_preparation_audit.json",audit)
    files=[p for directory in ["scripts","config","runtime_code","phase_a/config"] for p in (R/directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!="cpu_preparation_manifest.json"]
    write_json(R/"phase_a/config/cpu_preparation_manifest.json",{"created_at":now(),"sha256":{str(p.relative_to(R)):sha(p) for p in sorted(files)}})
    strata="\n".join(f"| {name} | {count} |" for name,count in sorted(summary["ready_fail_by_historical_stratum"].items()))
    skips="、".join(f"{reason}: {count}" for reason,count in summary["skip_reasons"].items()) or "无"
    text=f'''# 阶段 A：来源反馈与 CPU 输入准备报告

完成时间：{audit["created_at"]}。**前置准备完成，等待用户明确开始指令。尚未生成 Qwen 候选、重放来源轨迹或训练。**

## 已完成的工作

138 条不同来源轨迹、90 道训练题完成输入准备；合计 3,429 个原始步骤。138 个原动作前 prompt 的 token 序列与历史记录逐项一致。使用本地 tokenizer，没有加载模型权重。外部输入已按既有 v3 结构整理，并使用每题本地登记与模式匹配等值脱敏；没有加入隐藏测试、官方成功标签或额外账户事实。

8 条调试来源轨迹各用原 v7 与 v7-feedback 评分一次。8 个目标步标签完全一致，全部 281 个步骤的逐维一致率 98.98%；这是版本对照的一致性，不是准确率。8 条反馈已完成助手证据复核，不是独立人工金标。详见 [调试报告](../calibration/REPORT.md)。

正式的 130 条来源轨迹全部完成 v7-feedback 评分，共 {summary["all_source_steps_scored"]} 个步骤；每条一次返回所有标签和目标步反馈。总计 {logical} 个逻辑来源请求、{calls} 次实际 Codex 调用，技术/格式失败尝试为 {dict(retries)}。全部成功调用通过工具禁用审计。

唯一一次格式修复是把误写成字符串方法调用的标签改成合法 JSON 字符串。仅规范化该处后，首份结果与修复结果全文一致，标签和反馈没有实质变化。见 [格式修复审计](format_repair_audit.json)。

## 目标样本与反馈

| 项目 | 数量 |
|---|---:|
| 原固定 FAIL 目标 | 100 |
| 新 v7 仍含 F | {summary["fail_targets_still_F_v7"]} |
| 标签、反馈与输入预算通过准备检查的 FAIL 目标 | {summary["fail_targets_feedback_ready"]} |
| 原干净对照 | 30 |
| 新 v7 及输入预算仍符合条件的干净对照 | {summary["good_targets_ready"]} |
| 可用 FAIL 中引用后来观察的反馈 | {summary["later_evidence_ready_fail"]} |
| 可容纳完整原回答 C3 的 FAIL 目标 | {summary["c3_available_fail"]} |
| 正式待生成动作上限 | {summary["ready_candidate_ceiling"]} |

正式目标的八维标签相对历史 v6 有 {audit["formal_target_label_changes"]}/130 个变化；其中 FAIL 目标 {audit["formal_fail_target_label_changes"]}/100、干净对照 {audit["formal_control_target_label_changes"]}/30。原标签保留，未换样、未强行要求 v7 判 F。反馈长度为 {audit["feedback_token_min"]}–{audit["feedback_token_max"]} Qwen tokens，中位数 {audit["feedback_token_median"]}。

准备可用的 FAIL 样本按**历史 v6 分层**如下；不是重新按 v7 分组：

| 历史层 | 可用数量 |
|---|---:|
{strata}

排除/暂不使用原因：{skips}。这些条目仍保留在清单与原始结果中。

## 可直接审阅的产物

- [目标步标签、完整反馈与输入预算](target_feedback_inventory.csv)
- [正式来源全部 step 的 v7 标签](all_source_step_scores_v7.csv)
- [准备统计](preparation_summary.json)
- [最终审计与调用统计](final_preparation_audit.json)

四组输入、固定种子及 token IDs 已保存在实验本地 `phase_a/ready/`；基线输入与旧 prompt tokens 再次核对一致。该目录含本地 agent 执行上下文，已排除版本控制。调试 8 状态另有 32 个待生成动作，不混入正式统计。

## 等待开始后的工作

用户明确开始后，先验证动作前状态恢复，再执行 8 状态的 Qwen 调试；通过后进行正式纠错候选生成与实际动作执行，最后离线用原 v7 盲评。必须使用当前分支实际观察，不能拼接旧失败分支后续。

当前“可用”只表示来源评分、反馈结构/长度和输入预算通过准备检查，不代表反馈语义已被独立证明，更不代表 Qwen 已能纠错。单步纠错效果、教师分布诊断和完整任务收益尚未测量。B/C 未启动；没有 GPU 空闲后自动运行的任务。
'''
    (R/"phase_a/analysis/PREPARATION_REPORT.md").write_text(text)
    print(json.dumps(audit,ensure_ascii=False,indent=2))


if __name__=="__main__":main()
