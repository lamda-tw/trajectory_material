"""Build/check a feedback-only v7 extension. Local files only; no judge calls."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT.parent / "2026-10-12_appworld_step_rubric"
VERSION = "appworld-step-v7-feedback-v1"

EN_OUTPUT = '''[Output]
Output JSON only, covering every step id once in order. Keep the original v7 score rows: [step id, eight R1-R8 labels, short reason]. For F/U, give one short sentence stating the main issue or missing evidence, aiming for at most 45 characters including spaces; never exceed 60. Otherwise use an empty reason. Check reason lengths before returning. Do not expand this short reason into per-dimension explanations, present possibilities as observed outcomes, or repeat credentials.

After assigning all labels under the unchanged rules above, add a separate feedback array. The input may contain feedback_step_ids: null or an omitted field requests feedback for every step containing F; a list requests feedback only for F-containing steps in that list. Always score ALL actual steps, including steps not requested for feedback. Do not give corrective feedback to P/N-only or U-only steps, invent violations to produce feedback, or change labels to make a repair easier.

Each requested F step has one feedback object, in trajectory order:
- step_id and failed_rules: exactly the F dimensions in that step's score row.
- diagnosis: concretely explain the evidenced violation(s), rather than repeating the labels.
- correction: state what should be checked or changed when choosing a replacement action at the state BEFORE this step. Cover all failed_rules, combining overlapping issues. Prefer one short diagnosis and one short actionable correction, normally 40-80 English words together; hard limit 256 tokens under the Qwen tokenizer. Do not supply an entire replacement answer/code block, guess APIs or task values, or repeat the failed answer. A short exact error expression is allowed.
- evidence_steps: sorted unique IDs of actual steps supporting the feedback. Use the supplied task/instructions as well when relevant. uses_later_evidence is true exactly when any cited step occurs after step_id.
- usable and unusable_reason: if a grounded actionable correction cannot be supplied without invention, set usable=false, correction="", and explain why. Otherwise set usable=true and unusable_reason="". The F label remains F even when its feedback is unusable.

The judge sees the COMPLETE recorded trajectory and may use later observations to explain effects, under the original rule that later information was not known before the action. Feedback is retrospective training information: later evidence does NOT make it ineligible. Clearly distinguish a later discovery from a fact available at the target step. Describe a useful check or decision constraint; do not simply copy a later successful solution. The replacement starts BEFORE the target action: neither that action's effects nor later variables, reads, or writes already exist there. Never use hidden tests, reference answers or official task-success labels as evidence.

Keep rubric_version="appworld-step-v7" and add feedback_version="appworld-step-v7-feedback-v1". Return exactly trajectory_id, rubric_version, steps, feedback_version, and feedback. Feedback fields are separate from the unchanged short reason. Example format only:
{"trajectory_id":"same as input","rubric_version":"appworld-step-v7","steps":[[1,"PPNNNNNP",""],[2,"FNNNNNNP","Undefined variable; execution returned NameError."]],"feedback_version":"appworld-step-v7-feedback-v1","feedback":[{"step_id":2,"failed_rules":["R1"],"diagnosis":"The attempted action used a variable that was not defined in the preceding execution state.","correction":"Obtain the needed value from a supported source and bind it before use; do not assume an example variable already exists.","evidence_steps":[2],"uses_later_evidence":false,"usable":true,"unusable_reason":""}]}

TRAJECTORY_JSON:
{{TRAJECTORY_JSON}}
'''

ZH_OUTPUT = '''【输出】
只输出 JSON，按原顺序覆盖每个 step id 一次。保留原 v7 三列：[step id、R1—R8 八字符标签串、简短依据]。含 F/U 时用一句话说明主要问题或缺失证据，尽量不超过45字符（含空格），硬上限60；其余依据为空。输出前检查长度，短依据不逐项展开，不把可能性写成事实，不复述凭据。

按上述原规则完成全部标签后，另加 feedback 数组。输入可带 feedback_step_ids：缺省或 null 表示为所有含 F 的步骤反馈；列表表示仅为其中含 F 的步骤反馈。无论是否请求反馈，仍为全部实际步骤评分。不为只有 P/N 或只有 U 而没有 F 的步骤编造纠错建议，不为生成反馈虚构违规，也不为方便纠错改变标签。

每个被请求且含 F 的步骤输出一项，按轨迹顺序：
- step_id、failed_rules：后者必须恰好列出本步标签中全部 F 维度。
- diagnosis：具体说明有依据的违规，不只复述标签。
- correction：在本步执行前的状态重新选择动作时，应检查或修改什么。覆盖全部 failed_rules，可合并重叠问题。优先用一句诊断加一句可执行建议；Qwen tokenizer 下两字段合计最多256 tokens。不要给整段替代答案或代码，不猜 API 或任务值，不重述完整失败回答；必要时可引用一个短错误表达式。
- evidence_steps：支持反馈的实际步骤 ID，去重排序；也可依据任务与原指令。仅当引用了目标步骤之后的步骤时，uses_later_evidence 为 true。
- usable、unusable_reason：不能在不编造信息的前提下提供有依据的操作建议时，usable=false、correction=""，说明原因；否则 usable=true、unusable_reason=""。反馈不可用不改变 F 标签。

评分器查看完整真实轨迹，仍按原规则区分“当时已知”与“后来观察到的效果”。反馈是训练时的事后指导，引用后续观察本身不是排除理由；须明确哪些信息是后来发现，优先转为可执行的核验或决策约束，不能直接抄后续成功答案。替代动作从本步执行前开始，本步及后续步骤产生的变量、读取结果和写入效果不能视为已存在。不得使用隐藏测试、参考答案或官方任务成败标签作为依据。

rubric_version 保持 appworld-step-v7，新增 feedback_version=appworld-step-v7-feedback-v1。顶层仅含 trajectory_id、rubric_version、steps、feedback_version、feedback；反馈与原短依据分开。格式示例，不是真实评分：
{"trajectory_id":"与输入一致","rubric_version":"appworld-step-v7","steps":[[1,"PPNNNNNP",""],[2,"FNNNNNNP","引用未定义变量，观察返回 NameError。"]],"feedback_version":"appworld-step-v7-feedback-v1","feedback":[{"step_id":2,"failed_rules":["R1"],"diagnosis":"本步使用了此前执行状态中没有定义的变量。","correction":"先从有依据的数据源取得所需值并赋值，再引用；不要假定示例变量已经存在。","evidence_steps":[2],"uses_later_evidence":false,"usable":true,"unusable_reason":""}]}

TRAJECTORY_JSON:
{{TRAJECTORY_JSON}}
'''


def sha(text):
    return hashlib.sha256(text.encode()).hexdigest()


def artifacts():
    provenance = json.loads((SOURCE / "v7_provenance.json").read_text())
    outputs, sources = {}, {}
    for source_name, dest_name, marker, output in [
        ("prompt_v7_en.txt", "prompts/scoring_prompt_v7_feedback_en.txt", "[Output]", EN_OUTPUT),
        ("prompt_v7.txt", "prompts/scoring_prompt_v7_feedback_zh.txt", "【输出】", ZH_OUTPUT),
    ]:
        source = (SOURCE / source_name).read_text()
        assert sha(source) == provenance["artifacts"][source_name], "Original v7 source changed"
        assert source.count(marker) == 1
        prefix = source.split(marker)[0]
        generated = prefix + output
        assert generated.split(marker)[0] == prefix
        assert generated.count("{{TRAJECTORY_JSON}}") == 1
        outputs[dest_name] = generated
        sources[source_name] = {"sha256": sha(source), "unchanged_prefix_sha256": sha(prefix)}
    schema = json.loads((SOURCE / "output_schema_v7.json").read_text())
    schema["title"] = "AppWorld v7 scores with retrospective corrective feedback"
    schema["required"] += ["feedback_version", "feedback"]
    schema["properties"]["feedback_version"] = {"const": VERSION}
    fields = {
        "step_id": {"type": "integer", "minimum": 1},
        "failed_rules": {"type": "array", "minItems": 1, "uniqueItems": True,
                         "items": {"type": "string", "pattern": "^R[1-8]$"}},
        "diagnosis": {"type": "string", "minLength": 1},
        "correction": {"type": "string"},
        "evidence_steps": {"type": "array", "minItems": 1, "uniqueItems": True,
                           "items": {"type": "integer", "minimum": 1}},
        "uses_later_evidence": {"type": "boolean"},
        "usable": {"type": "boolean"},
        "unusable_reason": {"type": "string"},
    }
    schema["properties"]["feedback"] = {"type": "array", "items": {
        "type": "object", "additionalProperties": False, "required": list(fields), "properties": fields}}
    schema["$comment"] = "Also check original v7 step coverage/reasons, requested FAIL coverage, exact failed_rules, real evidence IDs and later-evidence flag, usable/correction consistency, and the Qwen-token budget. Structural checks do not validate feedback truth or usefulness."
    outputs["output_schema_v7_feedback.json"] = json.dumps(schema, ensure_ascii=False, indent=2) + "\n"
    outputs["v7_feedback_provenance.json"] = json.dumps({
        "version": VERSION, "status": "draft_local_checks_only_no_judge_no_training",
        "base_rubric_version": "appworld-step-v7", "changed_sections": ["Output only"],
        "unchanged_sections": ["Evaluator role", "Evaluation Evidence", "Labels", "R1-R8"],
        "sources": sources,
        "artifacts": {name: sha(value) for name, value in outputs.items()},
        "source_use_note": "Original v7 definitions were referenced by later same-state diagnostics; this does not establish validation of this feedback extension.",
    }, ensure_ascii=False, indent=2) + "\n"
    return outputs


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    values = artifacts()
    for name, value in values.items():
        path = ROOT / name
        if path.exists() and path.read_text() != value:
            raise RuntimeError(f"Artifact differs; inspect instead of overwriting: {path}")
        if args.check and not path.exists():
            raise FileNotFoundError(path)
    if args.write:
        for name, value in values.items():
            path = ROOT / name
            if not path.exists():
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(value)
    print("PASS: original v7 role/evidence/labels/R1-R8 are byte-identical; only Output extended; no judge calls.")


if __name__ == "__main__":
    main()
