#!/usr/bin/env python3
"""Freeze the post-execution Step 4A sample set, exclusions, and costs."""

from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


STAGE = Path(__file__).resolve().parent
PARENT = STAGE.parent
STEP03 = PARENT / "step03_repair_validation"


FINAL_LABELS = {
    # Imported Step 3 successes.
    "ccb4494_2": ("状态错误", ["队列位置"], "教师重新读取当前播放队列，修正了基于错误状态变量的选择。"),
    "302c169_2": ("状态错误", ["操作语义"], "教师依据现有闹钟状态更新起床时间并停用其余闹钟。"),
    "60d0b5b_1": ("参数错误", ["对象选择"], "教师从已见请求中精确选择Robert、金额和接收方参数。"),
    # Step 4A official successes, audited from the actual teacher action.
    "34d9492_2": ("参数错误", ["时间范围", "目标路径"], "文件年份和月份已可见；教师修正分类条件并构造正确移动参数。"),
    "22cc237_3": ("参数错误", ["API选择", "操作语义"], "真实邮箱和金额已可见；教师改查付款请求接口，学生随后构造正确调用。"),
    "76f2c72_1": ("状态错误", ["时间过滤", "文件格式"], "教师补齐当前年份过滤、去重并读取可用账单内容。"),
    "d0b1f43_1": ("状态错误", ["联系人关系"], "教师先取得真实关系枚举，学生据此重建室友集合与聚合。"),
    "b0a8eae_3": ("状态错误", ["笔记选择"], "教师拒绝首条搜索结果，读取候选笔记全文后再选择当天计划。"),
    "692c77d_3": ("状态错误", ["动作准备"], "教师确认缺失评分需要新增接口并补齐该接口状态，学生随后完成评分。"),
    "7d7fbf6_2": ("参数错误", ["目录路径", "删除语义"], "目录列表已可见；教师修正直接子目录、归档路径和原子删除参数。"),
    "d0b1f43_3": ("参数错误", ["交易方向", "对象角色"], "交易与室友已可见；教师修正sender/receiver方向和聚合对象。"),
    "6104387_3": ("恢复错误", ["CSV格式"], "原动作已因字典无法join而报错；教师在错误反馈后生成合法CSV并写入。"),
    "7d7fbf6_3": ("参数错误", ["目录索引", "归档路径"], "目录已可见；教师在首次写入前修正目录索引和目标文件名。"),
    "7d7fbf6_1": ("状态错误", ["路径过滤"], "教师修正绝对路径的直接子目录判断，避免把全部目标过滤掉。"),
    "34d9492_3": ("参数错误", ["时间范围", "目标路径"], "元数据已可见；教师补齐写操作文档，学生随后用年份和月份构造正确目标。"),
    "d0b1f43_2": ("状态错误", ["联系人关系"], "教师指出入账总额未限定同事并引导取得电话联系人状态。"),
}


EXCLUSIONS = {
    "692c77d_1": "官方5/7；教师找对目标与review_id，但学生多次使用错误键和接口参数，3条已有评分未更新。",
    "29caf6f_2": "官方7/8；教师找到了Tarantino请求，但学生发送导演行而非对应电影标题。",
    "692c77d_2": "官方5/7；学生更新了已有评分，却没有为5首缺失评分的目标歌曲新增评分。",
    "29caf6f_3": "官方6/8；教师只读取整篇笔记，学生未按对方要求筛选，既漏目标片名又混入非目标片名。",
    "29caf6f_1": "官方7/8；教师直接发送全部14个标题，包含请求导演之外的电影。",
    "6104387_2": "官方7/10；教师代码调用环境禁用的csv.writer而执行失败，后续CSV缺少完整歌曲映射。",
    "b0a8eae_2": "官方0/5；教师动作成功，但学生打印完整歌单状态后请求达到45,403 tokens，超过固定32,000上下文并未播放。",
}


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text())


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")


def result_paths(stage: Path) -> dict[str, Path]:
    return {
        read_json(path)["task_id"]: path
        for path in (stage / "attempts").glob("rank*/result.json")
    }


def freeze_success(task_id: str, result_path: Path, origin: str) -> dict:
    result = read_json(result_path)
    if not result["official_successful_repair"]:
        raise RuntimeError(f"{task_id}: cannot freeze an official failure")
    label, secondary, rationale = FINAL_LABELS[task_id]
    teacher = result["teacher"]["response"]
    return {
        "sample_id": f"{origin}:{task_id}:action{result['replace_action_index_1based']}",
        "origin": origin,
        "task_id": task_id,
        "family_id": result["family_id"],
        "replace_action_index_1based": result["replace_action_index_1based"],
        "final_primary_label": label,
        "secondary_labels": secondary,
        "label_rationale_zh": rationale,
        "teacher_code_sha256": sha256(teacher["code"]),
        "teacher_reasoning_sha256": sha256(teacher["reasoning"]),
        "prefix_replay_success": result["prefix_replay_success"],
        "official_success": True,
        "official_evaluation": result["official_evaluation"],
        "teacher_boundary": {
            "ground_truth_visible": result["teacher"]["ground_truth_visible"],
            "rejected_action_visible": result["teacher"]["rejected_action_visible"],
            "later_trajectory_visible": result["teacher"]["later_trajectory_visible"],
            "official_failure_condition_visible": result["teacher"]["official_failure_condition_visible"],
        },
        "result_path": str(result_path),
        "interaction_log": result["interaction_log"],
        "official_report": result["official_report"],
    }


