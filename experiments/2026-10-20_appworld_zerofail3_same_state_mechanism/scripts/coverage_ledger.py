"""Mechanical local audit: request parameters and observable IDs, never a completeness oracle."""
from experiment import *
from collections import defaultdict
import re

def decode(x):
 if not isinstance(x,dict):return x
 if set(x)=={'dict'}:
  return {str(decode(k)):decode(v) for k,v in x['dict']}
 for kind in ['list','tuple','set','frozenset']:
  if set(x)=={kind}:return [decode(v) for v in x[kind]]
 return {k:decode(v) for k,v in x.items()}

def json_values(s):
 dec=json.JSONDecoder();i=0
 while i<len(s):
  match=re.search(r'[\[{]',s[i:])
  if not match:break
  begin=i+match.start()
  try:value,end=dec.raw_decode(s,begin);yield value;i=end
  except ValueError:i=begin+1

def ids(value):
 out=defaultdict(set)
 def visit(v):
  if isinstance(v,dict):
   if 'api_name' in v or 'response_schemas' in v:return
   for k,x in v.items():
    if k=='id' or k.endswith('_id') or k.endswith('_ids'):
     for z in (x if isinstance(x,list) else [x]):
      if type(z) in (int,str):out[k].add(str(z))
    if k not in ['password','access_token','refresh_token','api_key','secret_key']:visit(x)
  elif isinstance(v,list):
   for x in v:visit(x)
 visit(value);return {k:sorted(v) for k,v in out.items()}

def save_csv(path,items):
 if not items:return
 fields=list(dict.fromkeys(k for r in items for k in r))
 with path.open('w',newline='') as f:
  wr=csv.DictWriter(f,fieldnames=fields);wr.writeheader();wr.writerows(items)

def main():
 requests=[];collections=[];responses=[];seen_ids=defaultdict(lambda:defaultdict(set));seen_calls=defaultdict(set)
 def record(meta,step):
  for i,request in enumerate(decode(step['actual_requests'])):
   args=request.get('data') or {};args=args if isinstance(args,dict) else {}
   paging={k:v for k,v in args.items() if k in ['page_index','page_limit','cursor','page_token']}
   requests.append(dict(meta,request_index=i,method=request.get('method'),url=request.get('url'),paging_arguments=json.dumps(paging,ensure_ascii=False),object_arguments=json.dumps({k:v for k,v in args.items() if k=='id' or k.endswith('_id') or k.endswith('_ids')},ensure_ascii=False),response_to_request_alignment='see separate API response ledger; validation failures may have no HTTP request'))
  observed=defaultdict(set)
  for value in json_values(step['observation']):
   for k,v in ids(value).items():observed[k].update(v)
  collections.append(dict(meta,evidence_source='printed JSON only; not an exhaustive API response log',observed_ids=json.dumps({k:sorted(v) for k,v in observed.items()},ensure_ascii=False),execution_error=step['observation'].startswith('Execution failed.'),complete_scope='not_inferred'))
  for i,call in enumerate(step.get('local_api_responses',[])):
   args=decode(call['arguments']);paging={k:v for k,v in args.items() if k in ['page_index','page_limit','cursor','page_token']}
   scope={k:v for k,v in args.items() if k not in ['page_index','cursor','page_token','access_token','password','refresh_token','api_key','secret_key']}
   identity=(meta['state_id'],meta['group'],meta['seed'],meta['receiver'],call['app_name'],call['api_name'],digest(scope))
   request_hash=digest(args);repeat=request_hash in seen_calls[identity];seen_calls[identity].add(request_hash)
   body=call.get('response_json');objects=ids(body);new={k:sorted(set(v)-seen_ids[identity][k]) for k,v in objects.items()}
   for k,v in objects.items():seen_ids[identity][k].update(v)
   responses.append(dict(meta,call_index=i,app_name=call['app_name'],api_name=call['api_name'],status=call['status'],http_status=call.get('status_code'),paging_arguments=json.dumps(paging,ensure_ascii=False),scope_hash=identity[-1],response_sha256=digest(body) if 'response_json' in call else '',top_level_list_length=len(body) if isinstance(body,list) else None,returned_ids=json.dumps(objects,ensure_ascii=False),new_ids_within_logged_branch_and_same_query=json.dumps(new,ensure_ascii=False),repeat_request_within_logged_branch=int(repeat),complete_scope='not_inferred',visibility='local response audit; only printed content is visible to policy text or judge'))
 for m in models():
  for p in (R/'results/executions'/model_key(m)).glob('*.json'):
   if any(x in p.name for x in ['.job.','.infrastructure_errors.']):continue
   d=read(p)
   if 'candidate' not in d:continue
   record({'state_id':d['state_id'],'group':m['group'],'seed':m['training_seed'],'receiver':'','followup_step':0},d['candidate'])
   before=ids(decode(d['before']['variables']));after=ids(decode(d['after']['variables']));collections.append({'state_id':d['state_id'],'group':m['group'],'seed':m['training_seed'],'receiver':'','followup_step':0,'evidence_source':'local Python variable audit; may contain unprinted data unavailable to language-model text','before_ids':json.dumps(before,ensure_ascii=False),'after_ids':json.dumps(after,ensure_ascii=False),'new_ids':json.dumps({k:sorted(set(v)-set(before.get(k,[]))) for k,v in after.items()},ensure_ascii=False),'complete_scope':'not_inferred'})
 for p in (R/'results/continuations/continuation').glob('*/*/*.json'):
  if any(x in p.name for x in ['.job.','.errors.','.partial.']):continue
  d=read(p);job=d['job'];group=job['first_model'].split('__seed_')[0]
  record({'state_id':d['state_id'],'group':group,'seed':job['first_seed'],'receiver':job['receiver'],'followup_step':0},d['candidate'])
  for step in d['followup_steps']:record({'state_id':d['state_id'],'group':group,'seed':job['first_seed'],'receiver':job['receiver'],'followup_step':step['followup_step']},step)
 save_csv(R/'analysis/api_request_ledger.csv',requests);save_csv(R/'analysis/visible_collection_ledger.csv',collections);save_csv(R/'analysis/api_response_ledger.csv',responses)
 atomic_json(R/'analysis/coverage_ledger_limits.json',{'request_rows':len(requests),'response_rows':len(responses),'collection_rows':len(collections),'no_total_coverage_rate_inferred':True,'response_limitation':'Passive API wrapper records returned responses and raised exceptions without extra API calls. New IDs are relative to the recorded branch and same query scope, not all historical knowledge. Unprinted responses stay local, unavailable to policy text/judge. Failed requests without a returned response have unknown body. No total completeness is inferred; official requirements provide independent outcome checks.'})
if __name__=='__main__':main()
