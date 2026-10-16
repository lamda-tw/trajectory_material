"""Finalize independent scoring deliverables after structural and semantic review."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import json, hashlib
ROOT=Path(__file__).resolve().parents[1]
def read(p): return json.loads(p.read_text())
def dump(p,x): p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
v=read(ROOT/'analysis/validation.json'); s=read(ROOT/'analysis/summary.json'); review=read(ROOT/'review/semantic_review.json'); timing=read(ROOT/'TIMING.json')
assert v['passed'] and v['trajectories']==540 and v['steps']==9886 and v['labels']==79088
assert review['complete']
manifest=read(ROOT/'manifest.json'); cfg=read(ROOT/'judge_config.json')
outputs=['analysis/step_labels.csv','analysis/step_labels.jsonl','analysis/scored_trajectories.jsonl','analysis/trajectory_metrics.csv','analysis/outcome_association.csv','analysis/summary.json','analysis/validation.json','analysis/attempts.json','analysis/mechanical_review_flags.json','review/pilot_review.json','review/semantic_review.json','review/raw_evidence_checks.json','references/model_provenance.json']
score_manifest={'completed_at':now(),'experiment':ROOT.name,'scope':'540 trajectories from the train90 epoch5 LoRA-SFT initial policy; scoring only','counts':{'trajectories':540,'tasks':90,'steps':9886,'rubric_labels':79088},'source_manifest':'manifest.json','source_manifest_sha256':sha(ROOT/'manifest.json'),'model':cfg['model'],'reasoning_effort':cfg['reasoning_effort'],'prompt_version':manifest['prompt_version'],'prompt_sha256':manifest['prompt_sha256'],'config_sha256':sha(ROOT/'judge_config.json'),'outputs':{p:{'sha256':sha(ROOT/p),'bytes':(ROOT/p).stat().st_size} for p in outputs},'samples':[{'id':x['id'],'trajectory_id':x['trajectory_id'],'source_sha256':x['source_sha256'],'input_sha256':x['input_sha256'],'steps':x['steps'],'judgement':f"runs/scoring/{x['id']}/judgement.json",'judgement_sha256':sha(ROOT/'runs/scoring'/x['id']/'judgement.json'),'accepted_attempt':read(ROOT/'runs/scoring'/x['id']/'metadata.json')['accepted_attempt']} for x in manifest['samples']]}
dump(ROOT/'score_manifest.json',score_manifest)
report=ROOT/'REPORT.md'; txt=report.read_text()
clear=review.get('confirmed_errors',[]); boundary=review.get('boundary_disagreements',[])
section=f'''\n## 语义复核结论\n\n已完成最初 8 条试评和预选 12 条样本的关键证据复核。12 条样本预先确定；其中 53 项证据检查在对应评分到达前冻结。该复核是定向质量检查，不是全部 79,088 个标签的人工金标准验收，也不能给出总体准确率。\n\n本次复核记录 {len(clear)} 项明确标签问题、{len(boundary)} 项边界争议；细节及证据见 [语义复核记录](review/semantic_review.json)。原始标签全部保留，未按复核意见静默改写，也未发起语义重评挑选结果。\n\n最终输出及逐轨迹哈希见 [评分清单](score_manifest.json)。后续局部 SFT 筛选应显式处理这些已知问题，而不能把格式通过当作标签全部正确。\n'''
if '## 语义复核结论' not in txt: report.write_text(txt+section)
(ROOT/'README.md').write_text(f'''# SFT 初始模型 AppWorld 540 条轨迹评分：已完成\n\n英文 v6 format prompt；GPT-6.1 sol / high；540 条、9,886 步、79,088 个标签。覆盖与来源验收通过；评分阶段耗时 {timing['scoring_wall_seconds']/60:.2f} 分钟。未训练或改动源模型。\n\n- [完整报告](REPORT.md)\n- [逐步标签 CSV](analysis/step_labels.csv)\n- [逐步标签 JSONL](analysis/step_labels.jsonl)\n- [完整逐轨迹评分 JSONL](analysis/scored_trajectories.jsonl)\n- [评分清单和哈希](score_manifest.json)\n- [文件与标签说明](analysis/DATA_DICTIONARY.md)\n- [结构验收](analysis/validation.json) · [语义复核](review/semantic_review.json)\n\n数据唯一来源为 `2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts/trajectories`。本目录独立保存输入、prompt、schema、配置、来源清单、原始响应和重试日志。不是原始基座模型那批轨迹。语义问题另记，原始裁判结果不静默修改。\n''')
dump(ROOT/'COMPLETION_CHECK.json',{'completed_at':now(),'scoring_complete':True,'structural_validation_passed':True,'semantic_review_complete':True,'trajectories':540,'steps':9886,'labels':79088,'confirmed_review_issues':len(clear),'boundary_disagreements':len(boundary),'score_manifest_sha256':sha(ROOT/'score_manifest.json'),'report_sha256':sha(report)})
status=read(ROOT/'STATUS.json'); status.update(phase='complete',updated_at=now(),valid=540,steps_valid=9886,queued=0,active={}); dump(ROOT/'STATUS.json',status)
dump(ROOT/'PIPELINE_STATUS.json',{'updated_at':now(),'phase':'complete','score_manifest':'score_manifest.json','report':'REPORT.md'})
print(json.dumps({'complete':True,'trajectories':540,'steps':9886,'labels':79088,'confirmed_review_issues':len(clear),'boundary_disagreements':len(boundary)}))
