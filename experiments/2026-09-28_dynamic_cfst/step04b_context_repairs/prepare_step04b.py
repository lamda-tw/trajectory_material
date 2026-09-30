#!/usr/bin/env python3
"""Freeze the eight source-side context-failure reviews and Step 4B repair points."""

from __future__ import annotations

import csv
import hashlib
import json
import sys
from pathlib import Path

STAGE = Path(__file__).resolve().parent
PARENT = STAGE.parent
STEP01 = PARENT / "step01_train90_student_rollouts"
STEP02 = PARENT / "step02_error_analysis"
MAX_CONTEXT = 32000
MAX_COMPLETION = 3000

# Order is exactly the context-failure order frozen in Step 2.  Labels are
# hypotheses for review, not training labels; successful attempts are relabelled
# from the actual teacher action and environment result after execution.
DECISIONS = [
    {
        "task_id": "76f2c72_2", "replace": 11, "label": "恢复错误",
        "diagnosis": "第10步用缺少月份部分的正则筛选当前年份账单，得到意外空列表；第11步扩大搜索范围却重复同一错误正则，仍返回空列表。",
        "evidence": "动作10输出[]；动作11再次使用 current_year + r'\\.\\w+'，而真实文件名包含 YYYY-MM，输出仍为[]。",
        "direction": "利用已经读入的账单内容或改正年份-月份文件名筛选，直接计算当前年份网络账单总额，停止跨应用漫游。",
    },
    {
        "task_id": "b0a8eae_1", "replace": 5, "label": "状态错误",
        "diagnosis": "首次业务查询同时翻完所有含workout的笔记和所有公开歌单，并把完整对象全部打印，单步输出把下一请求推到66,948 tokens。",
        "evidence": "动作5输入9,146 tokens，输出包含大量无关Habit Tracking笔记和歌单；紧接着的第6次模型请求被32,000窗口拒绝。",
        "direction": "只保留与当天锻炼计划和候选歌单有关的少量字段，读取匹配笔记正文并计算所需时长，避免打印全集。",
    },
    {
        "task_id": "2a163ab_1", "replace": 9, "label": "状态错误",
        "diagnosis": "登录与室友关系已经恢复成功，但第9步翻完并打印整个Venmo社交动态，没有在环境内按当天和室友邮箱过滤。",
        "evidence": "动作9输入8,959 tokens；完整social_feed输出使下一请求达到197,952 tokens。此前第5步401已在第7步成功恢复。",
        "direction": "在同一代码单元中按当前日期和室友邮箱筛选，保留目标transaction_id并执行或准备点赞，不回传完整动态。",
    },
    {
        "task_id": "2a163ab_2", "replace": 17, "label": "状态错误",
        "diagnosis": "日期解析异常已经在第8步自行恢复；第17步仍翻完并打印整个Venmo动态，没有按昨天和兄弟姐妹邮箱过滤。",
        "evidence": "动作17输入10,539 tokens，完整列表使下一请求达到266,081 tokens；第7步日期异常并非未恢复错误。",
        "direction": "在环境内按昨天日期和兄弟姐妹邮箱过滤，只输出或处理目标交易ID。",
    },
    {
        "task_id": "22cc237_2", "replace": 19, "label": "恢复错误",
        "diagnosis": "模型已看到unpaid_friends的值是金额而不是邮箱，也已连续收到user_email类型错误，第19步仍逐项重复完全相同的无效付款请求。",
        "evidence": "动作18明确打印Adrian->36.0等错误映射；动作17的8次请求全部422；动作19再次把这些浮点数传给user_email。",
        "direction": "从已经取得的联系人中重建姓名到邮箱映射，排除已付款者，再用正确邮箱、金额和固定描述创建收款请求。",
    },
    {
        "task_id": "22cc237_1", "replace": 5, "label": "状态错误",
        "diagnosis": "首次业务查询把所有含dinner的笔记和全部收款记录完整打印；此后又重复读取同一批笔记，历史在第11次请求因预留3,000输出tokens而超限。",
        "evidence": "动作5输入7,330 tokens，下一输入立即增至23,735；动作7再次打印全集后增至28,399，最终请求29,514+3,000超过32,000。",
        "direction": "在环境内筛选昨天的工作晚餐笔记和相关付款，只返回精确笔记/付款摘要，避免两次完整列表输出。",
    },
    {
        "task_id": "c901732_2", "replace": 3, "label": "状态错误",
        "diagnosis": "歌单搜索接口返回宽泛结果，第3步翻完所有页面并打印数百个歌单，没有即时限定标题和目标所有者。",
        "evidence": "动作3输入7,867 tokens；输出不仅有同名歌单，也含大量其他Vibes歌单，使下一请求达到62,083 tokens。",
        "direction": "只保留精确标题候选及歌曲ID，结合可见任务信息确定目标歌单，再查播放次数并播放最高者。",
    },
    {
        "task_id": "2a163ab_3", "replace": 9, "label": "状态错误",
        "diagnosis": "联系人401已通过登录恢复；第9步翻完并打印整个Venmo动态，没有在环境内按昨天/今天和同事邮箱过滤。",
        "evidence": "动作9输入9,554 tokens，完整动态使下一请求达到263,599 tokens；先前401并非仍未解决的恢复失败。",
        "direction": "在环境内按两天日期范围和同事邮箱过滤，只输出或处理目标交易ID并点赞。",
    },
]


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def main() -> None:
    sys.path.insert(0, str(STEP02))
    from inspect_saved_trajectories import load_task

    queue_rows = list(csv.DictReader((STEP02 / "review_queue.csv").open()))
    queue = {row["task_id"]: row for row in queue_rows}
    frozen_context_order = [
        row["task_id"] for row in queue_rows
        if row["context_error"] == "True"
    ]
    expected_order = [row["task_id"] for row in DECISIONS]
    if frozen_context_order != expected_order:
        raise RuntimeError(f"Frozen Step 2 context order changed: {frozen_context_order}")

    source_ids = set((STEP02 / "source_task_ids.txt").read_text().split())
    check_ids = set((STEP02 / "check_task_ids.txt").read_text().split())
    official = json.loads((STEP01 / "experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/evaluations/train.json").read_text())["individual"]

    candidates, reviews = [], []
    for rank, decision in enumerate(DECISIONS, 1):
        task_id = decision["task_id"]
        replace = decision["replace"]
        if task_id not in source_ids or task_id in check_ids:
            raise RuntimeError(f"{task_id}: source/check boundary violation")
        q = queue[task_id]
        if q["context_error"] != "True":
            raise RuntimeError(f"{task_id}: expected a frozen context-limit failure")
        path, calls, steps = load_task(task_id)
        if not 1 <= replace <= len(steps):
            raise RuntimeError(f"{task_id}: replacement must be an executed pre-rejection action")
        messages = calls[replace - 1]["input"]["messages"]
        usage = (calls[replace - 1].get("output") or {}).get("usage") or {}
        prompt_tokens = int(usage["prompt_tokens"])
        total_reserved = prompt_tokens + MAX_COMPLETION
        if total_reserved > MAX_CONTEXT:
            raise RuntimeError(f"{task_id}: candidate violates fixed context budget: {total_reserved}")
        rejected_call = calls[len(steps)]
        rejection = str((rejected_call.get("output") or {}).get("error", ""))
        if "maximum context length" not in rejection and "max_completion_tokens" not in rejection:
            raise RuntimeError(f"{task_id}: final call is not a context rejection")
        task_instruction = calls[0]["input"]["messages"][-1]["content"].split("Task:", 1)[-1].strip()
        row = {
            "candidate_rank": rank,
            "task_id": task_id,
            "family_id": task_id.rsplit("_", 1)[0],
            "difficulty": int(q["difficulty"]),
            "primary_label_before_execution": decision["label"],
            "selection": f"step02_context_queue_{rank}",
            "replace_action_index_1based": replace,
            "prefix_action_count": replace - 1,
            "original_trajectory_actions": len(steps),
            "first_rejected_call_index_1based": len(steps) + 1,
            "original_prompt_tokens": prompt_tokens,
            "reserved_completion_tokens": MAX_COMPLETION,
            "prompt_plus_reserved_tokens": total_reserved,
            "input_within_fixed_32000_protocol": total_reserved <= MAX_CONTEXT,
            "input_messages_sha256": sha256_json(messages),
            "trajectory_path": str(path.parent.parent),
            "source_review_order": int(q["review_order"]),
            "review_metadata_is_not_teacher_input": True,
        }
        candidates.append(row)
        reviews.append({
            **row,
            "task_instruction": task_instruction,
            "official_failure_conditions_for_reviewer_only": [item["requirement"] for item in official[task_id]["failures"]],
            "pre_rejection_diagnosis_zh": decision["diagnosis"],
            "log_evidence_zh": decision["evidence"],
            "repair_direction_zh": decision["direction"],
            "original_candidate_code": steps[replace - 1]["code"],
            "original_candidate_observation_excerpt": steps[replace - 1]["observation"][:2000],
            "teacher_boundary": "仅原始轨迹中替换动作之前的可见消息；不含本审查、原动作、后续、上下文拒绝、评分条件或ground truth。",
        })

    for filename, rows in [("repair_candidates.jsonl", candidates), ("review_annotations.jsonl", reviews)]:
        with (STAGE / filename).open("w") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    (STAGE / "attempt_order.txt").write_text("\n".join(expected_order) + "\n")

    lines = [
        "# CFST 第4B步：上下文拒绝前的错误审查\n",
        "这8题严格来自第2步冻结的来源60题，顺序未改变。候选输入均满足 `prompt tokens + 3000 <= 32000`。暂定标签只描述执行前证据，最终只按成功修复时教师实际动作重核。\n",
        "| 顺序 | 任务 | 替换动作 | 窗口占用 | 暂定标签 | 审查结论 |",
        "| --- | --- | ---: | ---: | --- | --- |",
    ]
    for row, review in zip(candidates, reviews):
        lines.append(f"| {row['candidate_rank']} | {row['task_id']} | {row['replace_action_index_1based']} | {row['original_prompt_tokens']}+3000={row['prompt_plus_reserved_tokens']} | {row['primary_label_before_execution']} | {review['pre_rejection_diagnosis_zh']} |")
    lines.append("\n## 逐题证据\n")
    for review in reviews:
        failures = "；".join(" ".join(x.split()) for x in review["official_failure_conditions_for_reviewer_only"])
        lines.extend([
            f"### {review['candidate_rank']}. {review['task_id']}：替换第{review['replace_action_index_1based']}步",
            f"- 任务：{review['task_instruction']}",
            f"- 官方未满足条件（仅审查可见）：{failures}",
            f"- 日志证据：{review['log_evidence_zh']}",
            f"- 暂定类别：{review['primary_label_before_execution']}。{review['pre_rejection_diagnosis_zh']}",
            f"- 修复方向：{review['repair_direction_zh']}",
            f"- 固定窗口：原输入{review['original_prompt_tokens']} tokens，预留输出{review['reserved_completion_tokens']}，合计{review['prompt_plus_reserved_tokens']}/32000，通过。",
            "- 验证状态：待干净前缀重放、教师单步替换、原学生续跑与官方评分。\n",
        ])
    (STAGE / "failure_review.md").write_text("\n".join(lines) + "\n")
    print(json.dumps({"candidates": len(candidates), "source_only": True, "context_failures": True, "check_teacher_answers": 0, "provisional_labels": {"状态错误": 6, "参数错误": 0, "恢复错误": 2}}, ensure_ascii=False))


if __name__ == "__main__":
    main()
