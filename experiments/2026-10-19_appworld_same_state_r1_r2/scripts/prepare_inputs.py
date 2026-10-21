"""Freeze allowlisted prefixes and re-tokenize with the original local tokenizer (CPU)."""
from pathlib import Path
import csv,json,sys
R=Path(__file__).resolve().parents[1];W=R.parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha
from transformers import AutoTokenizer
T=AutoTokenizer.from_pretrained('/root/autodl-tmp/models/Qwen3-8B',local_files_only=True)
audit=json.loads((R/'plan_snapshot/same_state_audit.json').read_text())
formal=list(csv.DictReader((R/'plan_snapshot/states_selected.csv').open()))
inv={x['state_id']:x for x in csv.DictReader((R/'plan_snapshot/state_inventory.csv').open())}
pilot=[dict(inv[s],panel='pilot',temporal_band='') for s in audit['pilot_state_ids']]
for row in formal+pilot:
 src=W/row['source'];assert file_sha(src)==row['source_sha256'];t=json.loads(src.read_text());k=int(row['before_step']);prefix=[{z:s[z] for z in ['step','code','observation','history_assistant_text']} for s in t['steps'][:k-1]]
 messages=[dict(m) for m in t['initial_messages']]
 for s in prefix:
  messages.append({'role':'assistant','content':s['history_assistant_text']+'\n\n'})
  if s['code']:messages.append({'role':'user','content':'Output:\n```\n'+s['observation'].rstrip()+'\n```\n\n'})
 ids=T.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False)
 assert ids==t['steps'][k-1]['prompt_ids'],row['state_id']
 assert digest(ids)==row['prompt_ids_sha256'] and digest(messages)==row['messages_sha256'] and digest(prefix)==row['prefix_evidence_sha256']
 key=row['state_id'].replace(':','__')
 d={'state':row,'messages':messages,'prompt_ids':ids,'public_task':t['public_task'],'agent_instructions':t['initial_messages'],'history':prefix}
 atomic_json(R/'inputs'/f'{key}.json',d)
 if row['panel']=='pilot':
  # Original current action is only retained in a separate calibration fixture.
  s=t['steps'][k-1];atomic_json(R/'calibration/raw/original_actions'/f'{key}.json',{z:s[z] for z in ['text','code','observation']})
atomic_json(R/'config/input_audit.json',{'formal_states':len(formal),'pilot_states':len(pilot),'all_prompt_tokens_exact':True,'inputs':{p.name:file_sha(p) for p in sorted((R/'inputs').glob('*.json'))}})
print('Token equality verified for 299 formal + 8 independent pilot states.',flush=True)
