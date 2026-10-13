"""Verify the completed, frozen scoring run and close only evaluation timing."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import csv,hashlib,json,re,time
from judge_protocol import validate,audit_events
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def dump(p,d):(R/p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
frozen=read('runs/scoring/run_manifest.json')
for p,h in frozen['files'].items():assert sha(R/p)==h,p
canonical=R.parents[1]/'plans/2026-10-12_appworld_step_rubric/prompt_v5.txt'
assert sha(canonical)==sha(R/'assets/prompt_v5.txt')
assert sha(R/'review/semantic_sample_plan.json')==frozen['semantic_review_plan_sha256']
timer=read('TIMING.json');assert timer['phase']=='scoring_complete'
original_timer_sha=sha(R/'TIMING.json')
schema=read('assets/output_schema_v5.json');manifest=read('manifest.json')['samples']
assert len(manifest)==540
all_results=[];attempt_count=0;out_hash={}
for sample in manifest:
 sid=sample['id'];folder=R/'runs/scoring'/sid
 inp=json.loads((folder/'input.json').read_text());result=json.loads((folder/'judgement.json').read_text())
 validate(result,inp,schema);all_results.append(result);out_hash[sid]=sha(folder/'judgement.json')
 for event in folder.glob('attempt_*/events.jsonl'):
  audit_events(event);attempt_count+=1
assert attempt_count==542
export=[json.loads(x) for x in (R/'analysis/scored_trajectories.jsonl').read_text().splitlines()]
assert export==all_results
steps=list(csv.DictReader((R/'analysis/step_labels.csv').open()))
assert len(steps)==11254 and sum(len(x['steps']) for x in all_results)==11254
raw={(r['trajectory_id'].removeprefix('base:'),x[0]):x for r in all_results for x in r['steps']}
for x in steps:
 row=raw[x['id'],int(x['step'])]
 assert ''.join(x[f'R{i}'] for i in range(1,9))==row[1] and x['reason']==row[2]
candidates=[json.loads(x) for x in (R/'analysis/step_candidates.jsonl').read_text().splitlines()]
assert len(candidates)==6617 and len({(x['id'],x['step']) for x in candidates})==6381
assert all(x['training_weight'] is None for x in candidates)
review=read('analysis/semantic_review_summary.json')
assert (review['trajectories_reviewed'],review['steps_reviewed'],review['clear_error_cells'],review['debatable_cells'])==(12,176,27,21)
allowed={str(R/'COMPLETION_CHECK.json')}
for filename in ['REPORT.md','README.md']:
 for target in re.findall(r'\]\(([^)]+)\)',(R/filename).read_text()):
  if target.startswith('http'):continue
  assert target in allowed or Path(target).exists(),target
summary=read('analysis/summary.json')
assert summary['scoring_wall_seconds']==timer['scoring_wall_seconds']
assert sum(x['usage_reported']['input_tokens'] for x in read('analysis/attempts.json'))==11754719
assert sum(x['usage_reported']['output_tokens'] for x in read('analysis/attempts.json'))==2555901
end=time.time();evaluation=read('EVALUATION_TIMING.json')
assert evaluation['evaluation_start_epoch']>timer['scoring_end_epoch']
if not evaluation.get('evaluation_finished_at'):
 evaluation.update({'phase':'complete','evaluation_finished_at':now(),'evaluation_end_epoch':end,'evaluation_wall_seconds':end-evaluation['evaluation_start_epoch'],'scope':'Post-scoring official comparison, primary-assistant evidence review, analysis, report writing and final verification. No extra scoring model calls. Excludes the 6771.024665594101-second scoring window.'})
 dump('EVALUATION_TIMING.json',evaluation)
status=read('STATUS.json');status.update({'phase':'complete','updated_at':now(),'scoring_finished_at':timer['scoring_finished_at'],'scoring_elapsed_seconds':timer['scoring_wall_seconds'],'evaluation_finished_at':evaluation['evaluation_finished_at'],'evaluation_elapsed_seconds':evaluation['evaluation_wall_seconds'],'report':'REPORT.md','experiment_complete':True})
dump('STATUS.json',status)
assert sha(R/'TIMING.json')==original_timer_sha
paths=['REPORT.md','README.md','TIMING.json','EVALUATION_TIMING.json','STATUS.json','analysis/summary.json','analysis/step_labels.csv','analysis/scored_trajectories.jsonl','analysis/trajectory_metrics.csv','analysis/step_candidates.jsonl','analysis/report_metrics.json','analysis/semantic_review_summary.json','analysis/terminal_submission_analysis.json','review/manual_review.json','review/supplemental_review.json']
completion={'checked_at':now(),'phase':'complete','trajectories':540,'steps':11254,'rubric_cells':90032,'scoring_attempts':542,'frozen_files_unchanged':True,'canonical_v5_matches_snapshot':True,'all_attempt_event_audits_passed':True,'judge_tool_calls':0,'exports_exactly_match_raw_judgments':True,'all_weights_null':True,'no_scoring_timer_mutation':True,'evaluation_after_scoring':True,'no_training_started':True,'prior_full_source_integrity_check':'analysis/validation.json','scoring_wall_seconds':timer['scoring_wall_seconds'],'evaluation_wall_seconds':evaluation['evaluation_wall_seconds'],'experiment_preparation_to_completion_seconds':evaluation['evaluation_end_epoch']-datetime.fromisoformat(timer['experiment_prepared_at']).timestamp(),'artifact_sha256':{p:sha(R/p) for p in paths},'raw_judgement_sha256':out_hash}
dump('COMPLETION_CHECK.json',completion)
print(json.dumps({k:v for k,v in completion.items() if k not in ['artifact_sha256','raw_judgement_sha256']},ensure_ascii=False,indent=2))
