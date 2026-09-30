"""Update rolling plans only after all official check30 results have passed audit."""
from pathlib import Path
import json

OUT=Path(__file__).resolve().parent
ROOT=OUT.parents[2]
PLAN=ROOT/'plans/2026-09-28_capability_frontier'
BRANCHES=['CFST-state','CFST-Action','CFST-Mixed']

def main():
    s=json.loads((OUT/'summary.json').read_text());v=json.loads((OUT/'validation.json').read_text())
    assert s['status']=='completed' and v['passed']
    counts=[s['models'][b]['success_count'] for b in BRANCHES]
    selected=s['selection']['selected_candidate']
    count_text=f'State {counts[0]}/30、Action {counts[1]}/30、Mixed {counts[2]}/30'
    report=f'[第7b步总报告]({OUT}/README.md)'
    decision=(f'按冻结规则选择{selected}-1epoch作为Dev57候选，尚未接受为新学生；Dev57未运行。' if selected else '三支均无正净收益，保留原epoch5；不进入Dev57或来源侧刷新。')
    table='| 1epoch模型 | 官方成功 | 新增成功 | 退步 | 净改善 | 旧版成功数 | 相对旧版变化 |\n| --- | ---: | ---: | ---: | ---: | ---: | ---: |\n'
    for b in BRANCHES:
        p=s['paired_comparisons'][b];old=s['comparison_vs_previous'][b]
        table+=f"| {b} | {p['success_count']}/30 | {p['gained_success_count']} | {p['regression_count']} | {p['net_gain']:+d} | {old['previous_success_count']}/30 | {old['net_change']:+d} |\n"
    section=f'''## 第7b步实际结果：1epoch模型在冻结检查30题上评测（已完成）

原epoch5经核验复用，仍为17/30。三支第6b步新adapter各从初始环境完成同一30题，完整保存90条新轨迹与官方评分。没有Codex动作、没有生成训练答案、没有新训练，也没有运行Dev57。

{table}
新增成功、退步和净改善均相对原epoch5；最后两列与旧8,000监督tokens版本比较。**当前决定：{decision}**

评测协议与第1步、旧第7步相同：temperature=0、seed=100、32,000窗口、每次3,000输出tokens、每题50步、无reasoning parser。首条模型输入、冻结题目清单、运行器、配置、adapter哈希与官方评分一致性已核验，{v['checks_passed']}项检查通过。沿用旧版已验证的日志序列化修复，只影响日志落盘，本次没有前缀重放。完整证据见 {report}。

**能说明什么：** 这次直接检验了“每条修复只学一次”的训练尝试。先看相对旧版是否改善，再看是否超过原epoch5；不能把超过旧版自动视为模型更新成功。单次结果仍不能单独证明能力分类合理或锁定退步原因。三支训练量自然不同，同一检查30题已参与这次方案修订，属于开发实验。

**下一步边界：** {decision} 本次到检查30题结果与候选判断结束，不自动加训、更改超参数、补教师答案或启动其他任务集。

'''
    p=PLAN/'METHOD_PROPOSAL.md';text=p.read_text();lines=text.splitlines()
    lines[2]=f'**更新日期：2026-09-29。第6b步1epoch训练及第7b步冻结检查30题评测均已完成：原epoch5 17/30；{count_text}。{decision}旧训练与旧评测结果完整保留。**'
    text='\n'.join(lines)+'\n'
    text=text.replace('当前已启动同协议检查30题，第7b步运行中。',f'第7b步已完成，{count_text}。{decision}')
    text=text.replace('旧版7.1已完成；1epoch版本第7b步运行中','旧版及1epoch版检查30题均完成；Dev57未运行')
    marker='## 旧第6步结果：按约8,000监督tokens训练（保留对照）'
    text=text.replace(marker,section+marker,1)
    text=text.replace('第6b步1epoch版本现已完成训练，尚未评测；Dev57仍未运行。',f'第6b步1epoch版本现已完成第7b步检查30题，结果见上文；Dev57仍未运行。')
    text=text.replace('现已按后续执行指令完成1epoch训练，本次不启动评测。','现已按后续执行指令完成1epoch训练和第7b步冻结检查30题评测，本次不启动Dev57。')
    text=text.replace('旧版已完成；未来1epoch三支继续使用同一冻结清单与原协议，另存结果','旧版与1epoch版均完成；相同冻结清单与协议，结果分别保存')
    text=text.replace('**本轮没有合格候选，未执行本节。** 以下保留原接受规则，供后续方案参考。',f'**旧版无合格候选；第7b步结果：{decision}** 以下保留原接受规则。')
    last='**当前状态：第7b步运行中，见 [第7b步评测目录]('+str(OUT)+')。三支1epoch模型按原协议从头完成同一冻结30题；结果待全部完成后核验。当前学生仍为原epoch5，不提前选择候选。**'
    assert last in text
    text=text.replace(last,f'**当前状态：第7b步90条新轨迹与官方评分已核验，{count_text}。{decision}详见 {report}。**')
    p.write_text(text)
    p=PLAN/'DYNAMIC_CFST_OVERVIEW.md';text=p.read_text()
    text=text.replace('第7b步冻结检查30题评测现已启动，结果待核验；当前学生仍为原epoch5。',f'第7b步已完成：{count_text}，基线17/30。{decision}')
    text=text.replace('新的1epoch方案已训练并核验，尚未评测。',f'新的1epoch方案也已完成检查30题，结果为{count_text}。{decision}')
    text=text.replace('1epoch版本第7b步正在运行，协议保持不变',f'1epoch第7b步完成：{counts[0]}/{counts[1]}/{counts[2]}题成功；Dev57未运行')
    text=text.replace('后续同样完整报告各支评测结果','现已完整报告各支评测结果')
    p.write_text(text)
    p=PLAN/'STEP06_ONE_EPOCH_PLAN.md';text=p.read_text()
    old='**状态：已于2026-09-29按计划完成三支训练及282项核验，未启动评测。**'
    new=f'**状态：第6b步训练及282项核验已完成；后续按新执行指令完成第7b步检查30题，{count_text}。**'
    assert old in text;text=text.replace(old,new,1)
    text=text.replace('## 6. 接下来怎样判断（尚未执行评测）',f'## 6. 检查30题已执行，结果与后续判断\n\n后续按用户执行指令完成评测，结果见 {report}。{decision}下面保留训练前确定的比较规则。')
    p.write_text(text)
    p=PLAN/'IMPLEMENTATION_NOTES.md';text=p.read_text().replace('现已完成训练及核验，未评测，见','现已完成训练及核验，后续第7b步检查30题也已完成，结果见滚动待办；训练产物见');p.write_text(text)
    p=PLAN/'README.md';text=p.read_text().replace('第6b步三个分支各训练1轮已完成并通过核验，尚未重新评测。',f'第6b步三个分支各训练1轮及第7b步检查30题均已完成，{count_text}。{decision}');p.write_text(text)
    p=OUT.parent/'README.md';text=p.read_text()
    text=text.replace('第7b步冻结检查30题评测正在运行，见 [第7b步评测目录]('+str(OUT)+')。本次不运行Dev57。',f'第7b步检查30题也已完成，{count_text}。{decision}见 {report}。')
    text=text.replace('运行中：基线17/30复用，三个新分支各从头完成30题',f'已完成：基线17/30；1epoch为{counts[0]}/{counts[1]}/{counts[2]}题成功，90条新轨迹核验通过')
    text+='\n'+section
    p.write_text(text)
    print('Rolling plans updated from validated official results.')

if __name__=='__main__':main()
