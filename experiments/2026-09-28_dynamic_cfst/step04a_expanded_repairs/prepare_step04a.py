#!/usr/bin/env python3
"""Freeze the Step 4A source-only review order and repair decision points."""

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
STEP03 = PARENT / "step03_repair_validation"


# Step 3 backups first, then the untouched source-side review_queue order.  The
# first three Step 3 successes are imported evidence and are not run again.
DECISIONS = [
    ("34d9492_2", 13, "状态错误", "step03_backup", "分类条件把旧年四月照片也当作今年四月；在首次移动前重算年份与月份。"),
    ("22cc237_3", 18, "状态错误", "step03_backup", "已经确定真实欠款人与金额，但将收款请求误成主动转账；在首次资金写入前改正操作语义。"),
    ("692c77d_1", 19, "恢复错误", "review_queue_3", "连续键错误后仍索引缺失评分；在错误链中止处恢复未评分/已有评分的区分。"),
    ("29caf6f_2", 5, "恢复错误", "review_queue_4", "只读最新短信导致找不到请求；在首次异常后改为读取真实请求并继续解析。"),
    ("76f2c72_1", 9, "状态错误", "review_queue_5", "账单未按当前年份过滤且混有PDF；在汇总前重新取得年份与可读内容。"),
    ("d0b1f43_1", 13, "状态错误", "review_queue_7", "把父母误作室友并按错误转账方向聚合；在金额计算前重建联系人集合。"),
    ("b0a8eae_3", 6, "状态错误", "review_queue_8", "把搜索结果第一条语录当作锻炼计划；在读取错误笔记前核验标题和内容。"),
    ("692c77d_3", 12, "状态错误", "review_queue_11", "已经得到目标歌曲和现有评分，却转去查删除接口并直接完成；在写入前把读取状态转成更新/新增动作。"),
    ("7d7fbf6_2", 11, "参数错误", "review_queue_12", "目录列表含父目录，原循环会生成错误归档并提前删除；在首次文件写入前只选直接子目录并构造目标路径。"),
    ("d0b1f43_3", 16, "状态错误", "review_queue_13", "转账的发送方/接收方方向被反转；在提交答案前按当前用户视角重新聚合。"),
    ("6104387_3", 11, "恢复错误", "review_queue_14", "CSV行是字典，连接时报错；在该异常之后生成带表头的合法CSV并继续。"),
    ("7d7fbf6_3", 10, "参数错误", "review_queue_15", "用字符串查找结果当目录索引且后续目标路径含完整路径；在首次压缩前改正目录和文件名参数。"),
    ("692c77d_2", 15, "恢复错误", "review_queue_16", "目标集合和评分记录处理连续报错；在尚未发生有效业务写入时重新计算未喜欢歌曲并更新/新增评分。"),
    ("7d7fbf6_1", 9, "状态错误", "review_queue_17", "用斜杠数量筛选绝对路径，导致所有度假目录被丢弃；在首次压缩前按父目录关系筛选。"),
    ("29caf6f_3", 19, "参数错误", "review_queue_18", "直接发送整篇笔记，混入导演和类型行；在短信写入前只抽取电影标题并用逗号连接。"),
    ("34d9492_3", 12, "状态错误", "review_queue_19", "只按月份分类，把旧年四月照片归到首尔；在创建目录和移动前同时检查年份。"),
    ("29caf6f_1", 16, "参数错误", "review_queue_20", "标题列表包含标题、导演和类型元数据；在短信写入前只保留电影标题。"),
    ("6104387_2", 14, "恢复错误", "review_queue_21", "首次写文件把元组当映射而报错；在异常后生成表头和正确CSV行。"),
    ("b0a8eae_2", 13, "状态错误", "review_queue_22", "只读取歌曲搜索第一页，使大部分歌单时长为零；在选歌单前完整取得歌曲时长。"),
    ("d0b1f43_2", 8, "状态错误", "review_queue_23", "把所有入账当作同事转账，没有先取得同事联系人；在答案提交前补齐联系人状态并交叉过滤。"),
]


def sha256_json(value: object) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def main() -> None:
    sys.path.insert(0, str(STEP02))
    from inspect_saved_trajectories import load_task

    queue = {row["task_id"]: row for row in csv.DictReader((STEP02 / "review_queue.csv").open())}
    source_ids = set((STEP02 / "source_task_ids.txt").read_text().split())
    check_ids = set((STEP02 / "check_task_ids.txt").read_text().split())
    old_candidates = {row["task_id"]: row for row in read_jsonl(STEP02 / "repair_candidates.jsonl")}
    official = json.loads(
        (
            STEP01
            / "experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/evaluations/train.json"
        ).read_text()
    )["individual"]

    candidates = []
    reviews = []
    for rank, (task_id, replace, label, origin, diagnosis) in enumerate(DECISIONS, 1):
        if task_id not in source_ids or task_id in check_ids:
            raise RuntimeError(f"{task_id}: source/check boundary violation")
        q = queue[task_id]
        if q["context_error"] != "False":
            raise RuntimeError(f"{task_id}: context-limited task is not eligible")
        path, calls, steps = load_task(task_id)
        if not 1 <= replace <= len(calls):
            raise RuntimeError(f"{task_id}: invalid replacement index {replace}")
        messages = calls[replace - 1]["input"]["messages"]
        prompt = calls[0]["input"]["messages"][-1]["content"].split("Task:", 1)[-1].strip()
        prior = old_candidates.get(task_id, {})
        row = {
            "candidate_rank": rank,
            "task_id": task_id,
            "family_id": task_id.rsplit("_", 1)[0],
            "difficulty": int(q["difficulty"]),
            "primary_label_before_execution": label,
            "selection": origin,
            "replace_action_index_1based": replace,
            "prefix_action_count": replace - 1,
            "original_trajectory_actions": len(steps),
            "original_prompt_tokens": calls[replace - 1].get("input_tokens"),
            "input_messages_sha256": sha256_json(messages),
            "trajectory_path": str(path.parent.parent),
            "source_review_order": int(q["review_order"]),
            "review_metadata_is_not_teacher_input": True,
        }
        if prior and prior["input_messages_sha256"] != row["input_messages_sha256"]:
            raise RuntimeError(f"{task_id}: Step 3 backup digest changed")
        candidates.append(row)
        reviews.append(
            {
                **row,
                "task_instruction": prompt,
                "official_failure_conditions_for_reviewer_only": [
                    item["requirement"] for item in official[task_id]["failures"]
                ],
                "diagnosis_zh": diagnosis,
                "teacher_boundary": "仅原始轨迹中替换动作之前的可见消息；不含本审查、原错误动作、后续、评分条件或ground truth。",
            }
        )

    with (STAGE / "repair_candidates.jsonl").open("w") as stream:
        for row in candidates:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    with (STAGE / "review_annotations.jsonl").open("w") as stream:
        for row in reviews:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    (STAGE / "attempt_order.txt").write_text("\n".join(row["task_id"] for row in candidates) + "\n")
    print(json.dumps({"candidates": len(candidates), "source_only": True, "check_teacher_answers": 0}, ensure_ascii=False))


if __name__ == "__main__":
    main()
