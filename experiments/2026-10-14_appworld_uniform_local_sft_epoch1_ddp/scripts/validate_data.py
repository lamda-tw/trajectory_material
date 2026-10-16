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

rows=[json.loads(x) for x in (R/'data/uniform_selection.jsonl').read_text().splitlines()];order=read('data/epoch_orders.json')['orders'][0];cfg=read('config/training.json')
assert checked==len(rows)==2440 and len(order)==2440 and sorted(order)==list(range(2440))
assert len(set(order[0::2])&set(order[1::2]))==0
assert sum(rows[i]['selected_end'] for i in order)==cfg['total_supervised_tokens']
for x in rows:assert x['selected_end']==index[x['id']]['response_tokens']
for rel,h in read('data/DATA_MANIFEST.json')['artifacts'].items():assert hashlib.sha256((R/rel).read_bytes()).hexdigest()==h,rel
result={'phase':'passed','selected_histories_checked':checked,'all_original_history_tokens_match':True,'all_original_response_tokens_match':True,'no_current_or_future_observation_in_prompt':True,'epochs':1,'updates':1220,'no_sampler_padding_or_repeated_target':True,'wall_seconds':time.time()-start}
(R/'data/VALIDATION.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))
