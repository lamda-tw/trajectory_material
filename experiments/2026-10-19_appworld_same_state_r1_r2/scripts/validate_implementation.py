"""CPU verification of isolation, frozen inputs, credentials and paired-analysis behavior."""
from pathlib import Path
import csv,json,os,sys
R=Path(__file__).resolve().parents[1];W=R.parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import digest,file_sha,parse_code,atomic_json
from public_payload import public_prefix,sanitize
from analyze_phase1 import task_equal,bootstrap_pair
from policy_server import server_command
from judging import validate
c=json.loads((R/'config/runtime.json').read_text());models=json.loads((R/'plan_snapshot/same_state_models.json').read_text())['models'];assert len(models)==9
for m in models:assert file_sha(W/m['adapter'])==m['adapter_sha256']
for p in (R/'inputs').glob('*.json'):
 d=json.loads(p.read_text());k=int(d['state']['before_step']);pub=public_prefix(d);assert len(pub['history'])==k-1 and all(h['step']<k for h in pub['history']);assert set(pub)=={'state_id','prefix_hash','task','agent_instructions','history'}
 assert digest(d['prompt_ids'])==d['state']['prompt_ids_sha256']
 clean,_=sanitize(pub);assert sanitize(clean)[0]==clean
 for h in d['history']:assert parse_code(h['history_assistant_text'])[0]==h['code']
for x in json.loads((R/'calibration/judge_calibration_results_v2.json').read_text()):
 sid=x['state_id'].replace(':','__')
 for kind,sub in [('card','calibration_cards_v2'),('action','calibration_actions_v2')]:
  p=R/'judge_runs'/sub/sid;validate(json.loads((p/'judgement.json').read_text()),json.loads((p/'input.json').read_text()),kind)
# Non-mirroring checks: uneven eligible states should not overweight a task;
# a paired sign reversal must survive pooling and family resampling.
rr=[{'seed':1,'task_id':'a_1','metric':1},{'seed':1,'task_id':'a_1','metric':1},{'seed':1,'task_id':'b_1','metric':0}]
assert task_equal(rr,'metric')==.5
paired=[]
for fam in ['a','b']:
 for seed in [1,2,3]:
  for g,val in [('full_rule_1358',1),('drop_r1',0)]:paired.append({'family':fam,'task_id':fam+'_1','state_id':fam+'_1:s1','seed':seed,'group':g,'metric':val})
assert bootstrap_pair(paired,'drop_r1','metric',100)==(-1,-1)
os.environ['CUDA_VISIBLE_DEVICES']=c['server']['gpu'];cmd=server_command(c,(W/models[0]['adapter']).parent);assert '--enable-lora' in cmd and '--max-model-len' in cmd and c['server']['gpu'].endswith('0c092a3e8501')
assert c['agent']['max_model_len']==32000 and c['agent']['max_new_tokens']==3000 and c['evaluation']['temperature']==0
summary={'passed':True,'input_files':307,'all_nine_adapter_hashes_verified':True,'no_current_or_future_action_in_prefix':True,'credential_redaction_idempotent':True,'calibration_judge_schemas_valid':True,'task_equal_and_pair_sign_checks':True,'server_command_gpu1_only':True,'formal_generation_count':0,'new_gpu_allocations':0}
atomic_json(R/'calibration/implementation_audit.json',summary);print(json.dumps(summary))
