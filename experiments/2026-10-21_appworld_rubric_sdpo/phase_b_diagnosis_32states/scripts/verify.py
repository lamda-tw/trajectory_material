from pathlib import Path
import sys,json,math,collections,subprocess
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from common import read,write_json,now
from a_common import file_sha
m=read(D/'config/manifest.json');provenance=read(D/'config/model_provenance.json');parents={};branches=[];floats=0
assert len(m['states'])==32 and len({x['task_id'] for x in m['states']})==32
assert not read(D/'config/authorization.json')['training']
def finite(x):
 global floats
 if isinstance(x,float):assert math.isfinite(x);floats+=1
 elif isinstance(x,list):
  for a in x:finite(a)
 elif isinstance(x,dict):
  for a in x.values():finite(a)
for item in m['states']:
 assert file_sha(item['path'])==item['sha256'];s=read(item['path'])
 assert file_sha(s['source'])==s['source_sha256'];assert file_sha(s['judgment'])==s['judgment_sha256']
 assert file_sha(Path(s['source']).parent.parent/'dataset.json')==s['dataset_sha256']
 reference=read(D/'replay'/s['id']/'result.json');assert reference['all_observations_exact'] and reference['environment_supported']
 expected=['base_C0','ema36_C0','student36_C0']+([] if s['stratum']=='clean' else ['base_C2','ema36_C2'])
 for arm in expected:
  p=D/'runs'/arm/s['id']/'result.json';r=read(p);assert r['parameter_updates']==0 and r['all_observations_exact'] and r['environment_supported']
  assert r['before_sha256']==reference['before_sha256'] and r['prefix_api_sha256']==reference['prefix_api_sha256']
  ids=s['example']['teacher_prompt_ids' if arm.endswith('_C2') else 'prompt_ids'];assert r['actions'][0]['prompt_ids']==ids
  branches.append(r)
 p=read(D/'probabilities'/(s['id']+'.json'));finite(p)
 assert p['text_token_alignment'] and p['parameter_updates']==0 and p['model_parameter_gradients']==False
 h=p['historical_training_reproduction']
 if h:
  assert h['loss_absolute_difference']<1e-6
  if 'parent_checkpoint_sha256' in h:parents[h['parent_checkpoint']]=h['parent_checkpoint_sha256']
for path,sha in parents.items():assert file_sha(path)==sha
assert file_sha(R/'phase_b/runs/mixed/batch_036/checkpoint/state.pt')==provenance['checkpoint_sha256']
assert file_sha(Path(provenance['student36'])/'adapter_model.safetensors')==provenance['student_adapter_sha256']
assert file_sha(D/'models/student36/adapter_model.safetensors')==provenance['student_adapter_sha256']
assert file_sha(Path(provenance['ema36'])/'adapter_model.safetensors')==provenance['ema_adapter_sha256']
assert len(branches)==144
reviews=read(D/'analysis/manual_first_step_review.json');assert len(reviews['rows'])==72
for x in reviews['rows']:
 if x['targeted_first_step_repair']=='Y':assert not read(D/'runs'/x['condition']/x['state_id']/'result.json')['actions'][0]['execution_error']
proof=read(D/'probabilities/COMPLETE.json');assert proof['all_parameter_gradients_none'] and proof['new_optimizer_updates']==0
result={'verified_at':now(),'states':32,'unique_tasks':32,'valid_branches':len(branches),'generated_actions':sum(len(x['actions']) for x in branches),
 'original_sources_feedback_datasets_and_model_checkpoints_unchanged':True,'all_pre_action_states_and_api_replays_exact':True,'all_first_prompt_tokens_exact':True,
 'historical_checkpoint_hashes_rechecked':len(parents),'all_probability_numbers_finite':True,'finite_floats_checked':floats,'all_response_text_token_alignments_exact':True,
 'new_model_optimizer_updates':0,'all_model_parameter_gradients_none':True,'new_external_codex_requests':0,
 'gpu_query':subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,memory.free','--format=csv'],text=True)}
write_json(D/'verification.json',result)
write_json(D/'STATUS.json',{'stage':'complete','completed_at':now(),'physical_gpu':1,'gpu_released':True,'parameter_updates':0,'new_codex_calls':0,'states':32,'branches':144,'actions':result['generated_actions'],'report':str(D/'REPORT.md')})
paths=[*sorted((D/'scripts').glob('*.py')),*sorted((D/'config').glob('*.json')),D/'REPORT.md',D/'PROTOCOL.md',D/'verification.json']
write_json(D/'artifact_manifest.json',{str(p.relative_to(D)):file_sha(p) for p in paths})
print(json.dumps(result,ensure_ascii=False,indent=2))
