"""Local-only allowlisting and equality-preserving credential replacement; no network."""
from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[1]

def public_prefix(d):
 return {'state_id':d['state']['state_id'],'prefix_hash':d['state']['prefix_evidence_sha256'],'task':d['public_task'],'agent_instructions':d['agent_instructions'],'history':[{'step':x['step'],'assistant':x['history_assistant_text'],'code':x['code'],'observation':x['observation']} for x in d['history']]}

def strings(x):
 if isinstance(x,str):yield x
 elif isinstance(x,list):
  for v in x:yield from strings(v)
 elif isinstance(x,dict):
  for v in x.values():yield from strings(v)

# Preserve equality across prefix, card, code and observation. Hash-based placeholders
# are stable if a later candidate introduces another token; no mapping file leaves machine.
def sanitize(payload):
 pat=re.compile(r'''["'](?:(?:new_|old_|current_)?password|access_token|refresh_token|api_key|secret_key)["']\s*:\s*["']([^"'\n]+)["']''')
 kw=re.compile(r'''\b(?:[A-Za-z_]\w*_)?(?:password|access_token|refresh_token|api_key|secret_key)\s*=\s*["']([^"'\n]+)["']''')
 jwt=re.compile(r'\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b')
 vals=set()
 for s in strings(payload):
  vals.update(m.group(1) for p in (pat,kw) for m in p.finditer(s));vals.update(jwt.findall(s))
 vals={s for s in vals if s not in ('','string','...') and not s.startswith('<CREDENTIAL_')}
 mapping={s:'<CREDENTIAL_'+hashlib.sha256(s.encode()).hexdigest()[:24]+'>' for s in vals}
 ordered=sorted(mapping,key=len,reverse=True)
 def redact(x):
  if isinstance(x,str):
   for secret in ordered:x=x.replace(secret,mapping[secret])
   return x
  if isinstance(x,list):return [redact(v) for v in x]
  if isinstance(x,dict):return {k:redact(v) for k,v in x.items()}
  return x
 clean=redact(payload)
 # Validate replacement at string level (JSON escaping can otherwise obscure a leak).
 assert all(not any(s in v for v in strings(clean)) for s in vals)
 assert not any(jwt.search(v) for v in strings(clean))
 return clean,{'credential_values_replaced':len(vals),'equality_preserved':True,'not_full_anonymization':True,'hidden_evaluator_included':False,'model_group_or_training_seed_included':False}

if __name__=='__main__':
 out=R/'calibration/public_scoring_preview';out.mkdir(parents=True,exist_ok=True);rows=[]
 for sid in json.loads((R/'plan_snapshot/same_state_audit.json').read_text())['pilot_state_ids']:
  key=sid.replace(':','__');d=json.loads((R/'inputs'/f'{key}.json').read_text());payload=public_prefix(d);payload['candidate']=json.loads((R/'calibration/raw/original_actions'/f'{key}.json').read_text());clean,audit=sanitize(payload);p=out/f'{key}.json';p.write_text(json.dumps(clean,ensure_ascii=False,indent=2)+'\n');rows.append({'file':p.name,'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),**audit})
 manifest={'status':'local_preview_only_no_external_calls','destination_if_authorized':'existing Codex login / OpenAI GPT-6.1-sol high, tools disabled','contents':'AppWorld public task and protocol, prior assistant code and feedback, current calibration action and immediate feedback; credentials replaced; task entities retained','excludes':['hidden tests/answers','official outcomes','model group/seed','future trajectory','workspace files outside allowlist'],'rows':rows}
 (out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'prepared':len(rows),'credentials_replaced':sum(x['credential_values_replaced'] for x in rows),'external_calls':0}))
