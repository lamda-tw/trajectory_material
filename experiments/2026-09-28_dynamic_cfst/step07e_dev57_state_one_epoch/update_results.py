"""Record audited State Dev57 and the complete four-model comparison."""
from pathlib import Path
import json
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
START='<!-- STATE_DEV57_DIAGNOSTIC_START -->'
END='<!-- STATE_DEV57_DIAGNOSTIC_END -->'
def main():
 s=json.loads((OUT/'summary.json').read_text());v=json.loads((OUT/'validation.json').read_text())
 assert s['status']=='completed' and v['passed'] and s['diagnostic']['selection_unchanged']
 y=s['models']['CFST-state'];t=y['evaluator_tests'];p=s['paired_comparison']
 result=f"State-1epoch在Dev57成功{y['success_count']}/57（{y['task_goal_completion']:.1f}%），evaluator条件通过{t['passed']}/{t['total']}（{t['overall_pass_percentage']:.2f}%）"
 report=f'[第7e步总报告]({OUT}/README.md)';details=f'[State的57题evaluator明细]({OUT}/EVALUATOR_DETAILS.md)'
 block=f'''{START}
**2026-09-29四模型Dev57评测已齐：** {result}。相对原epoch5的23/57，新增成功{p['gained_success_count']}题、退步{p['regression_count']}题、净变化{p['net_gain']:+d}题；此前Action为31/57、Mixed为21/57。保持既有Action选择及接受记录；本次没有训练、教师答案或来源60题刷新。详见 {report} · {details} · [四模型逐题对照]({OUT}/four_model_per_task.csv)。
{END}'''
 for f in [ROOT/'plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md',ROOT/'plans/2026-09-28_capability_frontier/DYNAMIC_CFST_OVERVIEW.md',OUT.parent/'README.md']:
  text=f.read_text();assert text.count(START)==text.count(END)==1
  text=text[:text.index(START)]+block+text[text.index(END)+len(END):]
  f.write_text(text)
 section=f'''## 第7e步补充诊断：State-1epoch与原模型是否接近

{result}。本次使用第6b步CFST-state adapter：12条状态构建修复动作各学一遍，共6次参数更新。原模型仍指Qwen3-8B + train90 LoRA第5轮adapter。

| 模型 | 检查30题成功 | Dev57官方成功 | Dev57总体evaluator条件通过 |
| --- | ---: | ---: | ---: |
| 原epoch5 | 17/30 | 23/57；40.4% | 206/291；70.79% |
| State-1epoch | 17/30 | {y['success_count']}/57；{y['task_goal_completion']:.1f}% | {t['passed']}/{t['total']}；{t['overall_pass_percentage']:.2f}% |
| Action-1epoch | 19/30 | 31/57；54.4% | 215/291；73.88% |
| Mixed-1epoch | 15/30 | 21/57；36.8% | 184/291；63.23% |

**State实际变化：** 相对原epoch5新增成功{p['gained_success_count']}题、退步{p['regression_count']}题，净变化{p['net_gain']:+d}题。官方成功率变化{s['diagnostic']['task_success_percentage_point_change']:+.2f}个百分点，全部条件通过率变化{s['diagnostic']['evaluator_overall_percentage_point_change']:+.2f}个百分点；逐题条件通过率平均值为{t['macro_task_pass_percentage']:.2f}%。总体条件通过率与逐题平均值分别计算，均包含失败任务。

**怎样理解：** 本次整题成功小幅增加，但条件通过率下降，不能笼统说与原模型表现相同。两者都失败的{s["score_change_decomposition"]["both_failed"]["task_count"]}题中，通过条件由{s["score_change_decomposition"]["both_failed"]["baseline_passed"]}降至{s["score_change_decomposition"]["both_failed"]["state_passed"]}；这部分退步不会体现在整题成功数中。检查30题中State与原模型总分相同，只是已有观察；Dev57应按本次实际差值与逐题变化解释。本轮没有预先规定“差不多”的容许范围，不能把接近的单次得分直接称为统计等效。四个模型的数据内容、条数和更新次数不同，结果不能单独证明能力分类的因果作用。

**当前决定：** 本次补齐四模型描述性比较；原第7b步Action选择和第7c步接受记录保持不变。57条新轨迹与官方评分完整，{v['checks_passed']}项核验通过，历史结果原哈希不变。没有训练、教师修复、调参或第8步刷新。

产物：{report} · {details} · [四模型逐题对照]({OUT}/four_model_per_task.csv) · [总体对照CSV]({OUT}/model_comparison.csv)。

'''
 f=ROOT/'plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md';text=f.read_text();i=text.find('## 第8步')
 text=text+'\n'+section if i<0 else text[:i]+section+text[i:];f.write_text(text)
 f=OUT.parent/'README.md';f.write_text(f.read_text()+'\n'+section)
 print('Recorded State diagnostic and four-model results; historical selection unchanged.')
if __name__=='__main__':main()
