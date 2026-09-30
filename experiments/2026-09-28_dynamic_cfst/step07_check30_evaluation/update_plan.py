"""Update the rolling plan only from fully validated check30 results."""
from pathlib import Path
import json,re
S=Path(__file__).resolve().parent
ROOT=S.parents[2]
s=json.loads((S/'summary.json').read_text());v=json.loads((S/'validation.json').read_text())
assert s['status']=='completed' and v['passed']
models=s['models'];paired=s['paired_comparisons'];candidate=s['selection']['selected_candidate']
report=str(S/'README.md');matrix=str(S/'task_comparison.csv')
counts='、'.join(f"{b} {models[b]['success_count']}/30" for b in ['CFST-state','CFST-Action','CFST-Mixed'])
result=f'检查30题已完成：原epoch5为17/30（复用），{counts}。'
decision=f'按冻结规则选出{candidate}作为Dev57候选，尚未接受为新学生。' if candidate else '三个分支都没有正净改善，按原计划保留原epoch5，本轮不进入Dev57或来源60题刷新。'
table=['| 模型 | 官方成功 | 新增成功 | 退步 | 净改善 |','| --- | ---: | ---: | ---: | ---: |','| 原epoch5（复用） | 17/30 | — | — | — |']
for b,r in paired.items():table.append(f"| {b} | {r['success_count']}/30 | {r['gained_success_count']} | {r['regression_count']} | {r['net_gain']:+d} |")
record='\n'.join(['**2026-09-29实际结果：** '+result+' '+decision,'',*table,'','**本步做了什么：** 原模型的adapter、提示词、agent实现和180个逐题证据文件核验后复用；三个新分支分别从干净初始环境完成全部30题，共新增90条轨迹，保存完整交互与官方评分。未调用教师、未生成检查题训练答案、未更新模型、未给检查题重新划分能力类别。','', '**运行异常处理：** State在afc0fce_3第4步触发AppWorld日志序列化异常。仅修日志，原学生4个响应精确重放后从第5步继续，历史及前3步环境返回一致，仍受总50步限制。原中断证据和修复说明完整留档。', '', '**能说明什么：** '+('本轮检查题出现了正向净收益，可以进入独立的接受检查；这尚不能证明能力分类合理或Dynamic CFST已有效。' if candidate else '本次20条修复加当前短训设置没有带来检查题的净收益。训练loss降低不能替代任务成功率；也不能仅凭这一轮断定问题来自分类、数据规模或学习率中的哪一项。')+' 检查30题曾参与旧train90 SFT，只有10个任务族，且只有一套训练和推理种子。等监督tokens不等于等更新步数或等算力。','',f'**产物：** [第7.1步总报告]({report}) · [逐题四模型比较]({matrix}) · [完整性核验]({S / "validation.json"})。','', '**当前决定：** '+decision+' 本次请求仅执行7.1；Dev57未运行。'])
p=ROOT/'plans/2026-09-28_capability_frontier/METHOD_PROPOSAL.md';t=p.read_text()
t=re.sub(r'^\*\*更新日期：.*?\*\*$', '**更新日期：2026-09-29。第1–6步及第7.1步已完成。'+result+' '+decision+'**',t,count=1,flags=re.M)
t=t.replace('当前已完成三个纠错短训分支，正在运行检查30题。Dev57尚未运行，完整评测前不作CFST提高任务成功率的结论。','当前三个纠错短训分支及检查30题评测已经完成。'+result+' '+decision)
t=re.sub(r'^\| 第7步：检查30题并评测Dev57 \|.*$', '| 第7步：检查30题并评测Dev57 | 7.1已完成；'+('7.2待执行' if candidate else '7.2无合格候选，不执行')+' | 比较新增成功、退步与净收益 |',t,flags=re.M)
if not candidate:t=re.sub(r'^\| 第8步：接受更新并重新采样 \|.*$', '| 第8步：接受更新并重新采样 | 未触发：保留原模型 | 本轮没有可接受的模型更新 |',t,flags=re.M)
t=re.sub(r'^\*\*2026-09-29执行记录：\*\*.*$',record,t,count=1,flags=re.M)
t=t.replace('这里尚未运行检查30题或Dev57，不能把训练loss下降表述为任务能力提升。','这里记录的是训练完成时的核验；任务性能结果见下方第7.1步，不能把训练loss下降表述为任务能力提升。')
t=t.replace('| 检查30题评测 | 用同一协议运行原模型和三个分支，生成逐题新增成功/退步表 |','| 检查30题评测 | 已完成：原模型复用，三个分支各30题；逐题新增成功/退步表已保存 |')
t=re.sub(r'^\*\*当前状态：第1–6步完成。.*$', '**当前状态：第1–6步及第7.1步完成。'+result+' '+decision+' Dev57未运行，没有重新训练或刷新来源轨迹。**',t,flags=re.M)
p.write_text(t)
p=ROOT/'plans/2026-09-28_capability_frontier/DYNAMIC_CFST_OVERVIEW.md';t=p.read_text()
t=t.replace('| 步骤7 | 检查30题选择 + Dev57接受检查 | 下一项：测量其他任务收益与完整任务退步 |','| 步骤7 | 检查30题选择 + Dev57接受检查 | 7.1已完成；'+('选出'+candidate+'，Dev57未执行' if candidate else '无正净改善分支，保留原模型')+' |')
anchor='第一轮只跑一个训练随机种子和一套预先固定参数。'
assert anchor in t
t=t.replace(anchor,f'**2026-09-29第一轮实测：** {result} {decision} [逐题证据与报告]({report})。本轮没有给检查题生成教师答案，也没有给检查题精细重分类；这些结果用于判断当前更新是否值得继续，不能单独证明分类或完整动态算法有效。\n\n'+anchor,1)
p.write_text(t)
p=S.parent/'README.md';t=p.read_text();t=t.replace('| 第七步7.1：检查30题 | step07_check30_evaluation/ | 运行中：基线复用17/30，三个新分支评测中 |',f'| 第七步7.1：检查30题 | step07_check30_evaluation/ | 已完成：基线17/30；{counts} |');t+='\n## 第七步7.1：四模型检查30题\n\n'+result+' '+decision+'\n\n'+ '\n'.join(table)+f'\n\n三个新分支共90条完整轨迹及官方评分已归档；基线复用经核验的旧结果。未调用教师、未生成训练答案、未训练、未运行Dev57。日志异常的精确重放恢复及全部协议核验见[第7.1步报告]({report})。\n';p.write_text(t)
print(result,decision)
