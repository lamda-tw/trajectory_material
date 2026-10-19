"""Post-hoc semantic taxonomy and rubric exposure, using saved data only.

Taxonomy is manually audited and versioned in evaluator_type_mapping.csv.
No model inference, causal fitting, or evaluator reruns.
"""
import ast
import csv
import hashlib
import json
import statistics as st
from collections import Counter, defaultdict
from pathlib import Path

R = Path(__file__).resolve().parents[1]
O = R / 'analysis'
NAMES = {
    'target_set_mapping': '完整名单与对应关系',
    'local_content_identity': '具体内容与对象',
    'model_scope': '改动的数据类型',
    'record_counts': '新增、修改、删除的数量',
    'selection_constraints': '操作对象是否符合条件',
    'preservation': '不该改的内容是否保留',
    'answer_null': '按要求提交空答案',
    'answer_value': '实际答案是否正确',
}


def read(path):
    return json.loads(path.read_text())


def csv_read(name):
    return list(csv.DictReader((O / name).open()))


def save_csv(name, rows):
    with (O / name).open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)


def save(name, data):
    (O / name).write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def main():
    cfg = read(R/'config/training.json')
    seeds, arms = cfg['seeds'], cfg['arms']
    ground = Path(read(R/'config/evaluation.json')['paths']['appworld_data'])/'tasks'
    mapping = {(x['family'], x['requirement']): x['category'] for x in csv_read('evaluator_type_mapping.csv')}
    assert len(mapping) == 97
    checks = csv_read('evaluator_checks.csv')
    assert set(mapping) == {(x['family'], x['requirement']) for x in checks}
    answers = {}
    for task in sorted({x['task_id'] for x in checks}):
        p = ground/task/'ground_truth/answer.json'
        answers[task] = {'is_null': read(p) is None, 'source':str(p), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
    save('evaluator_answer_types.json', answers)
    for x in checks:
        x['passed'] = int(x['passed'])
        x['category'] = mapping[x['family'], x['requirement']]
        if x['category'] == 'answer':
            x['category'] = 'answer_null' if answers[x['task_id']]['is_null'] else 'answer_value'
    baseline = {(x['seed'],x['task_id'],x['requirement']):x['passed'] for x in checks if x['arm']=='random'}
    rows = []
    for cat in NAMES:
        for arm in arms:
            group = [x for x in checks if x['category']==cat and x['arm']==arm]
            gain = sum(x['passed']>baseline[x['seed'],x['task_id'],x['requirement']] for x in group)
            loss = sum(x['passed']<baseline[x['seed'],x['task_id'],x['requirement']] for x in group)
            b = sum(baseline[x['seed'],x['task_id'],x['requirement']] for x in group)
            row = dict(category=cat,arm=arm,checks=len(group),families=len({x['family'] for x in group}),passes=sum(x['passed'] for x in group),random_passes=b,gains=gain,losses=loss,net=gain-loss,delta_pp=100*(gain-loss)/len(group))
            for seed in seeds:
                xx=[x for x in group if x['seed']==str(seed)]
                row[f'net_{seed}']=sum(x['passed']-baseline[x['seed'],x['task_id'],x['requirement']] for x in xx)
            xx=[x for x in group if x['family']!='d4e9306']
            row['without_d4e9306_checks']=len(xx)
            row['without_d4e9306_net']=sum(x['passed']-baseline[x['seed'],x['task_id'],x['requirement']] for x in xx)
            rows.append(row)
    assert sum(x['net'] for x in rows if x['arm']=='zerofail3')==98
    assert sum(x['checks'] for x in rows if x['arm']=='zerofail3')==873
    save_csv('evaluator_type_results.csv',rows)

    inventory=[json.loads(l) for l in (R/'data/step_inventory.jsonl').read_text().splitlines()]
    index={x['id']:x for x in inventory}
    assert len(index)==11254
    p3=[x for x in inventory if x['P']>=3]
    z=[x for x in p3 if x['F']==0]
    rejected=[x for x in p3 if x['F']>0]
    assert len(z)==1710
    eligibility=[]
    for i in range(8):
        eligibility.append(dict(rubric=f'R{i+1}',P3_with_F=sum(x['labels'][i]=='F' for x in rejected),exclusive_F=sum(x['labels'][i]=='F' and x['F']==1 for x in rejected)))
    save_csv('rubric_filter_eligibility.csv',eligibility)
    filter_summary=dict(P_ge_3=len(p3),selected=len(z),excluded=len(rejected),excluded_R6_or_R8=sum(x['labels'][5]=='F' or x['labels'][7]=='F' for x in rejected),excluded_R6_and_R8=sum(x['labels'][5]=='F' and x['labels'][7]=='F' for x in rejected))
    save('rubric_filter_summary.json',filter_summary)

    selections={}
    for arm in arms:
        for seed in seeds:
            ss=[json.loads(l) for l in (R/f'data/{arm}/seed_{seed}/selection.jsonl').read_text().splitlines()]
            assert len(ss)==1710 and all(x==index[x['id']] for x in ss)
            selections[arm,seed]=ss
    assert all({x['id'] for x in selections['zerofail3',seed]}=={x['id'] for x in z} for seed in seeds)
    train_families={x['task_id'].rsplit('_',1)[0] for x in inventory}
    assert not train_families & {x['family'] for x in checks}
    # Read each source once, discard token arrays immediately; verify source hashes.
    by_source=defaultdict(list)
    for x in inventory:by_source[x['source']].append(x)
    hashes=read(R/'references/source_hashes.json')
    features={}
    for path,ss in by_source.items():
        raw=Path(path).read_bytes()
        assert hashlib.sha256(raw).hexdigest()==hashes[path]
        data=json.loads(raw)
        for x in ss:
            step=data['steps'][x['step']-1]
            assert step['step']==x['step']
            code=step['code']
            features[x['id']]=dict(doc='apis.api_docs.' in code,complete='apis.supervisor.complete_task(' in code)
    exposure=[]
    for (arm,seed),ss in selections.items():
        for i in range(8):
            labels=Counter(x['labels'][i] for x in ss)
            exposure.append(dict(arm=arm,seed=seed,rubric=f'R{i+1}',**{lab:labels[lab] for lab in 'PFUN'},P_doc=sum(x['labels'][i]=='P' and features[x['id']]['doc'] for x in ss),P_non_doc=sum(x['labels'][i]=='P' and not features[x['id']]['doc'] for x in ss)))
    save_csv('rubric_exposure_by_seed.csv',exposure)
    special={}
    for arm in arms:
        ss=[x for seed in seeds for x in selections[arm,seed]]
        special[arm]=dict(steps=len(ss),doc=sum(features[x['id']]['doc'] for x in ss),complete=sum(features[x['id']]['complete'] for x in ss),R5_U=sum(x['labels'][4]=='U' for x in ss),R7_U=sum(x['labels'][6]=='U' for x in ss))
    save('rubric_action_overlap.json',special)
    # Restrict this post-hoc trace audit to the already identified gain family.
    trace_rows=[]
    for arm in ['random','zerofail3']:
        for seed in seeds:
            folder=R/f'evaluation/{arm}/seed_{seed}/epoch_01'
            summary={x['task_id']:x for x in read(folder/'SUMMARY.json')['results']}
            for task in ['d4e9306_1','d4e9306_2','d4e9306_3']:
                path=folder/'trajectories'/f'{task}.json'
                assert hashlib.sha256(path.read_bytes()).hexdigest()==summary[task]['sha256']
                data=read(path)
                found=defaultdict(list)
                for step in data['steps']:
                    try: tree=ast.parse(step['code'])
                    except SyntaxError: continue
                    if step['observation'].startswith('Execution failed.'): continue
                    for node in ast.walk(tree):
                        if not isinstance(node,(ast.For,ast.While)): continue
                        # An explicit page-index increment and API call inside a loop.
                        nodes=list(ast.walk(node))
                        advances=any(isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id=='page_index' and isinstance(n.op,ast.Add) for n in nodes)
                        if not advances: continue
                        for n in nodes:
                            if not isinstance(n,ast.Call): continue
                            name=ast.unparse(n.func)
                            if name in ['apis.spotify.show_liked_songs','apis.spotify.show_liked_albums'] and any(k.arg=='page_index' for k in n.keywords):
                                found[name].append(step['step'])
                trace_rows.append(dict(arm=arm,seed=seed,task_id=task,success=data['official_evaluation']['success'],song_loop_steps=found['apis.spotify.show_liked_songs'],album_loop_steps=found['apis.spotify.show_liked_albums'],source=str(path.relative_to(R))))
    save('evaluator_d4e9306_pagination.json',trace_rows)
    anchors=[dict(id=x['id'],labels=x['labels'],source=x['source'],step=x['step']) for x in z if x['labels'][4]=='P' or x['labels'][6]=='P']
    save('rubric_sparse_action_examples.json',anchors)
    (O/'evaluator_rubric_report_section.md').write_text(render(rows,exposure,eligibility,filter_summary))
    print(json.dumps({'types':[x for x in rows if x['arm']=='zerofail3'],'filter':filter_summary,'eligibility':eligibility,'actions':special},ensure_ascii=False,indent=2))


def render(rows, exposure, eligibility, filter_summary):
    z=[x for x in rows if x['arm']=='zerofail3']
    lines=['''## 1.2 ZeroFail3 改善了哪些检查，与哪些 rubric 分项有关（2026-10-19 补充）

### 各类检查是什么意思，分别改善了多少

**evaluator 检查就是任务结束后的“验收清单”。** 一道题通常有多项要求，通过其中几项，不代表整道题完成了。报告中的 `requirement` 就是一条验收要求；同一类任务的不同题目合称一个“任务家族”。例如“关注所有已点赞歌曲和专辑的艺术家”，可以分别检查歌曲中的艺术家是否都关注了、专辑中的是否都关注了、是否多关注了其他人、是否取消了原来的关注。

下面这些分类是为了整理结果而起的名字，不是 AppWorld 官方维度。分类名称已改成直白表述；原有分类边界、统计和结论不变，CSV 中用于复现的英文分类标识也不变。

| 更直白的分类名称 | 实际在检查什么 | 通俗例子 |
| --- | --- | --- |
| 完整名单与对应关系 | 该处理的对象是否全部处理了；要求精确一致时，名单及一一对应关系是否正确。 | 应关注 A、B、C，是否一个不漏？如果要求名单完全一致，是否还多关注了 D？文件备份时，每个文件名是否对应正确内容？ |
| 具体内容与对象 | 某个具体操作的内容、数值和对象是否正确。 | 短信文本、转账金额、收款人、播放列表名称是否正确？ |
| 改动的数据类型 | 实际改动的是不是任务要求的那些种类的数据。 | 创建播放列表时，是否改动了“播放列表”和“列表中的歌曲”这两类数据？原名称中的“模型”指数据库里的数据类型，不是 AI 模型。 |
| 新增、修改、删除的数量 | 实际新增、修改、删除了多少条数据，是否符合要求。 | 是否恰好新增一笔转账？是否只创建了一个播放列表？ |
| 操作对象是否符合条件 | 已经操作的对象是否都属于允许范围；这本身不检查有没有漏掉其他对象。 | 下载的歌曲是否都属于已点赞歌曲？有没有下载不符合条件的歌？ |
| 不该改的内容是否保留 | 原有内容、记录或其他字段，有没有被不必要地删除或改动。 | 添加关注时有没有取消旧关注？修改播放位置时有没有顺便改掉其他设置？ |
| 按要求提交空答案 | 不需要文字或数值答案的任务，是否按要求提交了空值 `null`。 | “关注这些艺术家”要求实际操作，通常不需要回答一个数值。空答案正确不代表关注操作正确。 |
| 实际答案是否正确 | 任务要求回答问题时，答案本身是否正确。 | “一共有多少首歌？”如果正确答案是 20，是否回答了 20？ |

**“有没有做全”和“做的对象是否符合条件”是两件事。** 假设任务要求下载全部已点赞歌曲，应该下载 A、B、C：

- 只下载 A、B：下载的都符合条件，但漏了 C，所以“操作对象是否符合条件”可以通过，“完整名单”检查不能通过。
- 下载 A、B、C、D，而 D 没有被点赞：该下载的都下载了，但多下载了不符合条件的 D，所以“操作对象是否符合条件”不能通过；如果名单检查要求完全一致，也不能通过。

“改动的数据类型”则是更粗的一层检查。例如确实新增了转账记录，这一项可能通过，但收款人、金额仍可能错误，要靠其他检查判断。以上例子用于说明各类要求的区别，不是新增实验结果。

依据官方要求，人工将 97 条“任务家族 × 验收要求”归为互斥类型，完整对应关系保存在 [分类表](analysis/evaluator_type_mapping.csv)。这是事后描述性分类，未用结果大小决定单条检查的归类。一条检查同时包含几种要求时，按主要求归类：必须新增／修改一定记录数归“新增、修改、删除的数量”，只限制不能删除／改变其他字段归“不该改的内容是否保留”。分类边界会影响分组数字，逐条验收结果仍是核查依据。

`answers match`（答案是否匹配）另据全部 57 题的 `ground_truth/answer.json` 拆为“按要求提交空答案”和“实际答案是否正确”；只读取既有评测定义做解释，未将这些答案用于训练或重跑模型。下表分母为三个 seed（使用不同随机种子的三次运行）的检查次数，按检查加权；不是前节的逐题 Macro。

**表格里的“净增”不是多完成了多少道题。** 它等于“Random 没通过、ZeroFail3 通过”的检查次数，减去“Random 通过、ZeroFail3 没通过”的检查次数。例如第一类新增通过 39 次、丢失通过 8 次，所以净增 31 次。`pp` 表示百分点；各行净增之和仍为 +98，同一道题的多个检查互相关联，不能视为 98 个独立能力增益。

| 检查类型 | Random 通过 | ZeroFail3 通过 | 通过率差 | 新增／丢失 | 净增 | 三个 seed 净增（15/16/17） |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |''']
    for x in z:
        lines.append(f"| {NAMES[x['category']]} | {x['random_passes']}/{x['checks']} | {x['passes']}/{x['checks']} | {x['delta_pp']:+.2f} pp | {x['gains']} / {x['losses']} | {x['net']:+d} | {x['net_20261015']:+d} / {x['net_20261016']:+d} / {x['net_20261017']:+d} |")
    lines+=['''
**最明确的改善是把需要处理的名单做完整，以及把具体内容和对象做对，但改善的广度与稳定性不同。**

- 完整名单与对应关系净增 31 条，占全部净增的 31.6%，三个 seed 都为正。然而 d4e9306 的“歌曲艺术家覆盖、专辑艺术家覆盖、关注集合等于二者并集”三条检查就贡献 +24，占此类净增 77.4%。去掉该家族后，此类只净增 7/153（+4.58 pp），不支持泛化为“全面解决了集合覆盖”。下载歌曲完整集合、关注艺术家的全部歌曲、通知接收者全集等检查，在 ZeroFail3 中仍分别是 0/9。
- 具体内容与对象净增 21 条，分布于短信文本、交易金额与隐私、播放列表名称与关联、播放游标／歌曲身份等要求；但三个 seed 是 +13、−5、+13，并非稳定逐 seed 改善。改动的数据类型检查 +13、新增修改删除数量检查 +7 表明更多运行触及所需操作，但它们不保证对象范围完整。例如 0d8a4ee 的短信文本和改动的数据类型检查各从 1/9 到 6/9，精确接收者集合仍是 0/9；4fab96f 的改动的数据类型检查到 2/9，接收者、消息、payment_request_id 集合与映射仍全部 0/9。
- “操作对象是否符合条件”检查反而净减 4 条：下载歌曲是否属于已点赞／曲库范围、点赞歌曲是否来自已关注艺术家等仍有退化。“不该改的内容是否保留”类仅 +4，且 Random 已是 162/180（90%）；不能据其高通过率推出更强业务执行能力，其中多个无删除检查在没有完成业务时也可通过。
- 答案检查的净增 26 条中，21 条来自期望 `null` 的任务，实质答案只贡献 +5。`null` 匹配是答案字段要求，不证明业务终态正确，也不能解释为算术／问答推理普遍变强；例如 4fab96f 的答案通过从 1/9 到 5/9，但上述业务集合检查仍为零。

### 训练选样中发生了什么

下表直接使用原始 v6 标签与实际选样清单。Random 的 P/F 是三个 seed 每次 1,710 步的均值；ZeroFail3 使用同一 1,710 步全集，所有分项 F 都为 0。P 表示当前步骤满足局部要求，N 表示不适用，U 表示证据不足，不能把 N/U 当作 P。最后两列是在固定 **P≥3** 的 4,888 步中分析零 F 门槛：共排除 3,178 步，“含该 F”可重叠，“仅该项 F”表示若只放宽这一项禁令会增加的候选数；它们不是训练后的因果贡献。

| Rubric 分项 | Random P | Random F | ZeroFail3 P | 被排除步中含该 F | 仅该项 F |
| --- | ---: | ---: | ---: | ---: | ---: |''']
    rubric_names=['R1 执行有效性','R2 证据与覆盖','R3 状态与数据忠实性','R4 决策逻辑与计算','R5 动作与实际效果','R6 反馈与恢复','R7 终止与交付','R8 授权与交互协议']
    for i,name in enumerate(rubric_names,1):
        rr=[x for x in exposure if x['arm']=='random' and x['rubric']==f'R{i}']
        zz=[x for x in exposure if x['arm']=='zerofail3' and x['rubric']==f'R{i}']
        e=eligibility[i-1]
        lines.append(f"| {name} | {st.mean(x['P'] for x in rr):.1f} | {st.mean(x['F'] for x in rr):.1f} | {zz[0]['P']} | {e['P3_with_F']} | {e['exclusive_F']} |")
    lines+=['''
**直接支持的选择机制：零 F 门槛主要排除了 R8/R6 违规，而非只增加正向标签。** 在这 3,178 个已达 P≥3 但被排除的步骤中，2,910（91.6%）含 R6 或 R8 的 F，其中 320 同时含二者。只含 R8 的 F 有 1,268 步，只含 R6 的 F 有 675 步。依据 [原始评分定义](config/scoring_prompt_v6_en_format.txt)，R8 要求使用 API 前查看完整规格、遵守代码块等交互约束；R6 针对已有错误、矛盾、无效结果及重复操作。这里统计的是标签覆盖，不把所有 R8=F 等同于未查文档，也不把所有 R6=P 等同于成功修复执行错误。原始全部候选中 P<3 的排除不属于此表分析范围。

**R2/R3 正例增多主要伴随文档步骤增多，不能直接解释成更多业务覆盖训练。** ZeroFail3 的 R2=P 为 1,568 步，其中 1,061（67.7%）包含 `apis.api_docs.`；不含文档查询的 R2=P 只有 507 步，反而低于 Random 的平均 558 步。R3=P 的非文档步骤也从平均 776.7 降到 615。R6=P 的 945 步中有 577（61.1%）含文档查询，非文档部分 368 步也低于 Random 的 429。这里只按代码是否包含文档调用划分，一步可以同时做其他动作；不能把非文档部分直接命名为业务读取或错误恢复。结果说明 P 标签增量与动作分布高度重叠，而非各维度独立加强。

### 哪些关联有证据，哪些仍只是机制假设

1. **R2（覆盖）与最大集合收益有具体行为桥梁，R8/R6 是相容的前置机制。** 对 d4e9306 全部 18 条 Random/ZeroFail3 轨迹核对：ZeroFail3 的 8/9 条轨迹出现了成功执行的歌曲及专辑分页循环，并且这 8 条均通过全部三个覆盖／集合检查；Random 0/9 出现这种显式分页循环，三个检查也均为 0/9。这里的自动检测只识别循环内使用 `page_index` 并递增的两个 liked API，详细步骤号见 [轨迹核查](analysis/evaluator_d4e9306_pagination.json)，不把未检测到等同于所有可能实现都未分页；有些循环有 10 页上限，不能据此推断普遍覆盖任意长度列表。结合原报告同题案例，支持“前置获取与局部推进改善，伴随更完整的最终对象集合”。训练中 R8/R6 违规减少、评测中执行错误和重复减少与此路径相容，但没有定位到哪个分项单独导致分页行为。
2. **R3/R4/R5 与内容、身份、范围要求在语义上相关，结果却不一致。** 具体内容与对象类改善，而“操作对象是否符合条件”类退化；R4=P 虽从 57.3 升至 98，只有 5.7% 的 ZeroFail3 步骤，不能推出复杂决策、筛选规则已普遍改善。R5=P 仅 4 步，少于 Random 的 14.7；这 4 步中包含创建播放列表、两步关注艺术家和更新笔记（[来源索引](analysis/rubric_sparse_action_examples.json)）。因此没有“大量正确写入正例导致提升”的证据，但也不能说没有同类业务动作监督：最大的艺术家关注收益确有少量相关目标动作，尚无法排除它们的作用。
3. **R7 的正例增加不是答案检查改善的解释。** ZeroFail3 的 R7=P 仅 1 步，Random 平均为 5 步；直接调用 `complete_task` 的训练目标从 Random 平均 56 步变为 0。答案检查仍净增 26，其中 21 是期望 null。该结果与更顺畅的推进带来更多有效提交相容，但不能归因为更多终止正例或更强实质答案推理。
4. **其他策略提供了反例，不能用单项 P 的数量排序收益。** Net3/Pass4 的 R2=P 平均分别为 1,614.7/1,649.7，都高于 ZeroFail3 的 1,568；R3/R4/R5 正例也更多。但两组在完整名单与对应关系类仅相对 Random 净增 −3/+5，远低于 ZeroFail3 的 +31。两组仍平均保留 R6=F 的 278.3/358.3 步和 R8=F 的 428.7/498.7 步。这支持关注“允许局部违规被正分抵消”这一选择机制，但不能排除长度、动作覆盖或其他分项共同变化的影响。

因此目前最有证据的表述是：**ZeroFail3 在本次实验中偏向无已知违规的、可执行的前置信息获取与局部推进；结果上最突出的收益是一个家族的完整集合覆盖，以及多个家族的局部内容正确性。它没有显示对对象筛选范围、复杂集合任务、实质答案或所有业务副作用的全面改善。** 训练任务家族与 DEV 家族已核验无交集；DEV 没有 R1–R8 逐步骤评分，本节不把测试检查反推成 rubric 标签。三个 seed 共享 ZeroFail3 全集，且规则同时改变各分项、动作与长度分布，既无单维干预，也无共同状态上的动作比较，故不能估计“R8／R6 贡献了多少个百分点”或声称 R2 导致了 +31 条检查。放宽单维后的候选增量只用于说明筛选机制，未作为新增训练实验运行。

复现与证据：[类型统计（含全部策略、逐 seed、去掉 d4e9306）](analysis/evaluator_type_results.csv)、[逐 seed rubric 暴露与文档重叠](analysis/rubric_exposure_by_seed.csv)、[筛选门槛统计](analysis/rubric_filter_summary.json)、[逐维排除计数](analysis/rubric_filter_eligibility.csv)、[答案类型来源及哈希](analysis/evaluator_answer_types.json)、[分析脚本](scripts/analyze_evaluator_rubric_links.py)。运行顺序为 `python scripts/analyze_evaluators.py` → `python scripts/analyze_evaluator_rubric_links.py` → `python scripts/write_final_report.py`，工作目录为本实验目录。全部是本地 CPU 事后分析。
''']
    return '\n'.join(lines)


if __name__=='__main__':main()

