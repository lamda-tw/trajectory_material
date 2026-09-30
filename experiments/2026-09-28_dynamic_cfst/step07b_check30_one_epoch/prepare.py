from pathlib import Path
import hashlib,json,shutil,datetime
ROOT=Path(__file__).resolve().parents[3]
EXP=ROOT/'experiments/2026-09-28_dynamic_cfst'
OUT=Path(__file__).resolve().parent
OLD=EXP/'step01_train90_student_rollouts'
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def read(p):return json.loads(Path(p).read_text())
def dump(p,x):
    p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def jl(p):return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
def main():
    if (OUT/'manifest.json').exists():raise RuntimeError('Already prepared; refusing to overwrite frozen evaluation')
    split=read(EXP/'step02_error_analysis/task_split.json')
    ids=(EXP/'step02_error_analysis/check_task_ids.txt').read_text().splitlines()
    assert ids==split['check_task_ids'] and len(set(ids))==30
    assert not set(ids)&set(split['source_task_ids'])
    assert not {x.rsplit('_',1)[0] for x in ids}&{x.rsplit('_',1)[0] for x in split['source_task_ids']}
    manifest=read(OLD/'manifest.json')
    assert read(OLD/'metrics/final_validation.json')['passed']
    checks={}
    for name,h in read(OLD/'config/source_hashes.json').items():
        p=Path(name) if name.startswith('/') else OLD/name
        checks[name]=sha(p)==h
    prompt=Path('/root/autodl-tmp/envs/appworld-0.2.0-py312/lib/python3.12/site-packages/appworld_agents/prompts/react_code_agent/instructions.txt')
    checks['live_prompt_matches']=sha(prompt)==manifest['prompt_sha256']
    checks['source_adapter_unchanged']=sha(Path(manifest['adapter'])/'adapter_model.safetensors')==manifest['adapter_sha256']
    assert all(checks.values()),checks
    evidence=read(OLD/'metrics/evidence_sha256.json')
    baseline_rows={r['task_id']:r for r in jl(OLD/'trajectory_index.jsonl')}
    official_path=OLD/'experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train/evaluations/train.json'
    official=read(official_path)
    baseline=[]; hashes={}
    for tid in ids:
        row=baseline_rows[tid];item=official['individual'][tid]
        assert row['official_success']==item['success'] and row['status'] in ('success','failed')
        for rel,h in evidence.items():
            if f'/tasks/{tid}/' in rel:
                assert sha(OLD/rel)==h,rel
                hashes[str(OLD/rel)]=h
        calls=jl(row['lm_calls_path'])
        for call in calls:
            for k,v in dict(model=manifest['served_adapter_name'],temperature=0,seed=100,max_completion_tokens=3000).items():assert call['input'][k]==v
        baseline.append(row)
    assert sum(x['official_success'] for x in baseline)==17 and len(hashes)==180
    dump(OUT/'baseline_reuse_validation.json',dict(passed=True,checks=checks,baseline_success=17,baseline_failure=13,task_count=30,source=str(OLD),evidence_sha256=hashes,official_aggregate_sha256=sha(official_path),note='Reuse official per-task results; recompute aggregates for the check30 subset.'))
    (OUT/'baseline').mkdir()
    (OUT/'baseline/trajectory_index.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in baseline))
    dump(OUT/'baseline/official_individual.json',{tid:official['individual'][tid] for tid in ids})
    (OUT/'check_task_ids.txt').write_text('\n'.join(ids)+'\n')
    shutil.copy2(EXP/'step02_error_analysis/task_split.json',OUT/'task_split.json')
    m6=read(EXP/'step06b_lora_one_epoch/summary.json');assert m6['status']=='SUCCESS'
    assert read(EXP/'step06b_lora_one_epoch/validation.json')['status']=='PASS'
    assert read(EXP/'step06b_lora_one_epoch/summary.json')['training_amount_policy']['epochs']==1
    runners={};protocol=dict(temperature=0,seed=100,max_completion_tokens=3000,max_steps=50,max_model_len=32000,reasoning_parser=None,num_processes=1,teacher_calls=0,new_training=False)
    for branch,gpu in [('CFST-state',0),('CFST-Action',1),('CFST-Mixed',0)]:
        d=OUT/branch
        for sub in ['logs','cache','metrics','scripts_snapshot','data/datasets','config']:(d/sub).mkdir(parents=True,exist_ok=True)
        for child in (OLD/'data').iterdir():
            if child.name!='datasets':(d/'data'/child.name).symlink_to(child.resolve(),target_is_directory=child.is_dir())
        (d/'data/datasets/train.txt').write_text('\n'.join(ids)+'\n')
        shutil.copytree(OLD/'config/agent_configs',d/'config/agent_configs')
        shutil.copytree(OLD/'cache/tests',d/'cache/tests')
        shutil.copy2(OLD/'config/react_instructions.txt',d/'config/react_instructions.txt')
        shutil.copy2(OLD/'scripts_snapshot/appworld_run_isolated_lora_config.py',d/'scripts_snapshot/appworld_run_isolated_lora_config.py')
        a=Path(m6['branches'][branch]['adapter_dir']);h=sha(a/'adapter_model.safetensors');assert h==m6['branches'][branch]['adapter_model_sha256']
        runner=dict(training_variant='one_epoch',logging_only_ellipsis_fix=True,prefix_replay=False,model=manifest['model'],adapter=str(a),adapter_sha256=h,served_adapter_name=branch.lower()+'-1epoch',model_config=manifest['model_config'],dataset='train',semantic_dataset='frozen_check30',task_count=30,scenario_count=10,gpu=gpu,**protocol,status='prepared')
        dump(d/'manifest.json',runner);runners[branch]=runner
    dump(OUT/'manifest.json',dict(stage='step07b_check30_one_epoch',status='prepared',created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),scope='Section 7.1 check30 only; Dev57 is not run in this request.',training_stage='step06b_lora_one_epoch',prefix_replay=False,logging_wrapper_sha256=sha(OUT/'resilient_entry.py'),baseline_reused=True,baseline_success=17,check_ids=ids,check_ids_sha256=sha(OUT/'check_task_ids.txt'),protocol=protocol,branches=runners,selection_rule=dict(require_positive_net_gain=True,sort=['net_gain_desc','regressions_asc','frozen_tie_order'],tie_order=read(EXP/'step05_training_packages/manifest.json')['order_policy']['check30_tie_break_branch_order']),baseline_runner_sha256=sha(OLD/'scripts_snapshot/appworld_run_isolated_lora_config.py'),baseline_config_sha256=sha(OLD/'config/agent_configs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train.jsonnet')))
    print('Baseline reuse verified: 17/30; 180 evidence files checked. Three isolated check30 roots prepared.')
if __name__=='__main__':main()
