"""Record audited Mixed Dev57 diagnostics without changing prior branch selection."""
from pathlib import Path
import json,re
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
START='<!-- MIXED_DEV57_DIAGNOSTIC_START -->'
END='<!-- MIXED_DEV57_DIAGNOSTIC_END -->'
def main():
 s=json.loads((OUT/'summary.json').read_text());v=json.loads((OUT/'validation.json').read_text())
 assert s['status']=='completed' and v['passed'] and s['diagnostic']['selection_unchanged']
 y=s['models']['CFST-Mixed'];t=y['evaluator_tests'];p=s['paired_comparison']
 relation={'lower':'低于','equal':'与基线持平，为','higher':'高于'}[s['diagnostic']['observed_task_success_vs_baseline']]
 result=f"Mixed-1epoch在Dev57成功{y['success_count']}/57（{y['task_goal_completion']:.1f}%），evaluator条件通过{t['passed']}/{t['total']}（{t['overall_pass_percentage']:.2f}%）"
 report=f'[第7d步总报告]({OUT}/README.md)';details=f'[57题evaluator明细]({OUT}/EVALUATOR_DETAILS.md)'
 block=f'''{START}
**2026-09-29补充诊断已完成：** {result}。相对原epoch5的23/57，本次净变化{p['net_gain']:+d}题（新增成功{p['gained_success_count']}、退步{p['regression_count']}）；此前Action为31/57。这次完整Dev57评测用于核查Mixed的表现，保留原第7b步选择和第7c步Action接受记录，不训练、不生成教师答案、不刷新来源60题。详见 {report} · {details}。
{END}'''
 for f in [ROOT/'plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md',ROOT/'plans/2026-09-28_capability_frontier/DYNAMIC_CFST_OVERVIEW.md',OUT.parent/'README.md']:
  text=f.read_text();assert text.count(START)==text.count(END)==1
  text=text[:text.index(START)]+block+text[text.index(END)+len(END):]
  f.write_text(text)
 section=f'''## 第7d步补充诊断：Mixed-1epoch在Dev57是否下降

{result}。这里的Mixup指第6b步已有的CFST-Mixed-1epoch；对照“不训”指Qwen3-8B + train90 LoRA第5轮adapter，即尚未追加CFST修复训练的模型。

| 模型 | 官方整题成功 | 总体evaluator条件通过 |
| --- | ---: | ---: |
| 原epoch5 | 23/57；40.4% | 206/291；70.79% |
| Action-1epoch（第7c步） | 31/57；54.4% | 215/291；73.88% |
| Mixed-1epoch（本次） | {y['success_count']}/57；{y['task_goal_completion']:.1f}% | {t['passed']}/{t['total']}；{t['overall_pass_percentage']:.2f}% |

**实际变化：** 相对原epoch5，新增成功{p['gained_success_count']}题、退步{p['regression_count']}题，净变化{p['net_gain']:+d}题；官方成功率变化{s['diagnostic']['task_success_percentage_point_change']:+.2f}个百分点，全部条件通过率变化{s['diagnostic']['evaluator_overall_percentage_point_change']:+.2f}个百分点。逐题条件通过率的平均值为{t['macro_task_pass_percentage']:.2f}%，与全部条件等权汇总的比例分别报告。

**怎样理解：** 检查30题中Mixed是15/30，原epoch5是17/30；Dev57现在有了独立的实际运行结果，应按上表描述，不能把检查30题的下降预先推广。本次是查看Action的Dev结果后追加的固定种子诊断，不能单独证明分类有效，或把差异完全归于混合训练；两分支的数据内容、条数和更新次数也不同。

**当前决定：** 既有Action候选选择和接受记录不变。本次57题从初始环境独立运行、使用原协议并接受官方评分；{v['checks_passed']}项核验通过，旧结果原哈希不变。未训练模型、生成教师答案或启动第8步。

产物：{report} · {details} · [三模型逐题对照]({OUT}/three_model_per_task.csv) · [诊断判断]({OUT}/diagnostic_decision.json)。

'''
 f=ROOT/'plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md';text=f.read_text();marker='## 第8步';i=text.find(marker)
 if i<0:text+='\n'+section
 else:text=text[:i]+section+text[i:]
 f.write_text(text)
 f=OUT.parent/'README.md';f.write_text(f.read_text()+'\n'+section)
 print('Recorded Mixed diagnostic metrics; previous Action selection remains unchanged.')
if __name__=='__main__':main()
