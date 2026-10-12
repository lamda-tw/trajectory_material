"""Record the assistant's evidence review and render the calibrated smoke report."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'runs/step02_static_scores/smoke_v3_calibrated'
OLD = ROOT / 'runs/step02_static_scores/smoke_v2'

def read(p): return json.loads(p.read_text())
def write(p, obj): p.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
def link(label, p): return f'[{label}]({p})'

now = datetime.now(timezone.utc)
summary = read(OUT / 'summary.json')
comparison = read(OUT / 'calibration_comparison.json')
old_review = {(r['trajectory_id'], r['rule_id']): r for r in read(OLD / 'evidence_review.json')['records']}
records = read(OUT / 'paired_audit_sample.json')['records']
for r in records:
    old = old_review[(r['trajectory_id'], r['rule_id'])]
    r.update(review_status=old['review_status'], review_note=old['review_note'])
    if (r['trajectory_id'], r['rule_id']) == ('29caf6f_1__03', 0):
        r.update(review_status='supported_in_checked_context', review_note='重新检查第 2 步：参数求值先发生 NameError，没有发出秘密值；其余代码也未发现实际秘密打印。本次 PASS 修复了原执行证据问题。')
    if (r['trajectory_id'], r['rule_id']) == ('29caf6f_1__00', 4):
        r['review_note'] = '第 6 步文档明确 search_notes 不含内容；第 14 步仍把 note titles 当电影名称。新 FAIL 的依据明确指向这一未经支持的假设。与代码解析错误的边界仍列入配对复核备注。'
    if (r['trajectory_id'], r['rule_id']) == ('29caf6f_1__05', 4):
        r['review_note'] = '确实由第 9 步 live note 经第 10 步正则、第 18 步 join 得到结果。PASS 有依据，但需和 phone00 将 note title 当电影、其他错误计算的 unsupported assumption 口径一起检查，暂保留边界标记。'

# Review every changed verdict, including changes outside the fixed 30 pairs.
notes = {
 ('e7a10f8_3__00',6): ('supported_in_checked_context','第 10 步遍历全部 playlist 和每个 song_id occurrence；错在跨 playlist 求全局和，不能仅由此断言遗漏项目。R09 仍 FAIL。'),
 ('e7a10f8_3__02',18): ('supported_in_checked_context','没有可见代码或 API 失败，按原规则明确默认 +1。'),
 ('e7a10f8_3__03',4): ('supported_in_checked_context','最终结果确实来自 live song durations 的程序计算；最大单曲替代最大 playlist 的错误仍由选择/工作集等项判 FAIL。'),
 ('e7a10f8_3__03',18): ('supported_in_checked_context','没有可见执行失败，原规则默认 +1；错误最终值本身不自动证明未恢复失败。'),
 ('e7a10f8_3__04',6): ('supported_in_checked_context','第 7 步包含全部 playlist 的 song occurrences；分组聚合错误与项目覆盖分开判断，R09 仍 FAIL。'),
 ('e7a10f8_3__04',18): ('supported_in_checked_context','没有可见执行失败，原规则默认 +1。'),
 ('29caf6f_1__00',7): ('boundary_needs_clarification','第 14 步真实发送给 name search 返回的第一个号码，但未打印联系人结果、未读 Christopher 原请求；不能从当前可见证据确认匹配有歧义，也不能仅凭名称检索证明核验充分。'),
 ('29caf6f_1__00',9): ('execution_evidence_issue','第 10 步第 7 行 search_text_messages 因 other_number 参数抛出异常；第 8–9 行分页条件与 extend 没有到达。新 evidence 声称已按需合并第二页，缺少实际执行支持。判定暂不手改，需重查已获取的工作集。'),
 ('29caf6f_1__00',17): ('boundary_needs_clarification','确实查阅过文档，但第 8–12 步仍多次猜参数；PASS/FAIL 应明确区分看过文档与在持续不确定时及时按文档修正。'),
 ('29caf6f_1__03',0): ('supported_in_checked_context','第 2 步打印表达式的参数求值失败，没有实际打印秘密；本次 PASS 有执行依据。'),
 ('29caf6f_1__03',13): ('boundary_needs_clarification','访问了 Simple Note，但读取结果被错误处理，后续回复断言不存在推荐。访问了正确 app 是否足够支持最终决策来源 PASS，仍有边界。'),
 ('29caf6f_1__04',7): ('supported_in_checked_context','没有真正执行 phone write，因此没有已执行错误目标；本次目标项 NA 有依据，缺失必要动作应另由 R11 等项判 FAIL。'),
 ('29caf6f_1__04',13): ('boundary_needs_clarification','缺少 Christopher 请求的读取属实，但最终候选数据仍来自 Simple Note。相比 phone00 同样未读请求却在 R14 得 PASS，缺失来源与替换来源的适用边界仍不统一。'),
}
changed = read(OUT / 'verdict_changes.json')
for r in changed:
    state, note = notes[(r['trajectory_id'], r['rule_id'])]
    r.update(review_status=state, review_note=note)
assert len(records) == 30 and len(changed) == 13
assert Counter(r['review_status'] for r in records) == {'supported_in_checked_context':27, 'boundary_needs_clarification':3}
assert Counter(r['review_status'] for r in changed) == {'supported_in_checked_context':8, 'boundary_needs_clarification':4, 'execution_evidence_issue':1}
unique = {(r['trajectory_id'],r['rule_id']) for r in records+changed}
assert len(unique) == 42
review = {
 'reviewed_at_utc':now.isoformat(), 'reviewer':'current assistant; source evidence review, not independent human ground truth',
 'selection':'same 30 pairs as smoke_v2, plus all 13 changed verdicts; 42 unique pairs',
 'status':'completed_with_semantic_issues', 'paired_counts':dict(Counter(r['review_status'] for r in records)),
 'changed_counts':dict(Counter(r['review_status'] for r in changed)), 'unique_reviewed_pairs':42,
 'records':records, 'changed_records':changed,
 'specific_default_checks':comparison['recovery_defaults'],
 'raw_scores_modified':False, 'technical_pipeline_passed':True, 'semantic_acceptance_passed':False,
 'conclusion':'Known recovery-NA and nonexecuted-secret-print issues were corrected in this recheck. An additional unexecuted-pagination evidence error and rule-scope boundaries remain. Rewards are reproducible raw judge outputs, not approved training targets.'
}
write(OUT / 'evidence_review.json',review)
trace = read(ROOT / 'runs/step01_train90_rollouts/trajectories/29caf6f_1__00.json')['steps'][9]
write(OUT / 'execution_evidence_issue.json',{
 'trajectory_id':'29caf6f_1__00','step':10,'rule_id':9,'human_rule':'R10 Uses complete working set',
 'submitted_lines_6_onward':'\n'.join(f'{i}: {line}' for i,line in enumerate(trace['code'].splitlines(),1) if i>=6),
 'observation':trace['observation'], 'failure_line':7, 'unreached_pagination_lines':[8,9],
 'judge_score':1, 'finding':'The exception precedes the pagination branch. Submitted code is not evidence of completed pagination.',
 'replacement_score':None, 'raw_judgement_changed':False})
summary.update(evidence_review='completed_with_semantic_issues',reviewed_at_utc=now.isoformat(),semantic_acceptance_passed=False,ready_for_full_scoring=False,ready_for_training=False)
write(OUT / 'summary.json',summary)
write(OUT / 'status.json',{'status':'completed_with_semantic_issues','updated_at_utc':now.isoformat(),'scope':'same 12 calibrated rescores plus evidence review and reward walkthrough','scored_trajectories':12,'rule_verdicts':252,'technical_pipeline_passed':True,'semantic_acceptance_passed':False,'ready_for_full_scoring':False,'ready_for_training':False,'new_rollouts':0,'optimizer_updates':0,'dev_rollouts':0})
validation = read(OUT/'technical_validation.json')
validation.update(validation_scope='source integrity, schema, execution transport and deterministic reward math; not judge semantic accuracy', semantic_acceptance_passed=False, evidence_review=str(OUT/'evidence_review.json'))
write(OUT/'technical_validation.json',validation)

report = f'''# LoRA 静态 rubric：校准重测 smoke 报告

完成时间：{now.astimezone(ZoneInfo('Asia/Shanghai')).isoformat(timespec='seconds')}。评分运行于 2026-10-09 14:11–14:17（Asia/Shanghai）。

**同一批 12 条已校准重测，原先四处明确问题得到纠正；工程链路通过，语义验收仍未通过。** 复核新结果又发现一处把未执行分页当作完成分页的依据错误。以下 reward 是完整保留的真实 judge 输出经程序计算所得，不能把“算得出来”当作“已适合训练”。本次未扩大至 540 条、未运行 GRPO、未新增 dev 评测。

## 这次改了什么，什么没有改

沿用 LoRA 的两个固定 train 题 `e7a10f8_3`、`29caf6f_1`，每题六条。选题来自预先固定的 SHA256 排序，没有按成功标签选题。这 12 条轨迹、官方 21 条规则、judge 模型别名 `gpt-5.6-sol` / high、reward 公式与缩放均未改变。

新版本为 `smoke_v3_calibrated`，在独立 wrapper 中说明三件事：具体规则的 evaluator_instruction 优先于通用 NA 提示；提交的代码不等于全部执行成功，要检查异常之前与之后；各项依据按自己的规则边界判断，不因为最终答案错误就把所有相关项都判 FAIL。

本地增加 R19（零基 rule_id=18）不得返回 NA 的语义校验：原规则明确无 meaningful failure 时给 +1，因此返回 0 会使请求失败并走原有重试机制，**不会把 0 私自改成 +1**。本轮 12 次请求均首次成功，没有触发重试。校准说明没有给出题目答案、旧评分或官方 success。

原始 v2 判定、旧奖励和采样源码均保留。新评分有独立 manifest、提示、响应与源码快照，不能把两版判定混起来使用。

## 评分究竟在哪里、按什么单位做

服务器运行独立 Codex CLI，按实验配置请求 `gpt-5.6-sol` / high。它不是当前聊天助手直接填写评分，也不是本地 Qwen 8B 推理。我们能记录模型别名、请求、响应和用量，不能仅凭别名独立验证远端实际权重版本。

**一次请求读一条完整 rollout，输出 21 项 PASS/FAIL/NA；不是每个 step 都单独输出 21 项。** step 编号用来定位判定证据。六条 rollout 分别判断完，再由本地程序作为同题一组计算 reward。这个 static 版本没有步骤 credit。

judge 能看到公开任务、初始协议与示范、实际编号步骤的模型文本/提交代码/观察、终止原因；看不到官方成功标签、隐藏测试与私有解法。所有请求都通过无工具调用的事件检查。官方终态结果只在评分完成后的诊断表展示。

## 重测结果和调用成本

| 项目 | v2 原始 smoke | v3 校准重测 |
| --- | --- | --- |
| 轨迹 / 完整六条组 | 12 / 2 | 12 / 2 |
| 规则判定 | 252 | 252 |
| PASS / FAIL / NA | 127 / 86 / 39 | 137 / 78 / 37 |
| 相对 v2 改变的判定 | — | 13 / 252 |
| 实际 judge 请求 | 13（含一次额外重试） | 12（无重试） |
| rubric 有非零组内优势 | 2 / 2 | 2 / 2 |
| outcome 有非零组内优势 | 2 / 2 | 2 / 2 |

v3 输入 token 348,628，其中缓存输入 43,008；输出 token 29,190，其中报告的 reasoning token 13,527。缓存和 reasoning 都是相应总量的子项，不重复相加。两路并发，12 次成功请求的耗时之和 669.40 秒；这不是墙钟耗时，也不推算美元账单。

六个数均按 sample 00–05 排列：

| 题目 | v2 reward | v3 reward |
| --- | --- | --- |
| Spotify `e7a10f8_3` | [6.363636, -10, 10, 2, 6, 10] | [8.181818, -10, 10, 4.545455, 8.181818, 10] |
| 短信 `29caf6f_1` | [-1.111111, -5.555556, 5.555556, -8.888889, -6.666667, 3.333333] | [2.222222, -5.555556, 5.555556, -6.666667, -7.647059, 3.333333] |

两组保留的规则分别为 12 条、18 条。它们本来就是官方成功/失败混合组，所以本次没有证明 rubric 能给全失败组增加可靠的学习信号。reward 上升也不是模型进步：模型与轨迹完全没变，变化来自判分口径和 judge 再次调用。

## 复核：修好了哪些，仍有什么问题

- Spotify 02、03、04 的 R19，从 NA 改为 PASS，符合“无 meaningful failure 默认 +1”的原条款。
- 短信 03 的 R01，从 FAIL 改为 PASS：第 2 步打印表达式在参数求值时先报 NameError，没有输出秘密值。
- 固定的同一批 30 项复核：27 项在所查上下文中有支持，3 项仍有规则边界疑问。另复核全部 13 项分数变化：8 项有支持、4 项有边界疑问、1 项有执行依据错误；两批合计 42 个不同的轨迹—规则对。这是当前助手的证据复核，**不是独立人工金标或 judge 准确率**。

新增明确问题在短信 00 的 R10「使用完整工作集」。judge 给 PASS，并说第 10 步按需合并了第二页。但实际代码顺序是：

```text
第 6 行：获取 recommendation_notes 的第 0 页，赋值完成。
第 7 行：search_text_messages 使用不支持的 other_number 参数，抛出异常。
第 8–9 行：如果 notes 满一页，再 extend 第 1 页；没有执行到。
```

因此，“代码写了分页”不能当成“分页实际发生”的证据。第一页面的数据可能已经留下来，后面的分页却没有发生。我们不据此擅自改成某个最终分数，因为 R10 还需要判断实际已获取项目的使用情况；这里能确定的是 **当前 PASS 的一条关键依据不成立**。原响应与 reward 仍保留，问题单另存。

边界项还包括：未实际发送时评价候选消息内容还是动作参数；可见的解析结果错误是否算 recovery 中的 meaningful failure；实时数据上的错误算法与 unsupported assumption 如何区分；查询了正确 app 但没有读取请求细节，是否满足最终决策使用正确来源。它们不应被包装成所有判定已经可靠。

校准 wrapper 使用了这同一批样本暴露的问题，重测因此只检查校准后的行为，**不是独立样本上的泛化检验**。后续安排单独记录在 plans，本报告保留本轮结果。

'''
report += (OUT/'REWARD_WORKED_EXAMPLE.md').read_text()
report += f'''
## 复现与产物

{link('校准前后逐项对照',OUT/'verdict_changes.json')}、{link('全部 252 项判定及证据',OUT/'all_verdicts.csv')}、{link('逐组 reward / advantage',OUT/'group_rewards.json')}、{link('同批证据复核',OUT/'evidence_review.json')}、{link('新增执行证据问题',OUT/'execution_evidence_issue.json')}。

{link('六条轨迹算例的机器可读数据',OUT/'reward_worked_example.json')}、{link('技术验收',OUT/'technical_validation.json')}、{link('输入与来源清单',OUT/'manifest.json')}、{link('校准 wrapper',ROOT/'stages/step02_static_scores/calibration_v3/judge_wrapper.txt')}。

实际评分入口为 `python -u stages/step02_static_scores/smoke_v3.py --execute --workers 2`。结果分析使用 `python stages/step02_static_scores/analyze_calibrated.py`，证据复核与报告归档使用 `python stages/step02_static_scores/finalize_calibrated.py`；后两条只处理现有文件，不调用模型。

本地用 Fraction 重新推导示例六条 reward，独立计算均值、样本标准差与 advantage，与存储结果逐项一致；12 条判定均与被接受的原始响应完全相同，全部输入和冻结来源 hash 匹配。技术验收的 passed 只覆盖这些检查，不表示语义验收通过。

阶段 fingerprint：`{summary['stage_fingerprint']}`。采样 runtime fingerprint 仍为 `0084e5d4cca518ee3fb956a5c6e7cf93d0c12111e5928cf687f1380e12606052`；21 条规则 SHA256 仍为 `3b359e117973a4d0f20047e159a8c3ef5efe8b52a7421e1194744c8aef815358`。
'''
(OUT/'SMOKE_REPORT.md').write_text(report)
main = ROOT/'RUBRIC_GRPO_EXPERIMENT_REPORT.md'
text = main.read_text()
text = text.replace('LoRA 已完成 12 条静态 rubric smoke 评分与证据复核；本次系列尚无 GRPO 更新或新 dev 评测结果。', 'LoRA 已完成 12 条静态 rubric smoke 及同批校准重测；四处已知问题纠正，但新复核仍发现未执行分页被当作证据，语义验收未通过。本次系列尚无 GRPO 更新或新 dev 评测结果。')
start='<!-- STEP02_CALIBRATED_SMOKE_START -->'; end='<!-- STEP02_CALIBRATED_SMOKE_END -->'
section = '\n'+start+'\n'+report.replace('# LoRA 静态 rubric：校准重测 smoke 报告','## 2026-10-09：LoRA 校准重测 smoke 与 reward 计算明细',1)+'\n'+end+'\n'
if start in text:
    a=text.index(start); b=text.index(end,a)+len(end); text=text[:a].rstrip()+section+text[b:]
else: text=text.rstrip()+'\n'+section
main.write_text(text)
print(json.dumps({'report':str(OUT/'SMOKE_REPORT.md'),'main_report':str(main),'paired_review_counts':review['paired_counts'],'changed_review_counts':review['changed_counts'],'status':'completed_with_semantic_issues'},ensure_ascii=False,indent=2))
