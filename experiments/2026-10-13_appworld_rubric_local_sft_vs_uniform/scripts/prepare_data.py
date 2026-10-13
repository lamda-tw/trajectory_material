"""Freeze a task/token-matched comparison using unchanged sampled token IDs."""
from pathlib import Path
from collections import defaultdict,Counter
import hashlib,json,math,random,shutil,array,sys
R=Path(__file__).resolve().parents[1];S=R.parent/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full';OLD=R.parent/'2026-10-08_static_rubric_grpo'
SEED=20261013;BUDGET=196608;TOKENS_PER_UPDATE=4096

def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def jsonl(p,x):p.write_text(''.join(json.dumps(v,ensure_ascii=False)+'\n' for v in x))
rows=[json.loads(x) for x in (R/'data/step_inventory.jsonl').read_text().splitlines()]
pools={a:defaultdict(list) for a in ['rubric','uniform']}
for x in rows:
 if x['common_pool']:pools['uniform'][x['task_id']].append(x)
 if x['rubric_pool']:pools['rubric'][x['task_id']].append(x)
assert set(pools['uniform'])==set(pools['rubric']) and len(pools['rubric'])==90
weights={t:sum(x['response_tokens'] for x in v) for t,v in pools['rubric'].items()};total=sum(weights.values());assert BUDGET<total
quotas={t:BUDGET*n//total for t,n in weights.items()}
for t in sorted(weights,key=lambda t:(-(BUDGET*weights[t]%total),t))[:BUDGET-sum(quotas.values())]:quotas[t]+=1
assert sum(quotas.values())==BUDGET
selected={};summaries={}
for arm in ['rubric','uniform']:
 segments=[];rng=random.Random(SEED+(0 if arm=='rubric' else 1))
 for task in sorted(quotas):
  pool=pools[arm][task].copy();rng.shuffle(pool);remain=quotas[task]
  for x in pool:
   if not remain:break
   count=min(x['response_tokens'],remain);segments.append({'id':x['id'],'task_id':task,'start':0,'end':count});remain-=count
  assert remain==0,task
 rng.shuffle(segments);batches=[];batch=[];remaining=TOKENS_PER_UPDATE
 for seg in segments:
  pos=seg['start']
  while pos<seg['end']:
   end=min(seg['end'],pos+remaining);batch.append({**seg,'start':pos,'end':end});remaining-=end-pos;pos=end
   if remaining==0:batches.append(batch);batch=[];remaining=TOKENS_PER_UPDATE
 assert not batch and len(batches)==48
 selected[arm]=segments;dump(R/f'data/{arm}_schedule.json',{'arm':arm,'seed':SEED,'supervised_tokens':BUDGET,'tokens_per_update':TOKENS_PER_UPDATE,'updates':batches})
 byid={x['id']:x for x in rows};unique=[byid[x['id']] for x in segments]
 summaries[arm]={'selected_steps':len(unique),'task_count':len({x['task_id'] for x in unique}),'supervised_tokens':BUDGET,'optimizer_updates':len(batches),'training_forward_segments':sum(len(b) for b in batches),'forward_input_tokens':sum(byid[x['id']]['prompt_tokens']+x['end'] for b in batches for x in b),'complete_responses_supervised':sum(x['end']==byid[x['id']]['response_tokens'] for x in segments),'partial_final_task_responses':sum(x['end']<byid[x['id']]['response_tokens'] for x in segments),'labels':{f'R{i+1}':dict(Counter(x['labels'][i] for x in unique)) for i in range(8)}}
 jsonl(R/f'data/{arm}_selection.jsonl',[{**x,**{'selected_end':seg['end']}} for seg,x in zip(segments,unique)])
needed={x['id'] for v in selected.values() for x in v};index={};offset=0
assert sys.byteorder=='little'
with (R/'data/tokens.bin').open('wb') as out:
 for sample in json.loads((S/'manifest.json').read_text())['samples']:
  raw=Path(sample['source']).read_bytes();assert hashlib.sha256(raw).hexdigest()==sample['source_sha256']
  d=json.loads(raw)
  for st in d['steps']:
   key=f"{sample['id']}:{st['step']}"
   if key not in needed:continue
   seq=st['prompt_ids']+st['response_ids'];values=array.array('i',seq);assert values.itemsize==4;out.write(values.tobytes())
   index[key]={'offset':offset,'prompt_tokens':len(st['prompt_ids']),'response_tokens':len(st['response_ids']),'source':sample['source'],'step':st['step']}
   offset+=len(seq)
assert set(index)==needed
dump(R/'data/token_index.json',index);dump(R/'data/task_token_quotas.json',quotas)
for n in ['train_all.txt','dev.txt']:
 shutil.copyfile(OLD/'assets/splits'/n,R/'config'/n)
train=set((R/'config/train_all.txt').read_text().split());dev=set((R/'config/dev.txt').read_text().split());assert len(train)==90 and len(dev)==57 and not train&dev and train==set(quotas)
shutil.copyfile(S/'assets/prompt_v5.txt',R/'config/scoring_prompt_v5.txt')
config={'experiment':'rubric-local-sft-vs-task-matched-uniform-v1','base_model':'/root/autodl-tmp/models/Qwen3-8B','initialization':'fresh_identical_LoRA_on_raw_base','seed':SEED,'training_python':str(R.parents[1]/'.conda-training/bin/python'),'supervised_tokens_per_arm':BUDGET,'tokens_per_update':TOKENS_PER_UPDATE,'optimizer_updates':48,'loss':'causal_cross_entropy_on_selected_original_response_token_spans_only','learning_rate':5e-5,'minimum_learning_rate':5e-6,'warmup_updates':4,'scheduler':'linear_warmup_cosine_decay','weight_decay':0.0,'max_grad_norm':1.0,'dtype':'bfloat16','attention':'sdpa','gradient_checkpointing':True,'max_length':32000,'head_chunk_size':128,'lora':{'r':16,'lora_alpha':32,'lora_dropout':0.0,'target_modules':['q_proj','k_proj','v_proj','o_proj','gate_proj','up_proj','down_proj'],'bias':'none','task_type':'CAUSAL_LM'},'evaluation':{'split':'DEV57','tasks':str(R/'config/dev.txt'),'temperature':0.0,'seed':100,'max_steps':50,'max_model_len':32000,'max_new_tokens':3000,'enable_thinking':False,'workers':3,'base_baseline':'fresh_same_protocol','primary_metric':'official_task_goal_completion'},'selection':{'common':'executed_without_exception; one_closed_python_block; no_generation_truncation; no_complete_task; exact_token_pair_deduplicated','rubric':'R1=P AND R2..R6 in {P,N} AND R7=N; R8 recorded but not a hard semantic gate','uniform':'uniform random order without replacement within each task in common pool; same task-specific supervised token quotas','task_quotas':'largest-remainder allocation proportional to rubric-pool response tokens, shared by both arms','official_outcomes_used_for_selection':False,'new_external_model_calls':0,'new_actions':0,'counterfactual_action_swaps':False,'negative_loss':False,'fixed_rubric_weights':False},'scope':'One prespecified selection rule and one initialization seed. DEV57 only evaluated after the two training schedules/configs are frozen; no checkpoint/threshold tuning on DEV57.'}
dump(R/'config/training.json',config)
summary={'token_budget_rationale':'196608 = 48*4096, below 211785 available unique rubric-pool target tokens; no repeated target tokens or manufactured actions','source_score_prompt_version':'v5','source_scoring_dir':str(S),'pool_summary':json.loads((R/'data/inventory_summary.json').read_text()),'arms':summaries,'shared_selected_steps':len({x['id'] for x in selected['rubric']}&{x['id'] for x in selected['uniform']}),'quota_tokens_identical_by_task':True,'all_tokens_original':True,'training_selection_uses_official_outcomes':False,'artifacts':{str(p.relative_to(R)):sha(p) for p in [R/'data/tokens.bin',R/'data/token_index.json',R/'data/rubric_schedule.json',R/'data/uniform_schedule.json',R/'data/task_token_quotas.json',R/'config/training.json',R/'config/dev.txt',R/'config/train_all.txt',R/'config/scoring_prompt_v5.txt']}}
dump(R/'data/DATA_MANIFEST.json',summary)
print(json.dumps({'arms':summaries,'shared_selected_steps':summary['shared_selected_steps'],'tokens_bytes':(R/'data/tokens.bin').stat().st_size},ensure_ascii=False,indent=2))
