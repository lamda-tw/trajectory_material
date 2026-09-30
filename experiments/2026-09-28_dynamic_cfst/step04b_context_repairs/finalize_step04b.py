#!/usr/bin/env python3
"""Freeze Step 4B outcomes, post-hoc labels, exclusions, and costs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path

STAGE = Path(__file__).resolve().parent
PARENT = STAGE.parent
STEP04A = PARENT / "step04a_expanded_repairs"

FINAL_LABELS = {
    "b0a8eae_1": (
        "状态错误", ["上下文控制", "信息选择"],
        "教师只取得锻炼笔记侧的必要状态，避免把全部公开歌单同时写入历史；学生随后读取计划、计算时长并播放正确歌单。",
    ),
    "2a163ab_1": (
        "状态错误", ["上下文控制", "日期过滤", "联系人关系"],
        "教师把完整社交动态在环境内按今天和室友邮箱过滤成目标交易；学生只对该目标集合点赞。",
    ),
    "2a163ab_2": (
        "状态错误", ["上下文控制", "日期过滤", "联系人关系"],
        "教师把完整社交动态在环境内按昨天和兄弟姐妹邮箱过滤成目标交易ID；学生据此完成点赞。",
    ),
    "2a163ab_3": (
        "状态错误", ["上下文控制", "认证状态"],
        "教师把登录独立成紧凑动作并保留访问令牌，避免原动作立即打印完整动态；学生后来取得并过滤同事交易后完成点赞。",
    ),
}

EXCLUSIONS = {
    "76f2c72_2": "官方1/2；教师修正年份-月份正则，但打印账单全文和PDF二进制，学生随后转向Gmail，续跑请求达到47,685 tokens，仍未给出总额。",
    "22cc237_2": "官方1/4；教师识别金额被误当邮箱，却只输出两个接口文档；教师观察加入后学生首个续跑输入30,340 tokens，预留3,000后再次超过32,000，没有创建任何收款请求。",
    "22cc237_1": "官方1/4；教师仍输出完整dinner笔记列表，学生继续查询和解析后请求达到44,705 tokens；没有创建任何收款请求。",
    "c901732_2": "官方0/6；教师只补查凭证接口，学生登录后再次打印全部歌单，下一请求达到62,464 tokens，未播放歌曲。",
}


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def result_paths() -> dict[str, Path]:
    return {read_json(path)["task_id"]: path for path in (STAGE / "attempts").glob("rank*/result.json")}


def freeze_new_success(task_id: str, path: Path) -> dict:
    result = read_json(path)
    if not result["official_successful_repair"]:
        raise RuntimeError(f"{task_id}: cannot freeze an official failure")
    label, secondary, rationale = FINAL_LABELS[task_id]
    teacher = result["teacher"]["response"]
    return {
        "sample_id": f"step04b:{task_id}:action{result['replace_action_index_1based']}",
        "origin": "step04b",
        "task_id": task_id,
        "family_id": result["family_id"],
        "replace_action_index_1based": result["replace_action_index_1based"],
        "final_primary_label": label,
        "secondary_labels": secondary,
        "label_rationale_zh": rationale,
        "teacher_code_sha256": digest(teacher["code"]),
        "teacher_reasoning_sha256": digest(teacher["reasoning"]),
        "prefix_replay_success": result["prefix_replay_success"],
        "official_success": True,
        "official_evaluation": result["official_evaluation"],
        "teacher_boundary": {
            "ground_truth_visible": result["teacher"]["ground_truth_visible"],
            "rejected_action_visible": result["teacher"]["rejected_action_visible"],
            "later_trajectory_visible": result["teacher"]["later_trajectory_visible"],
            "official_failure_condition_visible": result["teacher"]["official_failure_condition_visible"],
        },
        "result_path": str(path),
        "interaction_log": result["interaction_log"],
        "official_report": result["official_report"],
    }


def main() -> None:
    paths = result_paths()
    summary = read_json(STAGE / "summary.json")
    prefix = read_json(STAGE / "prefix_validation.json")
    if set(paths) != {row["task_id"] for row in prefix["results"]}:
        raise RuntimeError("Attempt set does not match validated candidate set")

    qualified = read_jsonl(STEP04A / "qualified_samples.jsonl")
    for task_id in summary["successful_task_ids"]:
        qualified.append(freeze_new_success(task_id, paths[task_id]))

    excluded = []
    for task_id in summary["failed_task_ids"]:
        result = read_json(paths[task_id])
        excluded.append({
            "task_id": task_id,
            "family_id": result["family_id"],
            "candidate_rank": result["candidate_rank"],
            "replace_action_index_1based": result["replace_action_index_1based"],
            "provisional_label": result["primary_label_before_execution"],
            "official_evaluation": result["official_evaluation"],
            "generation_error": result["generation_error"],
            "exclusion_reason_zh": EXCLUSIONS[task_id],
            "result_path": str(paths[task_id]),
            "official_report": result["official_report"],
        })

    counts = Counter(row["final_primary_label"] for row in qualified)
    families = defaultdict(set)
    for row in qualified:
        families[row["final_primary_label"]].add(row["family_id"])

    student_actions = student_prompt = student_completion = 0
    for path in paths.values():
        for line in (path.parent / "interactions.jsonl").read_text().splitlines():
            row = json.loads(line)
            if row["actor"] == "student":
                student_actions += 1
                student_prompt += int(row.get("prompt_tokens") or 0)
                student_completion += int(row.get("completion_tokens") or 0)

    costs = {
        "schema_version": "dynamic-cfst-step04b-costs-v1",
        "logical_candidates": 8,
        "clean_prefix_validations": len(prefix["results"]),
        "clean_prefix_actions_executed": sum(len(row["steps"]) for row in prefix["results"]),
        "prefix_environment_runs": len(prefix["results"]),
        "repair_environment_runs": len(paths),
        "total_environment_runs": len(prefix["results"]) + len(paths),
        "infrastructure_retries": 0,
        "teacher_process_invocations": summary["teacher_calls"],
        "teacher_actions_completed": summary["teacher_calls"],
        "student_continuation_actions": student_actions,
        "student_prompt_tokens": student_prompt,
        "student_completion_tokens": student_completion,
        "official_successes_step04b": summary["verified_successful_repairs"],
        "official_failures_step04b": len(paths) - summary["verified_successful_repairs"],
        "training_runs": 0,
        "check_split_teacher_answers": 0,
        "dev57_teacher_answers": 0,
        "notes": [
            "Teacher token accounting is unavailable from the Codex CLI audit response; calls and completed actions are reported instead.",
            "All eight candidates were run in the Step 2 frozen order regardless of interim success.",
            "Four model continuations ended in a fixed-window context error; these are method failures, not infrastructure retries.",
        ],
    }
    freeze = {
        "schema_version": "dynamic-cfst-step04b-freeze-v1",
        "qualified_samples": len(qualified),
        "step04a_and_earlier_imported": len(qualified) - summary["verified_successful_repairs"],
        "step04b_new": summary["verified_successful_repairs"],
        "label_counts": dict(counts),
        "unique_family_counts": {key: len(value) for key, value in families.items()},
        "target_per_label": [8, 12],
        "target_status": {label: "met" if 8 <= counts[label] <= 12 else "shortfall" for label in ["状态错误", "参数错误", "恢复错误"]},
        "remaining_to_lower_bound": {label: max(0, 8 - counts[label]) for label in ["状态错误", "参数错误", "恢复错误"]},
        "source_non_context_failures_exhausted": True,
        "source_context_failures_exhausted": True,
        "all_source_failures_exhausted": True,
        "fixed_context_queue_attempted": 8,
        "fixed_context_queue_successes": summary["verified_successful_repairs"],
        "new_parameter_successes": sum(row["origin"] == "step04b" and row["final_primary_label"] == "参数错误" for row in qualified),
        "new_recovery_successes": sum(row["origin"] == "step04b" and row["final_primary_label"] == "恢复错误" for row in qualified),
        "check_split_teacher_answers": 0,
        "dev57_teacher_answers": 0,
        "training_runs": 0,
        "training_gate_passed": False,
        "stop_reason_zh": "固定8个上下文失败已耗尽；新增4条均为状态错误，参数仍差1条、恢复仍差7条。按预设门槛停止，不进入训练。",
    }
    write_jsonl(STAGE / "qualified_samples.jsonl", qualified)
    write_jsonl(STAGE / "excluded_attempts.jsonl", excluded)
    (STAGE / "freeze_summary.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n")
    (STAGE / "costs.json").write_text(json.dumps(costs, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(freeze, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
