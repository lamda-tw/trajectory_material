"""Local-only allowlisting and equality-preserving credential replacement; no network."""
from pathlib import Path
import hashlib,json,re
R=Path(__file__).resolve().parents[1]

def public_prefix(d):
 return {'state_id':d['state']['public_state_id'],'prefix_hash':d['state']['prefix_sha256'],'task':d['public_task'],'agent_instructions':d['agent_instructions'],'history':[{'step':x['step'],'assistant':x['history_assistant_text'],'code':x['code'],'observation':x['observation']} for x in d['history']]}

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
 # API output may print only a scalar password, without a "password:" key.
 # This local registry is used exclusively for replacement, never as evidence.
 task=payload.get('task',{}).get('task_id')
 if task:
  registry=R/'runtime/redaction_credentials'/f'{task}.json'
  assert registry.exists(), 'Local task credential redaction registry missing'
  vals.update(json.loads(registry.read_text()))
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
 return clean,{'credential_values_replaced':sum(any(s in v for v in strings(payload)) for s in vals),'task_password_registry_checked':bool(task),'equality_preserved':True,'not_full_anonymization':True,'hidden_evaluator_included':False,'model_group_or_training_seed_included':False}

