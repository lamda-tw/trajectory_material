from pathlib import Path
from collections import defaultdict
import json,time,hashlib
import numpy as np
from transformers import AutoTokenizer
from train import R,read,dump,sha
start=time.monotonic();index=read(R/'data/token_index.json');data=np.memmap(R/'data/tokens.bin',dtype='<i4',mode='r');selected=set(read(R/'data/selected_union.json'));tok=AutoTokenizer.from_pretrained('/root/autodl-tmp/models/Qwen3-8B',local_files_only=True);sources=defaultdict(dict)
for key in selected:
 x=index[key];sources[x['source']][x['step']]=(key,x)
checked=0
for path,targets in sources.items():
 d=read(path);messages=d['initial_messages'].copy()
 for st in d['steps']:
  if st['step'] in targets:
   key,row=targets[st['step']];expected=tok.apply_chat_template(messages,tools=None,tokenize=True,add_generation_prompt=True,enable_thinking=False);assert expected==st['prompt_ids'],key
   assert data[row['offset']:row['offset']+row['prompt_tokens']+row['response_tokens']].tolist()==st['prompt_ids']+st['response_ids'];checked+=1
  messages.append({'role':'assistant','content':st['history_assistant_text']+'\n\n'})
  if not st['code']:break
  messages.append({'role':'user','content':'Output:\n```\n'+st['observation'].rstrip()+'\n```\n\n'})
 if len(sources)>0 and checked%100<30:print('validated',checked,flush=True)
assert checked==len(selected)
for rel,h in read(R/'data/DATA_MANIFEST.json')['artifacts'].items():assert sha(R/rel)==h,rel
for arm in read(R/'config/training.json')['arms']:
 for seed in read(R/'config/training.json')['seeds']:
  folder=R/f'data/{arm}/seed_{seed}';rows=[json.loads(s) for s in (folder/'selection.jsonl').read_text().splitlines()];assert len(rows)==len({r['id'] for r in rows})==1710
  for order in read(folder/'orders.json')['orders']:assert sorted(order)==list(range(1710))
dump(R/'checks/data_validation.json',{'passed':True,'unique_histories_validated':checked,'all_candidate_steps':len(index),'removed_candidate_steps':0,'no_quality_filters':True,'complete_original_responses':True,'no_current_or_future_observation_in_input':True,'wall_seconds':time.monotonic()-start})
print('PASS:',checked,'original histories and target token sequences')
