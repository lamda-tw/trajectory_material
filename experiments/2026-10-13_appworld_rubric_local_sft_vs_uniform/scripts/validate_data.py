"""Verify selected input histories, source targets, disjoint splits and loss budgets."""
from pathlib import Path
from collections import defaultdict
import hashlib,json,numpy as np,time
from transformers import AutoTokenizer
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
index=read('data/token_index.json');data=np.memmap(R/'data/tokens.bin',dtype='<i4',mode='r')
tokenizer=AutoTokenizer.from_pretrained('/root/autodl-tmp/models/Qwen3-8B',local_files_only=True)
sources=defaultdict(dict)
for key,row in index.items():sources[row['source']][row['step']]=(key,row)
checked=0;start=time.time()
for path,selected in sources.items():
 d=json.loads(Path(path).read_text());messages=d['initial_messages'].copy()
 for st in d['steps']:
  if st['step'] in selected:
   key,row=selected[st['step']];expected=tokenizer.apply_chat_template(messages,tools=None,tokenize=True,add_generation_prompt=True,enable_thinking=False)
   assert expected==st['prompt_ids'],('history_mismatch',key)
   saved=data[row['offset']:row['offset']+row['prompt_tokens']+row['response_tokens']].tolist()
   assert saved==st['prompt_ids']+st['response_ids'],('target_rewrite',key)
   checked+=1
  messages.append({'role':'assistant','content':st['history_assistant_text']+'\n\n'})
  if not st['code']:break
  messages.append({'role':'user','content':'Output:\n```\n'+st['observation'].rstrip()+'\n```\n\n'})
quotas=read('data/task_token_quotas.json');arms={}
for arm in ['rubric','uniform']:
 sched=read(f'data/{arm}_schedule.json');bytask=defaultdict(int);spans=defaultdict(list)
 for batch in sched['updates']:
  assert sum(x['end']-x['start'] for x in batch)==4096
  for x in batch:
   assert 0<=x['start']<x['end']<=index[x['id']]['response_tokens'];bytask[x['task_id']]+=x['end']-x['start'];spans[x['id']].append((x['start'],x['end']))
 for key,v in spans.items():
  end=0
  for a,b in sorted(v):assert a==end,(key,v);end=b
 assert dict(bytask)==quotas and len(sched['updates'])==48
 arms[arm]={'unique_selected_steps':len(spans),'supervised_tokens':sum(bytask.values()),'no_repeated_target_token':True,'task_quotas_verified':True}
result={'phase':'passed','selected_histories_checked':checked,'all_original_history_tokens_match':True,'all_original_response_tokens_match':True,'no_current_or_future_observation_in_prompt':True,'arms':arms,'wall_seconds':time.time()-start}
(R/'data/VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
