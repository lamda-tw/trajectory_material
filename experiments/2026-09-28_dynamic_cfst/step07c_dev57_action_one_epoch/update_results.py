"""Update rolling plans from audited Dev57 scores without launching another step."""
from pathlib import Path
import json
OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PLANS=ROOT/'plans/2026-09-28_capability_frontier'
def main():
 s=json.loads((OUT/'summary.json').read_text());v=json.loads((OUT/'validation.json').read_text());assert s['status']=='completed' and v['passed']
 a=s['models']['CFST-Action'];b=s['models']['baseline'];at=a['evaluator_tests'];bt=b['evaluator_tests'];p=s['paired_comparison'];gate=s['acceptance']['passed']
 result=f"Action-1epoch在Dev57上成功{a['success_count']}/57（{a['task_goal_completion']:.1f}%），测试条件通过{at['passed']}/{at['total']}（{at['overall_pass_percentage']:.2f}%）"
 decision='通过既有接受门槛，可在后续第8步使用该候选；本次未启动来源60题刷新' if gate else '未通过既有接受门槛，保留原epoch5；本次不进入来源60题刷新'
 report=f'[第7c步总报告]({OUT}/README.md)';detail=f'[57题evaluator明细]({OUT}/EVALUATOR_DETAILS.md)'
 section=f'''### 第7c步实际结果：Action-1epoch的Dev57接受检查（已完成）

**{result}。** 原epoch5基线成功23/57（40.4%），测试条件通过206/291（70.79%）；两者使用相同清单与评测协议。新增成功{p['gained_success_count']}题、退步{p['regression_count']}题，净变化{p['net_gain']:+d}题。

| 指标 | 原epoch5 | Action-1epoch |
| --- | ---: | ---: |
| 官方任务成功率TGC | 23/57；40.4% | {a['success_count']}/57；{a['task_goal_completion']:.1f}% |
| 官方完整任务族成功率SGC | {b['successful_family_count']}/19；{b['scenario_goal_completion']:.1f}% | {a['successful_family_count']}/19；{a['scenario_goal_completion']:.1f}% |
| 全部测试条件通过率 | 206/291；70.79% | {at['passed']}/{at['total']}；{at['overall_pass_percentage']:.2f}% |
| 57题各自测试通过率平均值 | {bt['macro_task_pass_percentage']:.2f}% | {at['macro_task_pass_percentage']:.2f}% |

总体测试条件通过率按“总通过条件÷总条件”计算；逐题平均值先算每题比例再平均。它们用于详细解释结果，不替代官方整题成功率。

**接受判断：{decision}。** 本轮始终只评估检查30题选出的Action，没有用Dev57重新选择State/Mixed、加训、调参或生成教师答案。已完成57条新轨迹和逐题官方评分；{v['checks_passed']}项核验通过。旧模型和旧实验结果保留。

产物：{report} · {detail} · [逐题百分比对照CSV]({OUT}/evaluator_per_task_comparison.csv) · [冻结规则接受判断]({OUT}/acceptance.json)。

'''
 f=PLANS/'METHOD_PROPOSAL.md';text=f.read_text();lines=text.splitlines();lines[2]=f'**更新日期：2026-09-29。第7c步Dev57评测已完成：{result}；相对原epoch5净变化{p["net_gain"]:+d}题。{decision}。**';text='\n'.join(lines)+'\n'
 text=text.replace('检查30题已完成；Action-1epoch的Dev57运行中','检查30题与Action-1epoch的Dev57均完成')
 text=text.replace('| 第8步：接受更新并重新采样 | 等待Dev57结果；当前保留原模型 | 候选是否通过预设接受规则？ |',f'| 第8步：接受更新并重新采样 | {"门槛已通过；尚未刷新来源60题" if gate else "未通过接受检查；保留原模型"} | {"使用接受的候选暴露下一轮错误" if gate else "本轮没有可接受的模型更新"} |')
 marker='### 7.2 Dev57：检查从头完成新任务是否退步'
 text=text.replace(marker,section+marker,1)
 start=text.index('**当前执行：第7c步正在评测唯一候选CFST-Action-1epoch。**')
 end=text.index('\n\n',start)
 text=text[:start]+f'**当前执行已完成：{result}。{decision}。** 详细的逐题条件及总体得分见 {report} 与 {detail}。'+text[end:]
 text=text.replace('**第7b步已选择CFST-Action-1epoch；现在执行其Dev57接受检查，结果待完成后核验。** 以下为既有接受规则。','**第7b步选出的唯一候选现已完成Dev57接受检查，实际结果见上节。** 以下保留既有接受规则。')
 lines=text.splitlines()
 for i,line in enumerate(lines):
  if line.startswith('**当前状态：'):lines[i]=f'**当前状态：第7c步Dev57结果与57题详细evaluator报告已交付。{decision}。详见 {report}。**'
 f.write_text('\n'.join(lines)+'\n')
 f=PLANS/'DYNAMIC_CFST_OVERVIEW.md';text=f.read_text();lines=text.splitlines();lines[6]=f'**2026-09-29当前进展：** 第6b步三支1epoch训练、第7b步检查30题选择和第7c步Dev57接受检查均已完成。检查30题为State 17/30、Action 19/30、Mixed 15/30，唯一候选为Action；{result}。{decision}。详见 {report}。';text='\n'.join(lines)+'\n';text=text.replace('1epoch第7b步完成：17/19/15题成功；Dev57未运行',f'1epoch检查30题完成；Action Dev57 {a["success_count"]}/57，接受门槛{"通过" if gate else "未通过"}')
 text+=f'\n**Dev57接受检查补充：** {result}。它执行的是既有候选接受规则，不是根据Dev重新选训练包；{decision}。{detail}。\n';f.write_text(text)
 f=PLANS/'README.md';text=f.read_text();text=text.replace('**2026-09-29当前执行进展：**','**2026-09-29最新结果：** '+result+'。'+decision+'。'+report+'。\n\n**此前执行进展：**',1);f.write_text(text)
 f=PLANS/'STEP06_ONE_EPOCH_PLAN.md';text=f.read_text();lines=text.splitlines();lines.insert(4,f'**后续Dev57结果：** {result}。{decision}。详见 {report}。');f.write_text('\n'.join(lines)+'\n')
 f=OUT.parent/'README.md';text=f.read_text();text=text.replace('**当前新增：Action-1epoch的Dev57评测正在进行，基线23/57经核验复用。**',f'**当前：第7c步Dev57评测已完成。{result}。{decision}。**')
 text=text.replace('运行中：原epoch5 23/57复用；报告逐题evaluator和总体百分比',f'已完成：Action {a["success_count"]}/57；evaluator {at["overall_pass_percentage"]:.2f}%；基线23/57复用')
 text+='\n'+section;f.write_text(text)
 print('Updated rolling plans with complete per-task evaluator results and acceptance decision.')
if __name__=='__main__':main()
