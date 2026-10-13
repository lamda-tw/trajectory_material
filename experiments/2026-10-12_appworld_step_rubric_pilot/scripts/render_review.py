"""Render readable side-by-side results from completed, validated judge outputs."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / "manifest.json").read_text())
    summary = json.loads((ROOT / "review/comparison.json").read_text())
    destination = ROOT / "review/trajectories"
    destination.mkdir(exist_ok=True)
    index = ["# 逐轨迹对照入口", "", "每条链接展示完整步骤的两版标签、judge 原始短证据与输入链接。官方结果仅供本页复核，不在 judge 输入中。", "",
             "标签位置固定为 R1 执行、R2 证据、R3 状态、R4 决策、R5 效果、R6 恢复、R7 交付、R8 协议。P/F/U/N 不计算总分。", "",
             "| 轨迹 | 官方结果 | 步数 | 选样理由 |", "| --- | --- | ---: | --- |"]
    for sample in manifest["samples"]:
        payload = json.loads((ROOT / sample["input"]).read_text())
        results = {version: json.loads((ROOT / "runs" / run / sample["id"] / "judgement.json").read_text())
                   for version, run in [("v1", "v1_audit_recovered"), ("v2", "v2_audit")]}
        success = "成功" if sample["official_success_for_researcher_only"] else "失败"
        page = destination / (sample["id"] + ".md")
        index.append(f"| [{sample['id']}]({page}) | {success} | {sample['steps']} | {sample['selection_reason']} |")
        lines = [f"# {sample['id']}", "", f"官方结果：{success}（只供复核，未提供给 judge）。完整实际步骤：{sample['steps']}。", "",
                 payload["task"], "", f"[完整准备输入]({ROOT / sample['input']}) · [原始轨迹]({sample['source']})", "",
                 "八字符依次为 R1 执行 / R2 证据 / R3 状态 / R4 决策 / R5 效果 / R6 恢复 / R7 交付 / R8 协议。", "",
                 "| Step | v1 | v2 | 改变维度 |", "| ---: | --- | --- | --- |"]
        for (step, old), (_, new) in zip(results["v1"]["steps"], results["v2"]["steps"]):
            changed = ", ".join(f"R{i+1}: {a}→{b}" for i, (a, b) in enumerate(zip(old, new)) if a != b) or "—"
            lines.append(f"| {step} | `{old}` | `{new}` | {changed} |")
        for version, result in results.items():
            lines += ["", f"## {version} 原始 judge 证据", ""]
            lines += [f"- Step {step} / {rubrics} / 引用 {','.join(map(str, evidence))}：{reason}" for step, rubrics, evidence, reason in result["notes"]]
        lines += ["", "## 本会话的开发检查点", "", "以下是开发复核，不是独立人工金标准，也未提供给 judge。", ""]
        a = summary["versions"]["v1"]["development_checks"]
        b = summary["versions"]["v2"]["development_checks"]
        for left, right in zip(a, b):
            if left["trajectory"] == sample["id"]:
                lines.append(f"- Step {left['step']} / {left['rubric']}：预期 {'/'.join(left['expected'])}，v1={left['observed']}，v2={right['observed']}。{left['rationale']}")
        page.write_text("\n".join(lines) + "\n")
    (ROOT / "review/TRAJECTORIES.md").write_text("\n".join(index) + "\n")
    print("Rendered six trajectory comparison pages.")


if __name__ == "__main__":
    main()
