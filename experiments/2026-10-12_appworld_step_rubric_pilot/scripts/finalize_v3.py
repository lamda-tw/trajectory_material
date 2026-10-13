"""Validate completed v3 experiment artifacts and write a review report."""
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


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+"\n")


def main():
    data = read(ROOT / "review/v3_comparison.json")
    first, new, repeat = (data[k] for k in ["primary", "unseen", "repeat"])
    funcs = runpy.run_path(str(ROOT / "scripts/run_judge_v3.py"))
    calls, usage = [], Counter()
    for run_name in ["v3_test", "v3_unseen", "v3_repeat"]:
        run = ROOT / "runs" / run_name
        assert (run / "prompt.txt").read_bytes() == (PLAN / "prompt_v3.txt").read_bytes()
        assert read(run / "schema.json") == read(PLAN / "output_schema_v3.json")
        for folder in sorted(p for p in run.iterdir() if p.is_dir()):
            payload, result = read(folder / "input.json"), read(folder / "judgement.json")
            funcs["validate"](result, payload, read(run / "schema.json"))
            for attempt in sorted(folder.glob("attempt_*")):
                audit = funcs["audit_events"](attempt / "events.jsonl")
                assert audit["tool_items"] == []
                raw = read(attempt / "response.json")
                assert raw == result, "This finalizer requires explicit accounting for any failed/retried response"
                usage.update(audit["usage"])
                calls.append(str(attempt.relative_to(ROOT)))
    hashes = {f"v{i}": sha(PLAN / f"prompt_v{i}.txt") for i in [1, 2, 3]}
    assert hashes == {
        "v1": "8c80e5480fd925eff89aa887a903c34b89bf3650e5e0ab0073624287fc8bec1a",
        "v2": "e8d175badc15c138459840950922cd282ce24ea82e9f66e8f830abf5aa4986d0",
        "v3": "1743b4b6cd6082c809bbde4791c087ff00428233b914dd5e359f745e48e40151"}
    assert len(calls) == 10
    unique_steps = first["steps"] + new["steps"]
    stable = repeat["same_cells"] / repeat["cells"]
    changed_rubrics = Counter(c["rubric"] for c in repeat["changed_cells"])
    f_switches = [c for c in repeat["changed_cells"] if "F" in [c["first"], c["repeat"]]]
    old = read(ROOT / "review/comparison.json")["versions"]
    seconds_v1 = mean(s["seconds"] for s in old["v1"]["samples"])
    seconds_v2 = mean(s["seconds"] for s in old["v2"]["samples"])
    old_chars = mean(len((ROOT / s["attempt"] / "response.json").read_text()) for s in old["v2"]["samples"])
    new_chars = mean(s["response_characters"] for s in first["samples"])
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).isoformat()
    validation = {"completed_at": timestamp, "new_completed_calls": len(calls),
                  "unique_trajectories": 8, "unique_steps": unique_steps,
                  "rated_rows_including_repeats": unique_steps + repeat["steps"],
                  "all_schema_step_coverage_and_reason_checks_passed": True,
                  "all_source_input_and_request_hash_checks_passed_in_analyzer": True,
                  "all_judge_tool_audits_passed": True, "raw_judgements_unmodified": True,
                  "official_outcomes_excluded_from_inputs": True, "prompt_hashes_unchanged": hashes,
                  "completed_call_usage": dict(usage), "attempts": calls,
                  "no_replay_training_reward_or_weight_generation": True,
                  "caveat": "Structural validation and selected evidence checks do not establish global semantic accuracy."}
    write(ROOT / "v3_final_validation.json", validation)
    rows = "\n".join(f"| {s['id']} | {s['steps']} | {s['seconds']:.1f} |" for s in first["samples"])
    repeat_changes = "\n".join(f"| {c['trajectory']} | {c['step']} | {c['rubric']} | {c['first']} → {c['repeat']} |" for c in repeat["changed_cells"])
    failed_new = [c for c in new["checks"] if not c["matches"]]
    report = f'''# prompt_v3 实测报告

日期：2026-10-12（北京时间）。完成时间：{timestamp}。

**结论：v3 可以用于下一阶段有抽检的 step 标注试验；当前证据不足以把它的输出直接当作全量训练真值。** 原有错误识别有所改善，新任务仍暴露维度误判和证据过度推断。此次没有修改 v3、生成 v4、合成 reward 或训练权重。

## 测试范围

- 原 6 条完整 base 轨迹：成功 3、失败 3，共 66 步，与 v1/v2 对照。
- 新增 2 条未参与 prompt 修改的任务：电费汇总成功轨迹、照片目录压缩失败轨迹，共 33 步。19 个检查点在这两条的 judge 调用前冻结。
- 对闹钟成功轨迹和便签成功轨迹各重复调用一次：请求逐字相同，共 28 步、224 个维度标签。
- 共 10 次新调用，8 条不同轨迹、99 个不同步骤；包括重复评分共 127 行。每次输入完整轨迹并返回全部 step，使用同一 prompt 和输出格式。

配置沿用 `gpt-5.6-sol / high`，最多同时两个请求。评分工具和浏览关闭，事件日志复核通过；官方成败仅用于研究者选样和事后分析，未送给 judge。所有调用首试有效，无重试。输入、原始响应、事件、耗时和快照见 [runs](runs/)。

## 主要结果

| 指标 | v1 | v2 | v3 |
| --- | ---: | ---: | ---: |
| 原六条格式及 step 覆盖通过 | 6/6 | 6/6 | 6/6 |
| 原开发检查点符合数 | 24/28 | 27/28 | {first['check_matches']}/28 |
| 原六条平均调用时间 | {seconds_v1:.1f} 秒 | {seconds_v2:.1f} 秒 | {first['mean_call_seconds']:.1f} 秒 |

新增任务：格式及覆盖 2/2，预设检查点 **{new['check_matches']}/{new['checks_total']}**。这两个数字都是选定检查点的符合数；旧样本用于 prompt 开发，新样本由同一助手按可见证据复核，均不能称为独立准确率。额外复核发现的问题另存，不改写原检查点分母。

v3 保留了几类关键判断：成功轨迹也标执行错误；失败便签轨迹第 11 步同时标 R3=F、R5=P，区分错误说明与正确写入；错误闹钟对象、未执行第二代码块却声称完成、用每首三分钟估算时长均被识别。成功便签轨迹第 12 步的无效重复查询恢复为 R6=F。

## 新任务暴露的问题

1. **提交被误判成业务操作错误。** `76f2c72_1__03` 第 16 步只有 `complete_task(answer=368.0)`，却得到 R5=F。v3 自己规定提交在 R5 应为 N；答案或覆盖争议不应扩散到这个维度。这是原 19 个检查点之外的新发现。
2. **部分执行后的重试漏判。** `7d7fbf6_1__00` 第 12 步循环可能已压缩并删除部分目录，随后报错。第 13 步没有核对已完成范围便从头重试，judge 给 R6=P；预设期望是 F。它认可了修正 overwrite 参数，却忽略同一维度中优先判 F 的不当重试。后续观察证实 Athens 目录已不存在。
3. **短依据有未经支持的事实。** 压缩轨迹第 16 步确实输出到错误目录，R5=F 有依据；但解释额外断言“覆盖了已有文件”。`overwrite=True` 只表示允许覆盖，输入并未证明这些同名目标文件之前存在。
4. **未知覆盖被说成确定漏算。** 电费轨迹未读五月 PDF，也未取当前日期。judge 断言漏算五月账单；根据可见材料应明确区分四份 TXT 算术正确、当前年份及全局覆盖未充分确认。官方结果成功不要求 judge 全部打 P，但文件名也不足以证明确定漏了应计金额。

详细证据见 [v3_review_findings.json](review/v3_review_findings.json)。原始模型标签全部保留，没有人工修正后再汇报通过率。

## 同输入重复评分

224 个标签中 **{repeat['same_cells']} 个一致（{stable:.1%}）**，{len(repeat['changed_cells'])} 个变化。其中涉及 F 与非 F 切换的有 {len(f_switches)} 个；不同维度变化数为 `{dict(changed_rubrics)}`。该结果只描述这两条输入的一次重评，不代表总体稳定性。

| 轨迹 | Step | 维度 | 首次 → 重复 |
| --- | --- | --- | --- |
{repeat_changes}

原六条 v2→v3 共 54/528 个标签变化，属于版本差异，不能当作重复性或改进率。单次检查点全部通过也不能消除细粒度标签漂移。

## 成本与输出

v3 prompt 从 v2 的 5,578 字符减为 1,786；原六条平均最终响应从 {old_chars:.0f} 字符减为 {new_chars:.0f} 字符。实测平均调用时间下降约 {(1-first['mean_call_seconds']/seconds_v2):.1%}，而非随文字长度成比例下降。

原六条 v3 报告 input tokens={first['completed_call_usage']['input_tokens']:,}，output tokens={first['completed_call_usage']['output_tokens']:,}，其中 reasoning tokens={first['completed_call_usage']['reasoning_output_tokens']:,}，约占 output 的 {first['completed_call_usage']['reasoning_output_tokens']/first['completed_call_usage']['output_tokens']:.1%}。缓存输入是 input 的子集，reasoning 是 output 的子集，不重复相加。未进行模型档位或推理强度对比，时间差也受服务与缓存状态影响。

| 原六条轨迹 | 步数 | 单次时间（秒） |
| --- | ---: | ---: |
{rows}

两条新任务平均 {new['mean_call_seconds']:.1f} 秒，本次观察到更长耗时，不能把原六条的均值当作固定成本。全量 540 条、超长观察输入和下游训练收益均未实测，不能从这几条直接外推全量成本或收益。

## 如何使用这版结果

可以保留 v3 作为候选 step 标注器，继续少量、多任务的抽检，先用结果定位值得复核的步骤。它已经能识别具体业务错误，当前主要问题在标签适用范围、部分副作用和不确定证据的处理。

暂不直接按 F 数量筛选负样本或计算学习权重：原六条 R8 有 48/66 步为 F，很多只是未查接口规格；协议错误与业务动作错误的学习意义不同。保留各维度、不预设总分与权重的方案仍有必要。

下一次若修改 prompt，应另建 v4，将这些边界简洁地整合进现有 rubric，然后用新的任务验证；不要覆盖 v3 或只对原 28 个检查点调优。本轮保持 v3 原文不变。

## 文件与复现

- [逐轨迹逐步结果](review/V3_TRAJECTORIES.md)：首次、新任务及重复评分的全部标签与短依据。
- [比较与调用统计 JSON](review/v3_comparison.json)、[最终验证](v3_final_validation.json)。
- [六条清单](manifest_v3.json)、[两条新任务清单](manifest_v3_unseen.json)、[新任务预设检查点](review/v3_unseen_checks.json)。
- [冻结 prompt](snapshots/prompt_v3.txt)、[调用配置](judge_config_v3.json)、[v3 执行脚本](scripts/run_judge_v3.py)。

在本实验目录复现，必须使用新的运行名：

```bash
python scripts/run_judge_v3.py --execute --run NEW_RUN_NAME
python scripts/run_judge_v3.py --execute --run NEW_UNSEEN_RUN --manifest manifest_v3_unseen.json
```

这些是同一评分协议的不同选样，不是不同输出模式。v1/v2 历史报告与运行记录保留不变。
'''
    (ROOT / "V3_REPORT.md").write_text(report)
    write(ROOT / "STATUS_v3.json", {"completed_at": timestamp, "status": "v3_pilot_complete_with_known_semantic_issues",
          "current_candidate": "appworld-step-v3", "prompt_sha256": hashes["v3"],
          "new_completed_calls": 10, "unique_trajectories": 8, "unique_steps": unique_steps,
          "development_check_matches": first["check_matches"], "development_checks": first["checks_total"],
          "unseen_check_matches": new["check_matches"], "unseen_checks": new["checks_total"],
          "repeat_same_cells": repeat["same_cells"], "repeat_cells": repeat["cells"],
          "independent_accuracy_measured": False, "full_corpus_validated": False,
          "training_performed": False, "reward_or_weights_generated": False, "report": "V3_REPORT.md"})
    print(json.dumps({"calls": len(calls), "unique_steps": unique_steps, "repeat_consistency": stable,
                      "repeat_f_switches": len(f_switches), "unseen_failed_checks": failed_new,
                      "usage_all_10_calls": dict(usage)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
