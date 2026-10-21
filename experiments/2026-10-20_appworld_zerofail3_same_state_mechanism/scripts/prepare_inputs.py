"""CPU-only input and identity validation. No sampling, environment execution, or scoring."""
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import csv,json,sys
R=Path(__file__).resolve().parents[1];W=R.parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha
from progress import update

def main():
 update('输入与权重核验','开始只读SHA256和138个状态的逐token核验，GPU保持未使用。')
 protocol=json.loads((R/'plan_snapshot/protocol_manifest.json').read_text())
 for v in protocol['dependency_files'].values():
  p=Path(v['path']);assert file_sha(p if p.is_absolute() else W/p)==v['sha256'],v['path']
 source=json.loads((R/'plan_snapshot/source_manifest.json').read_text())
 for p,h in source['summaries'].items():assert file_sha(W/p)==h
 for v in source['trajectories']:assert file_sha(W/v['source'])==v['sha256']
 models=json.loads((R/'plan_snapshot/models.json').read_text())['models']
 for m in models:
  p=W/m['adapter'];assert file_sha(p)==m['adapter_sha256'];assert file_sha(p.parent/'adapter_config.json')==m['adapter_config_sha256']
  m['alias']='checkpoint_'+digest(['20261020:blind_checkpoint',m['group'],m['training_seed']])[:12]
 atomic_json(R/'config/model_aliases_researcher_only.json',models)
 base=Path('/root/autodl-tmp/models/Qwen3-8B');weight_index=json.loads((base/'model.safetensors.index.json').read_text());files=sorted(set(weight_index['weight_map'].values()))
 with ThreadPoolExecutor(max_workers=2) as pool:hashes=dict(zip(files,pool.map(lambda f:file_sha(base/f),files)))
 atomic_json(R/'config/base_identity.json',{'path':str(base),'recorded_before_loading':True,'shards':hashes,'limitation':'Current full base identity recorded; old experiments did not provide a prior full-shard hash for retrospective comparison.'})
 from transformers import AutoTokenizer
 tokenizer=AutoTokenizer.from_pretrained(str(base),local_files_only=True)
 formal=list(csv.DictReader((R/'plan_snapshot/states_selected.csv').open()));pilot=list(csv.DictReader((R/'plan_snapshot/calibration_states.csv').open()));cache={}
 for n,row in enumerate(formal+pilot,1):
  src=W/row['source']
  if str(src) not in cache:cache[str(src)]=json.loads(src.read_text())
  t=cache[str(src)];k=int(row['before_step']);prefix=[{z:s[z] for z in ['step','code','observation','history_assistant_text']} for s in t['steps'][:k-1]]
  messages=[dict(m) for m in t['initial_messages']]
  for s in prefix:
   messages.append({'role':'assistant','content':s['history_assistant_text']+'\n\n'})
   if s['code']:messages.append({'role':'user','content':'Output:\n```\n'+s['observation'].rstrip()+'\n```\n\n'})
  ids=tokenizer.apply_chat_template(messages,tools=None,tokenize=True,add_generation_prompt=True,enable_thinking=False)
  assert ids==t['steps'][k-1]['prompt_ids'],row['state_id']
  assert digest(ids)==row['prompt_ids_sha256'] and digest(messages)==row['messages_sha256']
  assert digest({'task':t['public_task'],'initial_messages':t['initial_messages'],'history':prefix})==row['prefix_sha256']
  key=row['state_id'].replace(':','__');d={'state':row,'messages':messages,'prompt_ids':ids,'public_task':t['public_task'],'agent_instructions':t['initial_messages'],'history':prefix}
  atomic_json(R/'inputs'/f'{key}.json',d)
  if n%20==0:update('输入与权重核验',f'{n}/138状态逐token匹配；9权重、513源轨迹和完整基座权重已核验。',completed=n,total=138)
 atomic_json(R/'config/input_audit.json',{'formal_states':len(formal),'pilot_states':len(pilot),'all_prompt_tokens_exact':True,'models_verified':9,'sources_verified':513,'inputs':{p.name:file_sha(p) for p in sorted((R/'inputs').glob('*.json'))}})
 from public_payload import public_prefix,sanitize
 manifest=[]
 for row in pilot:
  d=json.loads((R/'inputs'/f"{row['state_id'].replace(':','__')}.json").read_text());clean,redaction=sanitize(public_prefix(d));p=R/'calibration/public_scoring_preview'/f"{row['public_state_id']}.json";atomic_json(p,clean);manifest.append({'file':p.name,'sha256':file_sha(p),**redaction})
 atomic_json(R/'calibration/public_scoring_preview/MANIFEST.json',{'status':'local_preview_only','destination':'OpenAI GPT-6.1-sol/high via existing Codex login, all tools disabled','included':'Public task, initial agent protocol, prior assistant text/code/feedback; candidates will use same allowlist with actual code/feedback only','excluded':['hidden tests/answers','future original actions','model group and training seed','workspace contents outside allowlist'],'rows':manifest})
 update('输入与权重核验','138/138状态逐token完全一致；9个adapter、513条源轨迹、完整基座SHA256核验完成；9份脱敏公开预览已生成。','complete',completed=138,total=138)
if __name__=='__main__':main()
