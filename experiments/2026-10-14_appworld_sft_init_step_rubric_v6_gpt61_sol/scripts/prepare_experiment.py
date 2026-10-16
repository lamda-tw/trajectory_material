"""Prepare this independent SFT-policy scoring experiment; no model calls."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from collections import Counter
import hashlib, json, shutil, runpy, os
ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT.parents[1]
PRIOR = WORK/'experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol'
SOURCE = WORK/'experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts'
def sha(raw): return hashlib.sha256(raw).hexdigest()
def dump(p,x):
    with p.open('x') as f: f.write(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
for d in ['assets','inputs','research','logs','runs/scoring','analysis','review','references']: (ROOT/d).mkdir(parents=True,exist_ok=True)
for name in ['prompt_v6_en.txt','output_schema_v6.json']: shutil.copy2(PRIOR/'assets'/name,ROOT/'assets'/name)
shutil.copy2(WORK/'experiments/2026-10-12_appworld_step_rubric_pilot/snapshots/prepare_input_v3.py',ROOT/'assets/prepare_input_v3.py')
for name in ['judge_protocol.py','run_scoring.py']: shutil.copy2(PRIOR/'scripts'/name,ROOT/'scripts'/name)
for name in ['trajectory_index.json','collection_validation.json']: shutil.copy2(SOURCE/name,ROOT/'references'/name)
shutil.copy2(WORK/'plans/2026-10-13_appworld_sft_init_local_sft_online_rl/PLAN.md',ROOT/'references/training_plan_snapshot.md')
prepare=runpy.run_path(str(ROOT/'assets/prepare_input_v3.py'))['prepare']
index=json.loads((SOURCE/'trajectory_index.json').read_text()); assert len(index)==540
samples=[]; outcomes=[]
for item in index:
    source=Path(item['trajectory']); assert source.parent==SOURCE/'trajectories'
    raw=source.read_bytes(); assert sha(raw)==item['sha256']
    assert item['policy_id'].startswith('initial-lora:')
    data=json.loads(raw); sid=source.stem; payload=prepare(data,'sft-init:'+sid)
    assert set(payload)=={'trajectory_id','task','agent_instructions','reference_api_docs','steps','termination'}
    assert [s['id'] for s in payload['steps']]==[s['step'] for s in data['steps']]
    assert len(payload['steps'])==item['steps']
    dest=ROOT/'inputs'/source.name; dump(dest,payload)
    samples.append({'id':sid,'trajectory_id':payload['trajectory_id'],'task_id':item['task_id'],'source':str(source),'source_sha256':sha(raw),'policy_id':item['policy_id'],'input':str(dest.relative_to(ROOT)),'input_sha256':sha(dest.read_bytes()),'steps':len(payload['steps']),'input_characters':len(dest.read_text()),'termination':data['termination']})
    assert item['success']==data['official_evaluation']['success']
    outcomes.append({'id':sid,'task_id':item['task_id'],'steps':item['steps'],'success':item['success'],'termination':item['termination']})
assert len({s['id'] for s in samples})==540
assert sum(s['steps'] for s in samples)==9886
assert len({s['task_id'] for s in samples})==90
assert set(Counter(s['task_id'] for s in samples).values())=={6}
assert sum(s['success'] for s in outcomes)==186
stamp=now()
config=json.loads((PRIOR/'judge_config.json').read_text())
config['source']='Fresh SFT-initial-policy inputs; frozen English v6 format prompt; no prior labels reused.'
config['sample_order_seed']=20261014
config['pilot_size']=8
config['max_attempts']=6
config['timeout_seconds']=900
config['max_workers']=8
config['initial_workers']=8
config['retry_policy']='First schema-valid result; bounded technical/format retries only; semantic flags never trigger best-of replacement.'
dump(ROOT/'judge_config.json',config)
prompt_hash=sha((ROOT/'assets/prompt_v6_en.txt').read_bytes())
assert prompt_hash=='df4e8fb406551f2d90e38bbe83838db181bda18e01d947b236ee10a05c633109'
dump(ROOT/'manifest.json',{'created_at':stamp,'purpose':'Fresh complete-trajectory step rubric labels for all 540 rollouts of the train90 epoch5 LoRA SFT model. Scoring only.','source_experiment':str(SOURCE),'prompt_version':'appworld-step-v6','prompt_sha256':prompt_hash,'input_preparer_version':'v3','input_preparer_sha256':sha((ROOT/'assets/prepare_input_v3.py').read_bytes()),'samples':samples})
dump(ROOT/'research/official_outcomes.json',{'warning':'Researcher only. Never included in judge inputs.','samples':outcomes})
# Outcome-stratified length coverage, distinct tasks; chosen before any judging.
pilot=[]; tasks=set()
for success in [True,False]:
    group=sorted([s for s in outcomes if s['success']==success],key=lambda x:(x['steps'],x['id']))
    for q in [0.05,0.35,0.65,0.95]:
        target=round(q*(len(group)-1))
        candidates=sorted(range(len(group)),key=lambda i:abs(i-target))
        pick=next(group[i] for i in candidates if group[i]['task_id'] not in tasks)
        pilot.append(pick); tasks.add(pick['task_id'])
dump(ROOT/'review/pilot_plan.json',{'selected_at':stamp,'method':'Four successes and four failures; nearest 5/35/65/95 percentiles of trajectory length per stratum; eight distinct tasks. Outcomes excluded from judge requests.','samples':pilot,'acceptance':'All steps/schema valid; review raw evidence for systematic rubric interpretation errors before expanding. Isolated semantic errors flagged and preserved, not rerolled.'})
# Independent post-score semantic sample, six successes/six failures, distinct from pilot.
review=[]; used={s['id'] for s in pilot}; review_tasks=set()
for success in [True,False]:
    group=sorted([s for s in outcomes if s['success']==success and s['id'] not in used],key=lambda x:(x['steps'],x['id']))
    for q in [.05,.2,.4,.6,.8,.95]:
        target=round(q*(len(group)-1))
        pick=next(group[i] for i in sorted(range(len(group)),key=lambda i:abs(i-target)) if group[i]['task_id'] not in review_tasks)
        review.append(pick); review_tasks.add(pick['task_id'])
dump(ROOT/'review/semantic_sample_plan.json',{'selected_at':stamp,'method':'12 preselected complete trajectories, 6 successes/6 failures, length-stratified, distinct tasks and disjoint from pilot. Purposive review, not an accuracy benchmark.','samples':review})
auth=json.loads((Path(os.environ.get('CODEX_HOME','/root/.codex'))/'auth.json').read_text())
assert auth.get('auth_mode')=='chatgpt' and not auth.get('OPENAI_API_KEY')
dump(ROOT/'AUTH_PROVENANCE.json',{'mode':'existing ChatGPT login','account_fingerprint':sha(str(auth.get('tokens',{}).get('account_id','')).encode())[:12],'recorded_at':stamp,'secrets_saved':False})
dump(ROOT/'STATUS.json',{'phase':'prepared','prepared_at':stamp,'valid':0,'total':540,'total_steps':9886})
dump(ROOT/'input_validation.json',{'passed':True,'trajectories':540,'tasks':90,'steps':9886,'successes_researcher_only':186,'failures_researcher_only':354,'source_hashes_verified':540,'exact_original_step_ids':True,'official_evaluation_excluded':True,'judge_calls':0,'input_adapter':'Frozen existing v3; equality-preserving credential replacement, not full anonymization'})
dump(ROOT/'AUTHORIZATION.json',{'scope':'User requested an independent experiments folder and all 540 LoRA-SFT trajectory scores with latest prompt and GPT-6.1 sol; authorized unattended handling. No training.','authorized_at_preparation':stamp})
(ROOT/'README.md').write_text('# SFT 初始模型 AppWorld 540 条轨迹逐步评分\n\n独立实验；状态见 STATUS.json。仅评分，不训练模型。\n\n来源：train90 epoch5 LoRA SFT 模型的 540 条轨迹、9,886 步。英文 v6 format prompt；gpt-6.1-sol / high；最多 8 个并发请求。先 8 条试评，检查后全量；最终复用相同配置的试评结果。每次评价完整轨迹，输出每步 R1—R8 的 P/F/U/N 标签。所有原始响应及失败尝试保留。官方成败仅用于研究者选样与事后分析。\n\n目录：inputs 为评分输入，runs/scoring 为逐条原始输出，analysis 为最终汇总，review 为质量复核，references 为来源索引和计划快照。\n')
print(json.dumps({'root':str(ROOT),'trajectories':len(samples),'steps':sum(s['steps'] for s in samples),'pilot':pilot},ensure_ascii=False))
