"""Verify finished experiment and publish completion metadata; no inference."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,math
R=Path(__file__).resolve().parents[1]
S=R.parent/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full'
P=R.parents[1]/'plans/2026-10-12_appworld_step_rubric'
def read(p):return json.loads(p.read_text())
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for chunk in iter(lambda:f.read(8*1024*1024),b''):h.update(chunk)
 return h.hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
state=read(R/'STATUS.json');assert state['phase'] in ['runs_complete_awaiting_analysis','complete'],state
summary=read(R/'analysis/summary.json')
for rel,h in read(R/'EXECUTION_MANIFEST.json')['files'].items():assert sha(R/rel)==h,rel
for rel,h in read(R/'data/DATA_MANIFEST.json')['artifacts'].items():assert sha(R/rel)==h,rel
assert read(R/'data/VALIDATION.json')['phase']=='passed'
source=read(S/'manifest.json');old_check=read(S/'COMPLETION_CHECK.json')
assert len(source['samples'])==540
for x in source['samples']:
 assert sha(Path(x['source']))==x['source_sha256'],x['id']
 assert sha(S/'runs/scoring'/x['id']/'judgement.json')==old_check['raw_judgement_sha256'][x['id']],x['id']
assert sha(P/'prompt_v5.txt')==source['prompt_sha256']==sha(R/'config/scoring_prompt_v5.txt')
assert sha(P/'prompt_v6.txt')==read(P/'v6_provenance.json')['prompt_sha256']
train_ids=set((R/'config/train_all.txt').read_text().split());dev_ids=set((R/'config/dev.txt').read_text().split())
assert len(train_ids)==90 and len(dev_ids)==57 and not train_ids&dev_ids
assert not {x.rsplit('_',1)[0] for x in train_ids}&{x.rsplit('_',1)[0] for x in dev_ids}
stages=[]
for p in sorted((R/'logs').glob('*.json')):
 j=read(p)
 if 'kind' not in j:continue
 assert j['status']=='complete' and j['exit_code']==0,p
 proc=Path(f"/proc/{j['pid']}/cmdline")
 if proc.exists():assert str(R).encode() not in proc.read_bytes(),('owned stage still running',j['pid'])
 elapsed=(datetime.fromisoformat(j['finished_at'])-datetime.fromisoformat(j['started_at'])).total_seconds()
 stages.append({'kind':j['kind'],'arm':j['arm'],'started_at':j['started_at'],'finished_at':j['finished_at'],'process_wall_seconds':elapsed})
assert len(stages)==5
for arm in ['base','rubric','uniform']:
 d=read(R/f'evaluation/{arm}/SUMMARY.json')
 assert d['phase']=='complete' and d['tasks']==57 and {x['task_id'] for x in d['results']}==dev_ids
 for x in d['results']:
  assert x['tests']>0 and sha(Path(x['source']))==x['sha256'],x['task_id']
 if arm=='base':continue
 c=read(R/f'training/{arm}/COMPLETE.json');m=read(R/f'training/{arm}/metrics.json')
 assert c['updates']==48 and c['supervised_tokens']==196608 and len(m)==48
 assert c['initial_adapter_tensor_sha256']!=c['final_adapter_tensor_sha256']
 assert sum(x['supervised_tokens'] for x in m)==196608
 assert all(math.isfinite(x['loss']) for x in m)
 for rel,h in c['adapter_files'].items():assert sha(R/f'training/{arm}/adapter'/rel)==h
assert summary['same_initial_adapter']
finished=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
latest=max(x['finished_at'] for x in stages)
timing={'execution_started_at':state['started_at'],'training_and_dev_finished_at':latest,'analysis_and_verification_finished_at':finished,'training_and_dev_wall_seconds':(datetime.fromisoformat(latest)-datetime.fromisoformat(state['started_at'])).total_seconds(),'total_execution_to_verified_completion_seconds':(datetime.fromisoformat(finished)-datetime.fromisoformat(state['started_at'])).total_seconds(),'stages':stages,'note':'Two GPU lanes overlap. Sum of stage wall times is not total elapsed time. No external model scoring or teacher action generation.'}
write(R/'TIMING.json',timing)
rows='\n'.join(f"| {a} | {summary['arms'][a]['successes']}/57 | {100*summary['arms'][a]['TGC']:.2f}% |" for a in ['base','uniform','rubric'])
(R/'README.md').write_text(f'''# Rubric 局部 SFT 与均匀抽样\n\n实验已完成。只使用已有540条原始Qwen3-8B轨迹和prompt_v5评分；不生成或替换训练动作，不调用新的外部judge。\n\n| 模型 | DEV57 官方成功 | TGC |\n| --- | ---: | ---: |\n{rows}\n\n两组均为全新LoRA、196,608监督token、48次更新、同题token配额。主要对照为rubric与uniform，base按相同协议重新验证；单seed结果不代表稳定优势。\n\n- [完整报告]({R/'REPORT.md'})\n- [事前冻结方案]({R/'PLAN.md'})\n- [逐题比较]({R/'analysis/task_comparison.csv'})\n- [结果与配对统计]({R/'analysis/summary.json'})\n- [用时]({R/'TIMING.json'})\n- [rubric LoRA]({R/'training/rubric/adapter'})\n- [uniform LoRA]({R/'training/uniform/adapter'})\n- [完成校验]({R/'COMPLETION_CHECK.json'})\n\nprompt_v6另存用于后续评分，未经新语义评分实测，未用于本实验。\n''')
state['phase']='complete';state['analysis_and_verification_finished_at']=finished;state['report']=str(R/'REPORT.md');write(R/'STATUS.json',state)
artifacts=[p for p in R.rglob('*') if p.is_file() and (p.parent==R or p.parent==R/'analysis' or p.parent==R/'scripts') and p.name!='COMPLETION_CHECK.json' and '__pycache__' not in str(p)]
check={'phase':'complete','checked_at':finished,'source_trajectories_checked':540,'frozen_raw_v5_judgements_checked':540,'train_tasks':90,'dev_tasks':57,'dev_results':171,'frozen_execution_and_data_hashes_match':True,'original_trajectories_and_v5_unchanged':True,'same_initial_lora':True,'updates_per_arm':48,'supervised_tokens_per_arm':196608,'all_official_evaluations_valid':True,'all_five_stages_exit_zero':True,'owned_stage_processes_exited':True,'external_judge_calls':0,'generated_training_actions':0,'artifact_sha256':{str(p.relative_to(R)):sha(p) for p in sorted(artifacts)}}
write(R/'COMPLETION_CHECK.json',check)
print(json.dumps({'phase':'complete','timing':timing,'results':{a:summary['arms'][a]['successes'] for a in ['base','uniform','rubric']}},ensure_ascii=False,indent=2))
