"""Validate and export scores without model calls; never alter accepted labels."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import argparse, ast, csv, hashlib, json, math
from judge_protocol import validate, audit_events, command
ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads(p.read_text())
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def writecsv(p,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def narrow_read_only(code):
    """Only direct documented non-business API calls plus print/len; flag, not autocorrect."""
    try: tree=ast.parse(code)
    except SyntaxError: return False
    if not code.strip() or any(isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef,ast.Lambda,ast.Import,ast.ImportFrom)) for n in ast.walk(tree)): return False
    api_seen=False
    for n in ast.walk(tree):
        if not isinstance(n,ast.Call): continue
        name=ast.unparse(n.func)
        if name in {'print','len','str','int','float','bool','list','dict','set','tuple','sorted','sum','max','min','enumerate','range','zip'}: continue
        parts=name.split('.')
        if len(parts)!=3 or parts[0]!='apis': return False
        app,fn=parts[1:]
        if (app=='api_docs' and fn.startswith('show_')) or (app=='supervisor' and fn=='complete_task') or fn.startswith(('show_','search_')) or fn in {'login','directory_exists','file_exists','get_current_date_and_time'}:
            api_seen=True
        else: return False
    return api_seen

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--pilot',action='store_true'); ap.add_argument('--partial',action='store_true'); a=ap.parse_args()
    started=now(); manifest=read(ROOT/'manifest.json'); config=read(ROOT/'judge_config.json'); frozen=read(ROOT/'FREEZE.json')
    for name,h in frozen['files'].items(): assert sha(ROOT/name)==h,name
    samples=manifest['samples']
    if a.pilot:
        ids={s['id'] for s in read(ROOT/'review/pilot_plan.json')['samples']}; samples=[s for s in samples if s['id'] in ids]
    if a.partial: samples=[s for s in samples if (ROOT/'runs/scoring'/s['id']/'judgement.json').exists()]
    if not a.pilot and not a.partial: assert len(samples)==540 and read(ROOT/'TIMING.json').get('scoring_finished_at')
    schema=read(ROOT/'assets/output_schema_v6.json'); prompt=(ROOT/'assets/prompt_v6_en.txt').read_text(); ph=sha(ROOT/'assets/prompt_v6_en.txt')
    outcomes={s['id']:s for s in read(ROOT/'research/official_outcomes.json')['samples']}
    steps=[]; trs=[]; scores=[]; attempts=[]; flags=[]; usage=Counter(); all_pairs=set()
    counts={f'R{i}':Counter() for i in range(1,9)}; strat={o:{f'R{i}':Counter() for i in range(1,9)} for o in ['success','failure']}
    for s in samples:
        folder=ROOT/'runs/scoring'/s['id']; payload=read(ROOT/s['input']); result=read(folder/'judgement.json'); meta=read(folder/'metadata.json')
        validate(result,payload,schema)
        assert sha(Path(s['source']))==s['source_sha256']
        assert sha(ROOT/s['input'])==sha(folder/'input.json')==s['input_sha256']
        assert (folder/'request.txt').read_text()==prompt.replace('{{TRAJECTORY_JSON}}',(ROOT/s['input']).read_text())
        assert meta['input_sha256']==s['input_sha256'] and meta['source_sha256']==s['source_sha256']
        assert meta['prompt_sha256']==ph and meta['model']==config['model'] and meta['reasoning_effort']==config['reasoning_effort']
        assert set(payload)=={'trajectory_id','task','agent_instructions','reference_api_docs','steps','termination'}
        successes=[]
        for p in sorted(folder.glob('attempt_*')):
            rec=read(p/'record.json'); cmd=read(p/'command.json')
            assert cmd==command(config,folder/'empty_cwd',p/'response.json')
            ev=[json.loads(l) for l in (p/'events.jsonl').read_text().splitlines() if l.strip()]
            reported=[e.get('usage',{}) for e in ev if e.get('type')=='turn.completed']
            if reported: usage.update(reported[-1])
            attempts.append({'id':s['id'],'attempt':rec['attempt'],'status':rec['status'],'elapsed_seconds':rec['elapsed_seconds'],'category':rec.get('category'),'usage':reported[-1] if reported else None})
            if rec['status']=='valid':
                audit_events(p/'events.jsonl'); assert read(p/'response.json')==result; successes.append(rec['attempt'])
        assert successes==[meta['accepted_attempt']], (s['id'],successes)
        o=outcomes[s['id']]; own={f'R{i}':Counter() for i in range(1,9)}
        for inp,(sid,labels,reason) in zip(payload['steps'],result['steps']):
            pair=(payload['trajectory_id'],sid); assert pair not in all_pairs; all_pairs.add(pair)
            row={'trajectory_id':payload['trajectory_id'],'id':s['id'],'task_id':s['task_id'],'step_id':sid,'labels':labels,**{f'R{i+1}':v for i,v in enumerate(labels)},'reason':reason}
            steps.append(row)
            for i,v in enumerate(labels):
                key=f'R{i+1}'; counts[key][v]+=1; own[key][v]+=1; strat['success' if o['success'] else 'failure'][key][v]+=1
            if narrow_read_only(inp['code']) and labels[4]!='N': flags.append({'id':s['id'],'step_id':sid,'rubric':'R5','observed':labels[4],'expected':'N','kind':'non_business_calls_only_candidate','status':'needs_raw_review'})
            explicit_failure=inp['observation'].startswith('Execution failed.') or (not inp['code'].strip() and sid==payload['steps'][-1]['id'] and payload['termination']=='no_python_code')
            if explicit_failure and labels[0]!='F': flags.append({'id':s['id'],'step_id':sid,'rubric':'R1','observed':labels[0],'expected':'F','kind':'explicit_execution_failure','status':'needs_raw_review'})
        trs.append({'id':s['id'],'trajectory_id':payload['trajectory_id'],'task_id':s['task_id'],'steps':s['steps'],'official_success_research_only':o['success'],'termination':s['termination'],'last_R7':result['steps'][-1][1][6],'any_F_steps':sum('F' in r[1] for r in result['steps']),**{f'{k}_{v}':own[k][v] for k in own for v in 'PFUN'}})
        scores.append(result)
    expected=sum(s['steps'] for s in samples); assert len(steps)==expected
    if not a.pilot and not a.partial: assert len(steps)==9886 and len(all_pairs)==9886
    prefix='pilot_' if a.pilot else 'partial_' if a.partial else ''
    out=ROOT/'analysis'
    writecsv(out/(prefix+'step_labels.csv'),steps); writecsv(out/(prefix+'trajectory_metrics.csv'),trs)
    with (out/(prefix+'step_labels.jsonl')).open('w') as f:
        for r in steps: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    with (out/(prefix+'scored_trajectories.jsonl')).open('w') as f:
        for r in scores: f.write(json.dumps(r,ensure_ascii=False)+'\n')
    association=[]
    for k in counts:
        sf=strat['success'][k]['F']; sp=strat['success'][k]['P']; ff=strat['failure'][k]['F']; fp=strat['failure'][k]['P']
        den=math.sqrt((sp+sf)*(fp+ff)*(sp+fp)*(sf+ff))
        association.append({'rubric':k,'success_P':sp,'success_F':sf,'failure_P':fp,'failure_F':ff,'phi_pass_vs_success':(sp*ff-sf*fp)/den if den else None,'success_U':strat['success'][k]['U'],'success_N':strat['success'][k]['N'],'failure_U':strat['failure'][k]['U'],'failure_N':strat['failure'][k]['N']})
    writecsv(out/(prefix+'outcome_association.csv'),association)
    summary={'completed_at':now(),'analysis_started_at':started,'trajectories':len(samples),'steps':len(steps),'labels':len(steps)*8,'tasks':len({s['task_id'] for s in samples}),'official_successes':sum(t['official_success_research_only'] for t in trs),'counts':{k:{v:c[v] for v in 'PFUN'} for k,c in counts.items()},'counts_by_official_outcome':strat,'attempts':len(attempts),'valid_attempts':sum(r['status']=='valid' for r in attempts),'invalid_attempts':sum(r['status']!='valid' for r in attempts),'reported_usage_including_invalid':dict(usage),'mechanical_review_flags':len(flags),'model':config['model'],'reasoning_effort':config['reasoning_effort'],'prompt_sha256':ph,'note':'Official outcomes used only after scoring. Associations are descriptive, steps are correlated, no label accuracy or training-effect claim.'}
    dump(out/(prefix+'summary.json'),summary); dump(out/(prefix+'attempts.json'),attempts); dump(out/(prefix+'mechanical_review_flags.json'),flags)
    validation={'passed':True,'validated_at':now(),'trajectories':len(samples),'steps':len(steps),'labels':len(steps)*8,'source_hashes_verified':len(samples),'input_hashes_verified':len(samples),'unique_trajectory_step_pairs':len(all_pairs),'schema_and_exact_order':True,'frozen_config_and_prompt':True,'first_valid_response_only':True,'all_accepted_event_audits_passed':True,'official_outcomes_excluded_from_input':True,'scope':'Structural/provenance validation; does not assert semantic perfection.'}
    dump(out/(prefix+'validation.json'),validation)
    if not a.pilot and not a.partial:
        timing=read(ROOT/'TIMING.json'); rows='\n'.join('| '+k+' | '+' | '.join(str(counts[k][v]) for v in 'PFUN')+' |' for k in counts)
        review_path=ROOT/'review/semantic_review.json'; reviewed=review_path.exists()
        review_text='见 [语义复核](review/semantic_review.json)。' if reviewed else '语义复核尚未完成；不可把格式验收当作语义准确率。'
        report=f'''# SFT 初始模型 AppWorld 540 条轨迹逐步评分\n\n540 条轨迹、9,886 步、79,088 个 R1—R8 标签已完整覆盖，源文件哈希、输入哈希、步骤顺序和输出格式验收通过。\n\n## 数据与配置\n\n评分来源为 `2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories`：train90 epoch5 LoRA SFT 模型，每题 6 条，共 90 题。官方成功 186 条、失败 354 条，仅用于研究者选样与事后分析，不输入裁判。没有复用原始基座模型那批 540 条轨迹的标签。\n\n采用冻结英文 v6 format prompt，模型 `{config['model']}`，推理强度 `{config['reasoning_effort']}`，并发上限 8。每次输入完整轨迹，返回所有步骤的 P/F/U/N。先 8 条试评，通过后扩展；同配置试评结果计入 540 条。每条仅接受首次格式有效结果，技术/格式失败按预设规则重试，不按标签好坏重评。\n\n## 文件\n\n- [逐步标签 CSV](analysis/step_labels.csv)\n- [逐步标签 JSONL](analysis/step_labels.jsonl)\n- [完整逐轨迹评分 JSONL](analysis/scored_trajectories.jsonl)\n- [结构与来源验收](analysis/validation.json)\n- [逐轨迹指标（含研究用官方结果）](analysis/trajectory_metrics.csv)\n- [完整来源清单](manifest.json)\n- [冻结配置](judge_config.json) 与 [prompt](assets/prompt_v6_en.txt)\n\n每条请求、原始响应、事件及失败尝试保存在 `runs/scoring/<id>/`。汇总标签不静默修正；语义争议另记。\n\n## 标签分布\n\n| 维度 | P | F | U | N |\n| --- | ---: | ---: | ---: | ---: |\n{rows}\n\n## 成本与质量\n\n共 {len(attempts)} 次已记录尝试，其中 {summary['invalid_attempts']} 次无效尝试。评分阶段墙钟时间 {timing['scoring_wall_seconds']/60:.2f} 分钟，含试评、试评复核等待、排队、必要重试与验收落盘，不含输入准备及最终分析。具体起止与调用 token 记录见 TIMING.json 和 analysis/summary.json。\n\n{review_text} 机械规则产生 {len(flags)} 个待复核标记，详见 analysis/mechanical_review_flags.json；它们不是自动判定的错误总数。\n\n官方成败关联仅是描述性分析，不代表步骤标签准确率；同一轨迹的步骤不独立。全轨迹裁判可能受后续信息影响。U 不等于 F，N 不等于 P；R7=P 也可能仅表示诚实报告失败。此实验仅产出评分，没有筛选训练数据或进行 SFT/RL。\n'''
        (ROOT/'REPORT.md').write_text(report)
        dump(ROOT/'COMPLETION_CHECK.json',{'scoring_complete':True,'structural_validation_passed':True,'semantic_review_complete':reviewed,'trajectories':len(samples),'steps':len(steps),'labels':len(steps)*8,'completed_at':now()})
    print(json.dumps({'prefix':prefix,'trajectories':len(samples),'steps':len(steps),'invalid_attempts':summary['invalid_attempts'],'mechanical_flags':flags},ensure_ascii=False))
if __name__=='__main__': main()
