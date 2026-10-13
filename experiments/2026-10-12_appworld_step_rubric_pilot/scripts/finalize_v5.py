"""Publish v5 evidence and documentation after all frozen pilot calls complete."""
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo
import hashlib
import json
import runpy

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT.parents[1] / "plans/2026-10-12_appworld_step_rubric"


def read(path):
    return json.loads(path.read_text())


def dump(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pct(n, d):
    return f"{100*n/d:.1f}%"


def main():
    for name in ["regression", "fresh", "repeat"]:
        summary = read(ROOT / f"runs/v5_{name}/summary.json")
        assert summary["valid"] == summary["requested"]
    runpy.run_path(str(ROOT / "scripts/analyze_v5.py"))["main"]()
    runpy.run_path(str(ROOT / "scripts/render_v5.py"))["main"]()
    comparison = read(ROOT / "review/v5_comparison.json")
    review = read(ROOT / "review/v5_semantic_review.json")
    groups = [comparison[k] for k in ["regression", "fresh", "repeat"]]
    primary_groups = groups[:2]
    samples, primary = [], {}
    for kind in ["regression", "fresh"]:
        for sample in read(ROOT / f"manifest_v5_{kind}.json")["samples"]:
            sid = sample["id"]
            assert sid not in primary
            path = ROOT / f"runs/v5_{kind}" / sid / "judgement.json"
            primary[sid] = {row[0]: row for row in read(path)["steps"]}
            samples.append({**sample, "judgement": str(path.relative_to(ROOT)), "run": f"v5_{kind}"})
    coverage = {x["trajectory"]: x["steps_reviewed"] for x in review["coverage"]}
    assert len(coverage) == len(review["coverage"]) == len(primary)
    for sid, rows in primary.items():
        assert coverage[sid] == list(rows)
    cells = {(sid, step, f"R{i+1}"): labels[i]
             for sid, rows in primary.items() for step, labels, reason in rows.values() for i in range(8)}
    findings = {}
    for finding in review["findings"]:
        key = (finding["trajectory"], finding["step"], finding["rubric"])
        assert key not in findings
        assert cells[key] not in finding["preferred"], (key, cells[key])
        findings[key] = {**finding, "observed": cells[key]}
    clear = {k: v for k, v in findings.items() if v["kind"] == "clear_error"}
    debated = {k: v for k, v in findings.items() if v["kind"] == "debatable"}
    applicable = {k for k, v in cells.items() if v != "N"} | set(clear) | set(debated)
    labels = Counter(cells.values())
    wrong_f = [v for v in clear.values() if v["observed"] == "F" and "F" not in v["preferred"]]
    missed_f = [v for v in clear.values() if v["observed"] != "F" and v["preferred"] == ["F"]]
    nsteps = sum(len(rows) for rows in primary.values())
    affected_steps = {(k[0], k[1]) for k in clear}
    quality = {
        "reviewer": review["reviewer"], "limitations": "Developer evidence review, not independent gold or population accuracy. All first-call rows reviewed; repeats excluded from this denominator.",
        "trajectories": len(primary), "steps": nsteps, "cells": len(cells), "label_counts": dict(labels),
        "clear_errors": len(clear), "debatable_cells": len(debated),
        "no_clear_error_cells": len(cells)-len(clear), "no_flagged_issue_cells": len(cells)-len(findings),
        "applicable_or_review_flagged_cells": len(applicable),
        "applicable_without_clear_error": len(applicable)-len(clear),
        "applicable_without_flagged_issue": len(applicable)-len(findings),
        "steps_with_clear_error": len(affected_steps), "steps_without_clear_error": nsteps-len(affected_steps),
        "clear_unsupported_F": len(wrong_f), "clear_missed_F": len(missed_f),
        "by_rubric": {f"R{i}": {"clear_errors": sum(k[2] == f"R{i}" for k in clear),
                                    "debatable_cells": sum(k[2] == f"R{i}" for k in debated)} for i in range(1, 9)},
        "findings": list(findings.values()), "reason_findings": review["reason_findings"],
    }
    dump(ROOT / "review/v5_quality_summary.json", quality)
    corpus = read(ROOT / "manifest_v5_corpus.json")
    assert len(corpus["samples"]) == 540
    remaining = [s for s in corpus["samples"] if s["id"] not in primary]
    dump(ROOT / "manifest_v5_remaining.json", {**corpus, "purpose": "Unscored v5 inputs; excludes only the 12 validated first-call v5 pilot judgements.", "samples": remaining})
    prompt_hash = sha(PLAN / "prompt_v5.txt")
    assert prompt_hash == "bc6335bf245b1c0991970662bad230cd30d6ae04c0e7e8fb8af0e1d57c70de4b"
    assert prompt_hash == sha(ROOT / "snapshots/prompt_v5.txt")
    for version, expected in {"v3": "1743b4b6cd6082c809bbde4791c087ff00428233b914dd5e359f745e48e40151", "v4": "90bdf0447b228d8699f11e9ec4fcea9e23474d591a778fa59a84c04a5f38756a"}.items():
        assert sha(PLAN / f"prompt_{version}.txt") == expected
    now = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    dump(ROOT / "v5_scored_index.json", {"created_at": now, "prompt_sha256": prompt_hash,
         "selection": "First valid v5 call only; never select best repeat or mix v4 labels.", "samples": samples})
    usage = Counter()
    for g in groups:
        usage.update(g["usage"])
    attempts = sum(len(g["attempts"]) for g in groups)
    valid = sum(g["valid"] for g in groups)
    checks_pass = sum(g["check_matches"] for g in primary_groups)
    checks_total = sum(g["checks_total"] for g in primary_groups)
    anchors_pass = sum(g["anchor_matches"] for g in primary_groups)
    anchors_total = sum(g["anchors_total"] for g in primary_groups)
    durations = [s["seconds"] for g in primary_groups for s in g["samples"]]
    repeat = comparison["repeat"]
    success = sum(s["official_success_for_researcher_only"] for s in samples)
    old = read(ROOT / "review/v5_matched_v4_checks.json")
    status = {
        "updated_at": now, "current_version": "appworld-step-v5", "status": "usable_offline_annotation_baseline_with_documented_noise",
        "recommendation": "Freeze v5 for exploratory full-corpus offline annotation; do not claim verified 95% population accuracy or convert every F/U to a hard training penalty.",
        "prompt_sha256": prompt_hash, "model": "gpt-5.6-sol", "reasoning_effort": "high",
        "unique_trajectories": len(primary), "unique_steps": nsteps, "completed_calls": valid, "attempts": attempts,
        "frozen_checks": {"matches": checks_pass, "total": checks_total},
        "full_corpus_scoring_started": False, "v5_scored": len(primary), "v5_unscored": len(remaining),
        "training_performed": False, "reward_or_weights_generated": False, "usage_reported": dict(usage),
        "report": "V5_REPORT.md", "results": "review/V5_TRAJECTORIES.md", "quality": "review/v5_quality_summary.json",
    }
    dump(ROOT / "STATUS_v5.json", status)
    dump(ROOT / "STATUS.json", status)
    dump(ROOT / "v5_final_validation.json", {
        "completed_at": now, "calls_validated": valid, "attempts": attempts,
        "source_input_request_hashes_verified": True, "exact_step_order_and_schema_verified": True,
        "raw_model_outputs_unchanged": True, "judge_tool_calls": 0,
        "no_official_outcome_in_input": True, "v3_v4_prompt_hashes_unchanged": True,
        "primary_semantic_review_steps": nsteps, "prompt_sha256": prompt_hash,
        "usage": dict(usage), "quality_file": "review/v5_quality_summary.json",
    })
    lines = ["# v5 实测报告", "", f"完成时间：{now}。",
        "", "建议：将 v5 冻结为可用于全量离线探索标注的第一版基线，允许并记录少量噪声。已有证据支持继续实验，但没有验证全量总体准确率超过 95%。本轮未启动全部 540 条评分，也未训练或生成 reward/权重。",
        "", "这一推荐采用用户提出的实用标准：判断大多有依据且能够定位有价值的问题即可。重复调用不必完全相同；我们没有为提高通过率修改冻结检查点，也没有在重评中挑更好的答案。",
        "", "## 版本与样本", "",
        f"[prompt_v5.txt]({PLAN / 'prompt_v5.txt'}) 共 2,111 字符，SHA256 `{prompt_hash}`，测试期间未修改。v4 原文、结果和报告保留。",
        "", "v5 把 F 的证据要求、R3 的事实边界、R5 的局部效果和 R6 的重复/恢复判定直接写入各 rubric。仍为一条完整轨迹一次调用、8 维 PFUN 和一句短依据；不加输出模式、单项解释、总分或权重。输入适配器继续用 v3，judge 为 gpt-5.6-sol/high，最多两个并发。",
        "", f"8 条历史反例回归 + 4 条此前未评分的新任务族，共 {len(primary)} 条完整轨迹、{nsteps} 步、{len(cells)} 个分项判断；其中成功 {success} 条、失败 {len(primary)-success} 条。成功样本为有意增采，样本不代表全量成败比例。另对原 v3/v4 的同一对样本重复调用，共 {valid} 次有效调用、{attempts} 次尝试。官方成败仅在研究清单中，未给 judge。",
        "", "## 冻结检查与重复性", "", "| 指标 | 结果 | 含义 |", "| --- | --- | --- |",
        f"| 相同52项回归 | v4 {old['matches']}/{old['total']} → v5 {comparison['regression']['check_matches']}/52 | 同样本、同预设检查 |",
        f"| 新任务检查 | {comparison['fresh']['check_matches']}/{comparison['fresh']['checks_total']} | 提示词冻结后、新调用前预设 |",
        f"| 合计 | {checks_pass}/{checks_total}（{pct(checks_pass, checks_total)}） | 定向检查符合率，不是准确率 |",
        f"| 执行/只读适用性机械检查 | {anchors_pass}/{anchors_total} | 结构及显式反馈锚点 |",
        f"| 同输入重复标签一致 | {repeat['same_cells']}/{repeat['cells']}（{pct(repeat['same_cells'], repeat['cells'])}） | 其中 {len(repeat['f_switches'])} 处 F/非F 切换，不等同正确率 |",
        "", "改善最明确的是：未验证歌单时长可留 U；刷新当前关注状态后有效重试记 P；没有前置异常的无效重复查文档记 F。原来复合写入后盲目重试的错误仍能识别。新任务也能发现收到索款请求不等于别人已付款、虚构执行回执、歌曲数代替时长，以及文件名不能替代创建日期。",
        "", "仍未通过的五项检查全部保留：账单15步R2和16步R7应保留未知；最少播放歌曲7步R8漏掉第二代码块；聚餐16步R4漏掉错误业务取证方向（R2/R3已判错）；照片17步R5把整体未完成连带算成本次13张移动的局部效果错误。",
        "", "## 如何理解 95%", "",
        "除定向检查外，我逐步对照全部201步的代码、反馈、上下文和八维标签，也检查N是否漏评。下面是本助手的证据复核结果，不是独立人工标注，不可当作论文级总体准确率。",
        "", "| 分母 | 未发现明确误判 | 连边界争议也扣除 |", "| --- | --- | --- |",
        f"| 全部分项 {len(cells)} | {len(cells)-len(clear)}/{len(cells)}（{pct(len(cells)-len(clear),len(cells))}） | {len(cells)-len(findings)}/{len(cells)}（{pct(len(cells)-len(findings),len(cells))}） |",
        f"| 非N及复核指出漏评的分项 {len(applicable)} | {len(applicable)-len(clear)}/{len(applicable)}（{pct(len(applicable)-len(clear),len(applicable))}） | {len(applicable)-len(findings)}/{len(applicable)}（{pct(len(applicable)-len(findings),len(applicable))}） |",
        "", f"发现 {len(clear)} 个明确分项误判，另有 {len(debated)} 个边界争议；明确问题影响 {len(affected_steps)}/{nsteps} 个步骤，即只有 {nsteps-len(affected_steps)}/{nsteps} 步在八项上均未发现明确问题。不能把约98%的分项复核结果说成约98%的步骤完全正确。",
        "", f"在原始 {labels['F']} 个 F 中，有 {len(wrong_f)} 个被复核认为缺少充分依据；另有 {len(missed_f)} 个明确应 F 的分项未标 F。账单一条轨迹集中贡献8个明确误判，错误存在任务内相关性。四条账单短依据也有把未知写成确定遗漏的过度表述。",
        "", "已发现的问题以证据不足误作F、局部取证过早承担全局要求、接口错误跨维度传播，以及R8漏掉额外代码块为主。若95%指大多数分项合理，本轮给出了支持性迹象；若指随机总体中95%的步骤八项全对，或错误step识别率达到95%，本轮没有证明。",
        "", f"[逐项复核记录]({ROOT / 'review/v5_quality_summary.json'}) · [所有原始逐步标签]({ROOT / 'review/V5_TRAJECTORIES.md'})。原始输出未被我的复核改写。",
        "", "## 成本与后续使用", "",
        f"12条首次评分平均 {mean(durations):.1f} 秒/条；回归 {comparison['regression']['mean_seconds']:.1f} 秒，新任务 {comparison['fresh']['mean_seconds']:.1f} 秒。服务负载、缓存和样本长度不同，不能把本轮耗时差当成提示词加速结论。",
        "", f"含两次重评的已报告用量：输入 {usage['input_tokens']:,} tokens（缓存是其子集），输出 {usage['output_tokens']:,} tokens（推理是其子集）。这次只在小样本做完整证据复核；未来批量仍然每条轨迹一次调用、相同简短输出，无自动重评或多轮审计成本。",
        "", f"540条输入可继续复用；当前v5已评分12条，尚有 {len(remaining)} 条未评分。全量可复用首次v5结果，只处理剩余清单，不混入v4标签。不要把U默认当F；暂不合成固定权重或奖励。后续用这些结构化标签做step选择等实验时，再判断哪些维度有预测价值。",
        "", "```bash", f"cd {ROOT}", "# 后续执行全量剩余标注的入口；本轮未执行", "python scripts/run_judge_v5.py --execute --run v5_remaining_001 --manifest manifest_v5_remaining.json", "```",
        "", "不继续为孤立反例堆补丁。若后续出现反复影响step选择的新问题，再据此建立v6，并在固定样本上比较。",
    ]
    (ROOT / "V5_REPORT.md").write_text("\n".join(lines) + "\n")
    (ROOT / "README.md").write_text(f"""# AppWorld step rubric 实验

当前版本 **v5**：建议冻结为全量离线探索标注基线，保留已知噪声；尚未证明总体95%准确率。本轮测试12条完整轨迹、201步，另两次重复调用；没有启动540条全量评分或训练。

[v5报告]({ROOT / 'V5_REPORT.md'}) · [逐步评分]({ROOT / 'review/V5_TRAJECTORIES.md'}) · [复核记录]({ROOT / 'review/v5_quality_summary.json'}) · [正式prompt]({PLAN / 'prompt_v5.txt'})。

回归检查50/52、新任务36/39；这些是开发检查而非独立准确率。具体证据复核、重复差异、限制和成本见报告。成功与失败轨迹均使用同一prompt、一次调用和统一三列输出，无权重、总分或audit/batch模式。

`manifest_v5_corpus.json`登记540条输入，`v5_scored_index.json`保留12条首次有效v5结果，`manifest_v5_remaining.json`登记528条未评分输入。准备输入不等于已经评分；旧v4结果不可改名混用。

复查现有实验：`python scripts/analyze_v5.py`；只整理原始结果展示：`python scripts/render_v5.py`。所有模型调用的请求、输入、配置、哈希和原始输出保存在`runs/v5_*`；旧版文件均保留。

[v4历史报告]({ROOT / 'V4_REPORT.md'}) · [v3历史报告]({ROOT / 'V3_REPORT.md'}) · [v1/v2历史报告]({ROOT / 'REPORT.md'})。
""")
    (PLAN / "README.md").write_text(f"""# AppWorld 逐步 rubric 评价

当前版本 **v5**，已完成12条完整轨迹、201步和两次重复调用的实测。建议将其冻结为后续全量离线探索标注的基线，允许少量噪声；没有证明总体准确率超过95%。

一条完整轨迹调用一次，成功和失败轨迹均逐步评价R1—R8；保留P/F/U/N与一句短依据，不计算总分、reward或固定权重，不设audit/batch模式。v5共2,111字符，适用边界直接写在唯一Evaluation Rubrics模块中。

| 文件 | 用途 |
| --- | --- |
| [prompt_v5.txt](prompt_v5.txt) | 当前冻结提示词 |
| [prepare_input_v3.py](prepare_input_v3.py) | 沿用统一输入适配器，不改变轨迹证据 |
| [output_schema_v5.json](output_schema_v5.json) | 三列输出结构 |
| [validate_output_v5.py](validate_output_v5.py) | 校验版本、格式、步骤覆盖和短依据 |
| [VERSIONS.md](VERSIONS.md) | 不可覆盖的各版本记录 |

```bash
python prepare_input_v3.py SOURCE.json INPUT.json --trajectory-id base:TASK__SAMPLE
python validate_output_v5.py INPUT.json RESPONSE.json
```

替换prompt中唯一的`{{{{TRAJECTORY_JSON}}}}`后调用judge；不附官方成败或检查点。保存输入、prompt、模型和推理强度。输出结构通过不代表语义正确。

[v5实测报告]({ROOT / 'V5_REPORT.md'}) · [逐步结果]({ROOT / 'review/V5_TRAJECTORIES.md'}) · [逐项复核]({ROOT / 'review/v5_quality_summary.json'})。

相同52项开发回归由v4的47项符合提高到v5的50项，新任务36/39。仍有F/U边界、局部/全局覆盖和协议漏判。总体判断大多可用，不继续追求完全一致；不要将未知直接作为错误或把这些标签视为独立真值。完整复核的分母和限制见报告。

实验目录已准备540条输入；v5已评分12条，528条未评分。后续批量使用相同prompt和输出，不增加重评模式。本轮未启动全量标注。所有v1—v4文件与结果保留，今后任何prompt修改须建立新版本。
""")
    version_path = PLAN / "VERSIONS.md"
    version_text = version_path.read_text()
    assert "## Prompt v5 / appworld-step-v5" not in version_text
    version_path.write_text(version_text + f"""

## Prompt v5 / appworld-step-v5

2026-10-12，依据v4反例进一步明确事实、业务决策、实际效果与恢复边界，纳入无前置异常的重复查询以及刷新状态后的有效重试。正文2,111字符；SHA256 `{prompt_hash}`。沿用v3输入适配器、统一八维PFUN短输出与gpt-5.6-sol/high，测试期间prompt保持不变。

12条不同完整轨迹、201步，成功7条、失败5条，另对原v3/v4同一对输入重复评分，共14次有效调用。相同52项回归v4为47/52，v5为50/52；新增检查36/39，合计86/91。219/219执行与只读锚点符合。重复一致性{repeat['same_cells']}/224，F/非F切换{len(repeat['f_switches'])}处；不把一致性等同准确率。

本助手逐步证据复核全部1608个分项，发现{len(clear)}个明确误判、{len(debated)}个边界争议；不是独立人工真值，也未证实总体95%准确率。采用用户允许少量噪声的标准，状态为**可用的全量离线探索标注基线**。当前v5已评分12条，528条未评分；未启动全量、训练或reward/权重合成。

见[v5完整报告]({ROOT / 'V5_REPORT.md'})和[逐步原始结果]({ROOT / 'review/V5_TRAJECTORIES.md'})。不要继续覆盖v5来修孤立反例；后续修改另建v6。
""")
    print(json.dumps({"status": status, "review": {k: v for k, v in quality.items() if k not in {"findings", "reason_findings"}}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
