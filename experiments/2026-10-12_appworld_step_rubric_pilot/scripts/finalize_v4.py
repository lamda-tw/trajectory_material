"""Finalize the v4 sample study and prepare the unscored corpus manifest."""
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean
from zoneinfo import ZoneInfo
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT.parents[1] / "plans/2026-10-12_appworld_step_rubric"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+"\n")


def main():
    data = read(ROOT / "review/v4_comparison.json")
    regression, fresh, repeat = (data[k] for k in ["regression", "fresh", "repeat"])
    assert regression["valid"] == 8 and fresh["valid"] == 7 and repeat["valid"] == 3
    assert sha(PLAN / "prompt_v4.txt") == "90bdf0447b228d8699f11e9ec4fcea9e23474d591a778fa59a84c04a5f38756a"
    for key, run in [("regression", "v4_regression"), ("fresh", "v4_fresh"), ("repeat", "v4_repeat")]:
        assert (ROOT / "runs" / run / "prompt.txt").read_bytes() == (PLAN / "prompt_v4.txt").read_bytes()
    frozen = read(ROOT / "review/v4_fresh_checks.json")["frozen_at"]
    started = read(ROOT / "runs/v4_fresh/run_manifest.json")["started_at"]
    assert datetime.fromisoformat(frozen) < datetime.fromisoformat(started)
    attempts = regression["attempts"] + fresh["attempts"] + repeat["attempts"]
    completed = [a for a in attempts if a["completed"]]
    failed = [a for a in attempts if not a["completed"]]
    usage = Counter()
    for a in completed:
        usage.update(a["reported_usage"] or {})
    first_samples = regression["samples"] + fresh["samples"]
    corpus = read(ROOT / "manifest_v4_corpus.json")
    by_id = {s["id"]: s for s in corpus["samples"]}
    first_results = {}
    for run, group in [("v4_regression", regression), ("v4_fresh", fresh)]:
        for sample in group["samples"]:
            sid = sample["id"]
            folder = ROOT / "runs" / run / sid
            assert sha(folder / "input.json") == by_id[sid]["input_sha256"]
            first_results[sid] = {"judgement": str((folder / "judgement.json").relative_to(ROOT)),
                                 "input_sha256": by_id[sid]["input_sha256"], "request_sha256": sha(folder / "request.txt")}
    remaining = {k: v for k, v in corpus.items() if k != "samples"}
    remaining.update(purpose="Unscored corpus remainder; reuse the first valid v4 sample judgement for the 15 already-scored inputs, not the repeated response.",
                     samples=[s for s in corpus["samples"] if s["id"] not in first_results])
    save(ROOT / "manifest_v4_remaining.json", remaining)
    save(ROOT / "v4_scored_index.json", {"prompt_sha256": sha(PLAN / "prompt_v4.txt"), "model": "gpt-5.6-sol", "reasoning_effort": "high", "first_judgements": first_results})
    primary_ids = {s["id"] for s in read(ROOT / "manifest_v3.json")["samples"]}
    primary_mean = mean(s["seconds"] for s in regression["samples"] if s["id"] in primary_ids)
    common_repeat_ids = {"302c169_2__02", "cf6abd2_2__01"}
    shared_changes = [c for c in repeat["changed_cells"] if c["trajectory"] in common_repeat_ids]
    shared_f_switches = [c for c in shared_changes if "F" in [c["first"], c["repeat"]]]
    stable = repeat["same_cells"] / repeat["cells"]
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    anchors = regression["anchors"] + fresh["anchors"]
    anchor_summary = {rubric: {"matches": sum(c["matches"] for c in anchors if c["rubric"] == rubric),
                              "total": sum(c["rubric"] == rubric for c in anchors)} for rubric in ["R1", "R5"]}
    status = {"completed_at": timestamp, "status": "v4_sample_study_complete_with_known_label_noise",
              "current_candidate": "appworld-step-v4", "recommendation": "Operationally ready for full-corpus input and calls, but keep v4 as a candidate: semantic uncertainty and repeated-label instability remain unresolved.",
              "unique_trajectories": 15, "unique_tasks": 13, "task_families": 12, "unique_steps": 279,
              "completed_calls": len(completed), "attempts": len(attempts), "failed_calls_without_completed_usage": len(failed),
              "regression_checks": [regression["check_matches"], regression["checks_total"]],
              "fresh_checks": [fresh["check_matches"], fresh["checks_total"]],
              "mechanical_anchors": anchor_summary,
              "repeat_same_cells": repeat["same_cells"], "repeat_cells": repeat["cells"],
              "repeat_f_switches": len(repeat["f_switches"]),
              "shared_v3_repeat_same_cells": 224-len(shared_changes), "shared_v3_repeat_cells": 224,
              "corpus_prepared": 540, "corpus_remaining_unscored": len(remaining["samples"]),
              "largest_input_characters": max(s["input_characters"] for s in first_samples),
              "prompt_unchanged_during_testing": True, "independent_accuracy_measured": False,
              "full_corpus_scoring_launched": False, "training_performed": False,
              "reward_or_weights_generated": False, "report": "V4_REPORT.md"}
    save(ROOT / "STATUS_v4_high.json", status)
    save(ROOT / "v4_high_final_validation.json", {**status, "all_hash_and_exact_request_checks_passed": True,
         "all_completed_calls_passed_tool_audit": True, "all_raw_judgements_preserved": True,
         "fresh_checks_frozen_before_fresh_judging": True, "total_reported_usage": dict(usage),
         "failed_attempts": failed, "usage_note": "Input includes cached input; output includes reasoning. Failed incomplete calls have unknown usage, not zero."})
    coverage_rows = "\n".join(f"| {s['id']} | {'成功' if s['official_success_for_researcher_only'] else '失败'} | {s['steps']} | {s['input_characters']:,} | {s['seconds']:.1f} |" for s in first_samples)
    mismatch_rows = "\n".join(f"| {c['trajectory']} | {c['step']} | {c['rubric']} | {'/'.join(c['expected'])} | {c['observed']} |" for c in regression["checks"]+fresh["checks"] if not c["matches"])
    report = f'''# prompt_v4 优化与抽样报告

完成：{timestamp}（北京时间）。

**v4 的输入与调用流程可以覆盖全量，但评分质量仍应保留为候选状态，尚不建议作为 540 条轨迹的正式固定标签来源。** 它修复了明确的适用性和重试错误，也识别出新任务中的业务问题；但 F/U 边界仍有偏差，重复评分的一致性反而下降。不能把运行成功、检查点符合率和语义稳定性混成一个“可用”结论。

本轮只完成抽样与重复评分，没有启动剩余 525 条的模型调用，没有生成 reward、权重或训练数据筛选结果。

## v4 改了什么

在原有八条 rubric 内合并修订，保持统一输出 `[step_id, 八维标签, 一句依据]`，没有增加输出模式或独立补丁。

- 明确先判适用性，再判 P/F/U，限制错误跨维度扩散。
- R3/R4 区分数据事实、业务决策与纯执行、认证准备。
- R5 明确只读、计算、认证准备和 `complete_task` 为 N；区分允许某种操作与实际产生的效果。
- R6 明确部分写入后未核对就重试的错误优先于局部参数修复。
- R2/R7 和短依据强调必要证据不足；实测表明这部分仍未完全达到预期。

v4 正文 2,152 字符（v3 为 1,786），SHA256 `{sha(PLAN / 'prompt_v4.txt')}`。测试开始后未改动，未创建 v5。输入仍使用 v3 适配器，模型仍为 `gpt-5.6-sol / high`，总并发最多两个请求。

## 抽样覆盖与结果

主实验共 **15 条不同完整轨迹、13 道题、12 类任务、279 个步骤**，成功 6 条、失败 9 条；另对三条相同输入重复评分，共 18 次有效 high 调用。后续 medium 配置诊断单独记录，不混入这些统计。

| 组别 | 轨迹 / 步骤 | 预设语义检查点 | 执行及适用性机械检查 |
| --- | ---: | ---: | ---: |
| 旧案例回归 | 8 / 99 | {regression['check_matches']}/{regression['checks_total']} | {regression['anchor_matches']}/{regression['anchors_total']} |
| 新任务与最长输入 | 7 / 180 | {fresh['check_matches']}/{fresh['checks_total']} | {fresh['anchor_matches']}/{fresh['anchors_total']} |

新任务涵盖跨应用运动播放、批量关注、退款、短信/语音删除、备份后销户、50 步预算耗尽循环和最长社交动态输入。v4 在读取这些新任务、制定检查点之前已冻结；43 个新检查点在调用 judge 前保存。

语义检查由本助手按可见证据制定，旧案例还参与了提示词开发，均不是独立人工准确率。机械检查只验证执行反馈明确失败时 R1=F，以及保守识别的只读/认证/提交代码 R5=N，不能替代业务正确性审查。其分项为 R1 {anchor_summary['R1']['matches']}/{anchor_summary['R1']['total']}、R5 {anchor_summary['R5']['matches']}/{anchor_summary['R5']['total']}。

所有有效调用都通过 JSON、轨迹 ID、完整步骤顺序和短依据长度验收；没有给 judge 官方成败或检查点，没有使用外部工具来执行或重放轨迹。

## v3 的关键问题是否修复

- **提交误判为业务修改：已修复。** 电费案例第 16 步 R5 从 F 改为 N；本轮可机械确认的只读/提交步骤均符合该边界。
- **部分执行后直接重试：已修复该反例。** 压缩案例第 13 步 R6 从 P 改为 F，识别参数修补不能抵消未经核对的重试。
- **凭 overwrite 参数断言实际覆盖：已修复该反例。** 压缩第 16 步依据只指出可确认的目录错误。
- **未读 PDF 被视为确定漏算：未完全修复。** 同一账单案例仍有两个 F/U 不一致，已保留为残余问题。

新任务中，v4 能区分删除一条消息的局部正确操作与声称全部删除的错误交付；能指出把最早请求误作最近请求、把删除请求当退款、把分钟等同歌曲数，以及把未执行备份/销户写成已完成。

## 尚存的五个检查点不一致

| 轨迹 | Step | 维度 | 预设 | v4 |
| --- | ---: | --- | --- | --- |
{mismatch_rows}

这些主要涉及两类边界：

1. **F/U 仍可能偏严。** 未读账单文件，以及没有验证时长的播放效果，被判为确定错误。相关决策可能确有问题，但未知效果不应自动等同已确认失败。
2. **R6 对重复与恢复仍有差异。** 已刷新关注状态后成功的相同代码仍被判错；无前置异常的重复查文档有一处被判 N。相同代码是否合理取决于当前状态与已有反馈，不能只比较代码是否重复。

原始标签和预设检查点没有被改写；逐例证据见 [残余问题](review/v4_residual_findings.json)。这些问题意味着后续不能简单把所有 F 都当成确定负监督，也不能仅凭“最终成功”把局部 F 改成 P。

## 重复评分

三条相同输入共 {repeat['cells']} 个标签，**{repeat['same_cells']} 个一致（{stable:.1%}）**，有 {len(repeat['f_switches'])} 处 F 与非 F 切换。重复响应全部保留，不选择较好的一次覆盖原结果。

其中与 v3 重复实验相同的两条输入共有 224 个标签：v3 为 216/224 一致；v4 为 **{224-len(shared_changes)}/224**，F/非 F 切换 {len(shared_f_switches)} 处。本轮没有获得稳定性改善，不能据此推荐直接固定全量标签。样本数量很小，不能据此估计全量稳定性。完整差异见 [比较 JSON](review/v4_comparison.json)。

## 全量输入与运行成本

已经在本地准备并核验 **90 题、540 条、11,254 步**，源文件哈希全部匹配。输入字符数中位数为 32,115，P95 为 100,039，最大为 527,852。

最长的 `2a163ab_1__03` 完整输入已实测通过，8 步无遗漏，CLI 报告输入 203,129 tokens；未截断观察、未改用摘要、未分割评价协议。50 步轨迹也完整通过，因此这轮同时覆盖了输入体积与步骤数两个边界；不代表所有任务语义都已验证。

在原六条相同样本上，v3 平均约 78.2 秒，v4 本轮约 **{primary_mean:.1f} 秒**；七条新任务平均 **{fresh['mean_seconds']:.1f} 秒**。本轮未证明 v4 更快，服务负载、缓存与推理量都影响耗时。v4 优化目标主要是边界清晰与可用性，而非已验证的吞吐提升。

共记录 {len(attempts)} 次尝试、{len(completed)} 次完成；{len(failed)} 次未完成请求的事件与错误原样保留。首次回归中有模型容量繁忙错误，重试沿用相同模型，没有静默换模型。未完成调用没有最终 token 用量，不能记作零成本。

本轮已完成调用合计 input={usage['input_tokens']:,}、output={usage['output_tokens']:,}，其中 reasoning={usage['reasoning_output_tokens']:,}。缓存是 input 的子集，reasoning 是 output 的子集，不重复累加。详细时间见下表。

| 轨迹 | 官方结果，仅供研究者 | 步数 | 输入字符数 | 有效调用时间（秒） |
| --- | --- | ---: | ---: | ---: |
{coverage_rows}

## 全量使用入口

计划目录保留唯一可维护源文件：[prompt_v4.txt]({PLAN / 'prompt_v4.txt'})、[output_schema_v4.json]({PLAN / 'output_schema_v4.json'})、[validate_output_v4.py]({PLAN / 'validate_output_v4.py'})。继续使用 `prepare_input_v3.py`，输入协议没有变化。

所有输入已准备好。为避免重复付费，[剩余清单](manifest_v4_remaining.json) 排除本轮首次已完成的 15 条；[已评分索引](v4_scored_index.json) 固定这 15 条的原始结果，不用重复评分挑选更好的标签。

在本实验目录，后续执行剩余 525 条的命令是：

```bash
python scripts/run_judge_v4.py --execute --run v4_full_01 --manifest manifest_v4_remaining.json
```

本报告没有执行该命令。若需要完全重新评分 540 条，清单为 `manifest_v4_corpus.json`。每次调用保存实际 prompt、输入、原始响应、模型配置、事件与用量；结构不合格不进入有效判断，最多两次尝试，不自动改写标签。

## 结果文件

- [全部逐步结果](review/V4_TRAJECTORIES.md)：首次与重复评分的逐维标签和依据。
- [比较统计](review/v4_comparison.json)、[最终验证](v4_final_validation.json)。
- [回归检查点](review/v4_regression_checks.json)、[新任务检查点](review/v4_fresh_checks.json)。
- [全量本地输入检查](v4_corpus_preflight.json)、[v3 历史报告](V3_REPORT.md)。
'''
    (ROOT / "V4_HIGH_REPORT.md").write_text(report)
    print(json.dumps({"status": status["status"], "completed_calls": len(completed), "attempts": len(attempts),
                      "repeat_same": repeat["same_cells"], "repeat_total": repeat["cells"],
                      "same_v3_pair_consistency": [224-len(shared_changes), 224], "remaining": len(remaining["samples"]),
                      "primary_six_mean_seconds": primary_mean, "reported_usage": dict(usage)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