def main() -> None:
    step03_paths = result_paths(STEP03)
    step04_paths = result_paths(STAGE)
    qualified = []
    for task_id in ["ccb4494_2", "302c169_2", "60d0b5b_1"]:
        qualified.append(freeze_success(task_id, step03_paths[task_id], "step03"))
    for candidate in sorted(
        (read_json(path) for path in step04_paths.values()),
        key=lambda row: row["candidate_rank"],
    ):
        if candidate["official_successful_repair"]:
            qualified.append(freeze_success(candidate["task_id"], step04_paths[candidate["task_id"]], "step04a"))

    excluded = []
    for task_id, reason in EXCLUSIONS.items():
        result = read_json(step04_paths[task_id])
        excluded.append(
            {
                "task_id": task_id,
                "family_id": result["family_id"],
                "candidate_rank": result["candidate_rank"],
                "replace_action_index_1based": result["replace_action_index_1based"],
                "official_evaluation": result["official_evaluation"],
                "generation_error": result["generation_error"],
                "exclusion_reason_zh": reason,
                "result_path": str(step04_paths[task_id]),
                "official_report": result["official_report"],
            }
        )

    counts = Counter(row["final_primary_label"] for row in qualified)
    families = defaultdict(set)
    for row in qualified:
        families[row["final_primary_label"]].add(row["family_id"])
    prefix = read_json(STAGE / "prefix_validation.json")
    summary = read_json(STAGE / "summary.json")
    student_actions = student_prompt = student_completion = 0
    for path in step04_paths.values():
        interaction_path = path.parent / "interactions.jsonl"
        if not interaction_path.exists():
            continue
        for line in interaction_path.read_text().splitlines():
            row = json.loads(line)
            if row["actor"] == "student":
                student_actions += 1
                student_prompt += int(row.get("prompt_tokens") or 0)
                student_completion += int(row.get("completion_tokens") or 0)
    costs = {
        "schema_version": "dynamic-cfst-step04a-costs-v1",
        "logical_candidates": 20,
        "clean_prefix_validations": len(prefix["results"]),
        "clean_prefix_actions_executed": sum(len(row["steps"]) for row in prefix["results"]),
        "prefix_environment_runs_including_normalization_retry": 31,
        "prefix_actions_including_normalization_retry": 348,
        "repair_environment_runs": 21,
        "total_environment_runs_including_retries": 52,
        "infrastructure_retries": 1,
        "teacher_process_invocations": 21,
        "teacher_actions_completed": summary["teacher_calls"],
        "student_continuation_actions": student_actions,
        "student_prompt_tokens": student_prompt,
        "student_completion_tokens": student_completion,
        "official_successes_step04a": summary["verified_successful_repairs"],
        "official_failures_step04a": 20 - summary["verified_successful_repairs"],
        "training_runs": 0,
        "check_split_teacher_answers": 0,
        "notes": [
            "One first teacher process for 6104387_2 exited before returning; it is preserved under infrastructure_failures and was retried once.",
            "The first prefix pass stopped after 11 environments because one saved observation contained an asynchronous throughput log line; business JSON matched. The pass is preserved and all 20 prefixes were then revalidated with only that log line normalized.",
            "Teacher token accounting is unavailable from the Codex CLI audit response; calls and completed actions are reported instead.",
        ],
    }
    freeze = {
        "schema_version": "dynamic-cfst-step04a-freeze-v1",
        "qualified_samples": len(qualified),
        "step03_imported": 3,
        "step04a_new": len(qualified) - 3,
        "label_counts": dict(counts),
        "unique_family_counts": {key: len(value) for key, value in families.items()},
        "target_per_label": [8, 12],
        "target_status": {
            label: "met" if 8 <= counts[label] <= 12 else "shortfall"
            for label in ["状态错误", "参数错误", "恢复错误"]
        },
        "source_non_context_failures_exhausted": True,
        "check_split_teacher_answers": 0,
        "training_runs": 0,
    }
    write_jsonl(STAGE / "qualified_samples.jsonl", qualified)
    write_jsonl(STAGE / "excluded_attempts.jsonl", excluded)
    (STAGE / "freeze_summary.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n")
    (STAGE / "costs.json").write_text(json.dumps(costs, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(freeze, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
