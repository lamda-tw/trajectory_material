"""Freeze the selected Action-1epoch Dev57 evaluation and verify reused baseline."""
from pathlib import Path
import datetime,hashlib,json,shutil
OUT=Path(__file__).resolve().parent
EXP=OUT.parent
ROOT=EXP.parents[1]
BASELINE=ROOT/'experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57'
CHECK=EXP/'step07b_check30_one_epoch'
STEP01=EXP/'step01_train90_student_rollouts'
SUB=Path('experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev')
BRANCH='CFST-Action'
def read(p):return json.loads(p.read_text())
def jl(p):return [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def dump(p,x):
 p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def main():
 assert not (OUT/'manifest.json').exists(),'Refusing to overwrite evaluation'
 selected=read(CHECK/'selection.json');assert selected['selected_candidate']==BRANCH
 assert read(CHECK/'validation.json')['passed']
 frozen=read(EXP/'step06b_lora_one_epoch/summary.json');assert frozen['status']=='SUCCESS'
 ids=(BASELINE/'data/datasets/dev.txt').read_text().splitlines();bm=read(BASELINE/'manifest.json')
 assert len(ids)==len(set(ids))==57 and len({t.rsplit('_',1)[0] for t in ids})==19
 assert sha(BASELINE/'data/datasets/dev.txt')==bm['dev_split_sha256']=='9fa976589300ea8905708257144d801d1604b06d85fb0181e381df8a3ba85001'
 train_split=read(EXP/'step02_error_analysis/task_split.json')
 train_ids=train_split['source_task_ids']+train_split['check_task_ids']
 assert not set(train_ids)&set(ids)
 assert not {t.rsplit('_',1)[0] for t in train_ids}&{t.rsplit('_',1)[0] for t in ids}
 for key,value in dict(temperature=0,seed=100,max_completion_tokens=3000,max_steps=50,max_model_len=32000,reasoning_parser=None).items():assert bm[key]==value
 assert sha(Path(bm['adapter'])/'adapter_model.safetensors')==bm['adapter_sha256']
 original={}
 for line in (BASELINE/'artifacts.sha256').read_text().splitlines():
  h,rel=line.split(maxsplit=1);p=BASELINE/rel;assert sha(p)==h,str(p);original[str(p)]=h
 assert sha(BASELINE/'scripts_snapshot/appworld_run_isolated_lora_config.py')==sha(STEP01/'scripts_snapshot/appworld_run_isolated_lora_config.py')
 source_checks={}
 for name,h in read(STEP01/'config/source_hashes.json').items():
  p=Path(name) if name.startswith('/') else STEP01/name
  source_checks[str(p)]=sha(p)==h
 assert all(source_checks.values())
 live_prompt=Path('/root/autodl-tmp/envs/appworld-0.2.0-py312/lib/python3.12/site-packages/appworld_agents/prompts/react_code_agent/instructions.txt')
 assert sha(live_prompt)==read(STEP01/'manifest.json')['prompt_sha256']
 official=read(BASELINE/SUB/'evaluations/dev.json');statuses=jl(BASELINE/'task_status.jsonl')
 assert [r['task_id'] for r in statuses]==ids and set(official['individual'])==set(ids)
 assert sum(v['success'] for v in official['individual'].values())==23
 assert sum(len(v['passes']) for v in official['individual'].values())==206
 assert sum(v['num_tests'] for v in official['individual'].values())==291
 evidence={};base_rows=[];request_count=0
 for tid,live in zip(ids,statuses):
  task=BASELINE/SUB/'tasks'/tid;item=official['individual'][tid]
  assert live['status'] in ['success','failed'] and (live['status']=='success')==item['success']
  assert len(item['passes'])+len(item['failures'])==item['num_tests']==live['num_tests']
  assert len(item['passes'])==live['passed_tests'] and len(item['failures'])==live['failed_tests']
  calls=jl(task/'logs/lm_calls.jsonl');assert 0<len(calls)<=50
  for call in calls:
   assert all(call['input'].get(k)==v for k,v in dict(model=bm['served_adapter_name'],temperature=0,seed=100,max_completion_tokens=3000).items())
   request_count+=1
  assert calls[0]['input']['messages'][0]['content']
  for rel in ['logs/lm_calls.jsonl','logs/environment_io.md','logs/api_calls.jsonl','logs/logger.jsonl','misc/finished','evaluation/report.md']:
   p=task/rel;assert p.is_file();evidence[str(p)]=sha(p)
  base_rows.append(dict(**live,trajectory_dir=str(task),official_report_path=str(task/'evaluation/report.md')))
 old_guard={**original,**evidence}
 for stage in [CHECK,EXP/'step06b_lora_one_epoch']:
  a=read(stage/'artifact_sha256.json')
  for rel,h in a.get('files',a).items():
   p=stage/rel;assert sha(p)==h,str(p);old_guard[str(p)]=h
  old_guard[str(stage/'artifact_sha256.json')]=sha(stage/'artifact_sha256.json')
 for rel,h in read(CHECK/'evidence_sha256.json').items():
  p=CHECK/rel;assert sha(p)==h;old_guard[str(p)]=h
 for path,h in read(CHECK/'old_results_guard.json')['files_sha256'].items():
  assert sha(Path(path))==h;old_guard[path]=h
 dump(OUT/'old_results_guard.json',dict(files_sha256=old_guard))
 dump(OUT/'baseline_reuse_validation.json',dict(passed=True,source=str(BASELINE),manifest=bm,source_checks=source_checks,validated_request_count=request_count,source_artifact_hashes=original,evidence_sha256=evidence,task_count=57,success_count=23,passed_tests=206,total_tests=291,official_scores=official['aggregate'],prompt_sha256=sha(live_prompt)))
 dump(OUT/'baseline/official_evaluation.json',official)
 (OUT/'baseline/task_status.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in base_rows))
 (OUT/'dev_task_ids.txt').write_text('\n'.join(ids)+'\n')
 d=OUT/BRANCH
 for sub in ['logs','cache','metrics','scripts_snapshot','data/datasets','config']:(d/sub).mkdir(parents=True,exist_ok=True)
 for child in (BASELINE/'data').iterdir():
  if child.name!='datasets':(d/'data'/child.name).symlink_to(child.resolve(),target_is_directory=child.is_dir())
 (d/'data/datasets/dev.txt').write_text('\n'.join(ids)+'\n')
 shutil.copytree(BASELINE/'config/agent_configs',d/'config/agent_configs')
 shutil.copytree(STEP01/'cache/tests',d/'cache/tests')
 shutil.copy2(BASELINE/'scripts_snapshot/appworld_run_isolated_lora_config.py',d/'scripts_snapshot/appworld_run_isolated_lora_config.py')
 shutil.copy2(live_prompt,d/'config/react_instructions.txt')
 a=Path(frozen['branches'][BRANCH]['adapter_dir']);h=sha(a/'adapter_model.safetensors');assert h==frozen['branches'][BRANCH]['adapter_model_sha256']
 protocol=dict(temperature=0,seed=100,max_completion_tokens=3000,max_steps=50,max_model_len=32000,reasoning_parser=None,num_processes=1)
 candidate=dict(model=bm['model'],adapter=str(a),adapter_sha256=h,served_adapter_name='cfst-action-1epoch',model_config=bm['model_config'],dataset='dev',task_count=57,scenario_count=19,gpu=0,**protocol,teacher_calls=0,new_training=False,training_variant='one_epoch',logging_only_ellipsis_fix=True,prefix_replay=False,status='prepared')
 dump(d/'manifest.json',candidate)
 dump(OUT/'manifest.json',dict(stage=OUT.name,status='prepared',created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Only selected CFST-Action-1epoch on Dev57, with reused original epoch5 baseline; no source60 refresh or training.',selected_candidate=BRANCH,selection_source=str(CHECK/'selection.json'),selection_sha256=sha(CHECK/'selection.json'),training_stage='step06b_lora_one_epoch',baseline_reused=True,baseline_success=23,baseline_passed_tests=206,baseline_total_tests=291,dev_ids=ids,dev_ids_sha256=sha(OUT/'dev_task_ids.txt'),protocol=protocol,branches={BRANCH:candidate},acceptance_rule=dict(check30_net_gain_positive=True,check30_net_gain=2,dev57_success_count_at_least_baseline=23,decision_metric='official task success count; test pass percentages are reported separately'),reporting=dict(per_task_evaluator_details=True,aggregate_assertion_pass_percent=True,macro_task_assertion_pass_percent=True,official_TGC_and_SGC=True),logging_wrapper_sha256=sha(OUT/'resilient_entry.py'),baseline_runner_sha256=sha(BASELINE/'scripts_snapshot/appworld_run_isolated_lora_config.py'),baseline_config_sha256=sha(BASELINE/'config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev.jsonnet')))
 print(json.dumps(dict(baseline_reuse='PASS',baseline_success='23/57',baseline_test_pass='206/291',baseline_test_pass_percentage=100*206/291,baseline_requests_validated=request_count,protected_old_files=len(old_guard),candidate_adapter_sha256=h),indent=2))
if __name__=='__main__':main()
