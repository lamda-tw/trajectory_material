"""Finalize only after scoring, statistical analysis, and documented semantic review."""
from pathlib import Path
import json,hashlib,time,datetime
R=Path(__file__).resolve().parents[1]
OLD=R.parents[1]/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full'
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
s=read(R/'analysis/summary.json');manual=read(R/'review/manual_review.json');plan=read(R/'review/semantic_sample_plan.json')
assert s['trajectories']==540 and s['steps']==11254
assert set(x['id'] for x in manual['coverage'])==set(plan['ids'])
assert sum(len(x['steps_reviewed']) for x in manual['coverage'])==176
for x in manual['coverage']:
 assert x['steps_reviewed']==[q['id'] for q in read(R/'inputs'/f"{x['id']}.json")['steps']]
seen=set()
for finding in manual['findings']:
 key=(finding['id'],finding['step'],finding['rubric']);assert key not in seen;seen.add(key)
 rows={q[0]:q[1] for q in read(R/'runs/scoring'/finding['id']/'judgement.json')['steps']}
 assert rows[finding['step']][int(finding['rubric'][1:])-1]==finding['observed']
 assert finding['kind'] in {'clear_error','debatable'}
 assert finding['observed'] not in finding['preferred']
frozen=read(R/'runs/scoring/run_manifest.json')
assert all(sha(R/p)==h for p,h in frozen['files'].items())
assert all(p.read_bytes()==(OLD/'inputs'/p.name).read_bytes() for p in (R/'inputs').glob('*.json'))
for p in ['REPORT.md','review/MANUAL_REVIEW.md','review/report_conclusions.json','analysis/figures/rubric_distribution.png','analysis/rubric_validity/statistics.json','analysis/configuration_comparison.json']:
 assert (R/p).stat().st_size>0
# Check judge tools in every attempt, including invalid responses.
for p in (R/'runs/scoring').glob('*/attempt_*/events.jsonl'):
 for line in p.read_text().splitlines():
  e=json.loads(line)
  if isinstance(e.get('item'),dict):
   assert e['item'].get('type') not in {'command_execution','mcp_tool_call','web_search','file_change','collab_tool_call'},str(p)
assert not list((R/'runs/scoring').glob('*/attempt_*/RUNNING.json'))
timer=read(R/'EVALUATION_TIMING.json');timer.update(phase='complete',evaluation_finished_at=now,evaluation_wall_seconds=time.time()-timer['evaluation_start_epoch'],raw_evidence_preparation_note='Pre-score-label evidence reading overlapped scoring; separately recorded in review/RAW_REVIEW_FREEZE.json, excluded from this post-scoring wall time.');write(R/'EVALUATION_TIMING.json',timer)
write(R/'ANALYSIS_STATUS.json',{'phase':'complete','semantic_review':'complete','report':'complete','finished_at':now})
status=read(R/'STATUS.json');status.update(phase='complete',analysis_finished_at=now);write(R/'STATUS.json',status)
(R/'README.md').write_text('# 英文 v6 / GPT-6.1 sol 全量评分：已完成\n\n540 条、11,254 步、90,032 个标签，并发上限 8、high reasoning；服务容量不足时按预设策略短暂降并发。评分墙钟 '+f"{s['scoring_wall_seconds']/60:.2f}"+' 分钟；计时包括重试和校验，不含准备与后续分析。\n\n[完整实验报告](REPORT.md) · [标签分布图](analysis/figures/rubric_distribution.png) · [逐步评分](analysis/step_labels.csv) · [语义复核](review/MANUAL_REVIEW.md)\n\n输入与旧中文全量实验逐字节相同。本轮改变了语言、v5→v6 规则和 judge 模型，是质量优先的配置比较，不能当作纯语言消融。原始输出及所有失败尝试均保留；未修改 LoRA 训练数据。\n')
files={str(p.relative_to(R)):sha(p) for folder in ['analysis','review'] for p in (R/folder).rglob('*') if p.is_file()}
files.update({p:sha(R/p) for p in ['REPORT.md','README.md','TIMING.json','EVALUATION_TIMING.json']})
write(R/'COMPLETION_CHECK.json',{'completed_at':now,'trajectories':540,'steps':11254,'cells':90032,'all_original_inputs_identical':True,'frozen_scoring_files_unchanged':True,'manual_review_trajectories':12,'manual_review_steps':176,'no_active_attempt_markers':True,'judge_tool_calls_all_attempts':0,'artifact_sha256':files})
print('Experiment completed and artifact hashes recorded.')
