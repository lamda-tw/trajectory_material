"""Render saved v4 judgements for review without changing any labels."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text())


def main():
    lines = ["# v4 逐步评分复核", "",
             "以下为模型原始标签与短依据，仅整理排版。官方成败仅供事后复核，未发送给 judge。", "",
             "P=通过，F=违反，U=证据不足，N=不适用；八维没有权重，不合成总分。", "",
             "R1 执行契约；R2 证据与覆盖；R3 状态与数据保真；R4 决策与计算；R5 操作与实际效果；R6 反馈与恢复；R7 结束与交付；R8 授权与交互协议。", ""]
    for run_name, manifest_name, title in [
        ("v4_regression", "manifest_v4_regression.json", "八条回归样本"),
        ("v4_fresh", "manifest_v4_fresh.json", "七条新任务（含最长输入）"),
        ("v4_repeat", "manifest_v4_repeat.json", "相同输入独立重复调用")]:
        if not (ROOT / "runs" / run_name / "summary.json").exists():
            continue
        lines += [f"## {title}", ""]
        for sample in read(ROOT / manifest_name)["samples"]:
            folder = ROOT / "runs" / run_name / sample["id"]
            if not (folder / "judgement.json").exists():
                continue
            result = read(folder / "judgement.json")
            payload = read(folder / "input.json")
            outcome = "成功" if sample["official_success_for_researcher_only"] else "失败"
            lines += [f"### {sample['id']}（官方结果：{outcome}）", "",
                      payload["task"].split("Task:")[-1].strip(), "",
                      f"[完整输入]({folder / 'input.json'}) · [原始判断]({folder / 'judgement.json'})", "",
                      "| Step | R1 | R2 | R3 | R4 | R5 | R6 | R7 | R8 | 模型简短依据 |",
                      "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
            for step, labels, reason in result["steps"]:
                safe_reason = reason.replace("|", "\\|").replace("\n", " ")
                lines.append("| " + " | ".join([str(step), *labels, safe_reason]) + " |")
            lines.append("")
    (ROOT / "review/V4_TRAJECTORIES.md").write_text("\n".join(lines)+"\n")


if __name__ == "__main__":
    main()
