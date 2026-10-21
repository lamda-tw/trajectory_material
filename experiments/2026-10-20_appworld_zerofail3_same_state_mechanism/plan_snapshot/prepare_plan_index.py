"""Standard-library-only, read-only experiment audit; writes planning metadata only.
Never imports AppWorld, torch, transformers or judge clients. Never executes trajectory code.
"""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,ast,csv,hashlib,json,re
HERE=Path(__file__).resolve().parent;W=HERE.parents[1]
OLD=W/'experiments/2026-10-16_appworld_rubric_selection_ablation'
GROUPS=['random','net3','zerofail3'];SEEDS=[20261015,20261016,20261017]
SALT='20261020:zerofail_same_state_v1'

def digest(v):return hashlib.sha256(json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def rank(domain,r):return hashlib.sha256((SALT+':'+domain+'|'+r['state_id']).encode()).hexdigest()
def json_values(text):
 decoder=json.JSONDecoder();i=0
 while i<len(text):
  m=re.search(r'[\[{]',text[i:])
  if not m:break
  j=i+m.start()
  try:v,end=decoder.raw_decode(text,j);yield v;i=end
  except ValueError:i=j+1

def specs(text):
 out={}
 def visit(v):
  if isinstance(v,dict):
   if {'app_name','api_name','parameters','response_schemas'}<=v.keys() and isinstance(v['parameters'],list):out[(v['app_name'],v['api_name'])]=v
   else:
    for x in v.values():visit(x)
  elif isinstance(v,list):
   for x in v:visit(x)
 for v in json_values(text):visit(v)
 return out

def calls(code):
 try:t=ast.parse(code)
 except SyntaxError:return [],False
 out=[]
 for n in ast.walk(t):
  if not isinstance(n,ast.Call):continue
  f=n.func
  if isinstance(f,ast.Attribute) and isinstance(f.value,ast.Attribute) and isinstance(f.value.value,ast.Name) and f.value.value.id=='apis':
   kw={}
   for k in n.keywords:
    if k.arg:
     try:kw[k.arg]=ast.literal_eval(k.value)
     except (ValueError,TypeError):pass
   out.append((f.value.attr,f.attr,kw))
 return out,any(isinstance(n,(ast.For,ast.While,ast.AsyncFor)) for n in ast.walk(t))

def inventory():
 rows=[];sources=[];models=[];tasks=set();summary_files={}
 for group in GROUPS:
  for seed in SEEDS:
   train=OLD/f'training/{group}/seed_{seed}';epoch=json.loads((train/'epoch_01.json').read_text());assert epoch['samples']==1710 and epoch['updates']==855
   adapter=train/'epoch_01_adapter/adapter_model.safetensors';assert sha(adapter)==epoch['adapter_files']['adapter_model.safetensors']
   models.append({'group':group,'training_seed':seed,'samples':1710,'epochs':1,'updates':855,'adapter':str(adapter.relative_to(W)),'adapter_sha256':sha(adapter),'adapter_config_sha256':sha(adapter.parent/'adapter_config.json'),'inference_gpu':1})
   summaryp=OLD/f'evaluation/{group}/seed_{seed}/epoch_01/SUMMARY.json';summary=json.loads(summaryp.read_text());summary_files[str(summaryp.relative_to(W))]=sha(summaryp)
   assert len(summary['results'])==57
   for item in sorted(summary['results'],key=lambda x:x['task_id']):
    src=Path(item['source']);assert sha(src)==item['sha256'];trace=json.loads(src.read_text());task=trace['public_task']['task_id'];tasks.add(task)
    assert trace['job']['policy_id']==models[-1]['adapter_sha256'] and trace['job']['seed']==100
    initial=trace['initial_messages'];messages=[dict(m) for m in initial];history=[];known={}
    for msg in initial:known.update(specs(msg['content']))
    previous=None;previous_calls=[];previous_full={};previous_loop=False;codes=[]
    coverage_word=bool(re.search(r'\b(all|every|each|total|most|maximum|longest|highest|largest|sum)\b|how many',trace['public_task']['instruction'],re.I))
    for i,step in enumerate(trace['steps']):
     assert step['step']==i+1
     # Only prompt IDs of the current action are read; never its output or outcome.
     flags=[];paging=[];subtype='';last_error=bool(previous and previous['observation'].startswith('Execution failed.'))
     if previous:
      non_docs=[(a,b,kw) for a,b,kw in previous_calls if a!='api_docs']
      # C: known paging contract plus task wording suggesting a complete-set requirement.
      if coverage_word and not last_error:
       paged_full=[(a,b) for (a,b),v in previous_full.items() if any(p.get('name') in ['page_index','page_token','cursor'] for p in v['parameters'])]
       paged_reads=[(a,b) for a,b,kw in non_docs if (a,b) in known and any(p.get('name') in ['page_index','page_token','cursor'] for p in known[a,b]['parameters'])]
       visible_nonempty_list=any(isinstance(v,list) and len(v)>0 for v in json_values(previous['observation']))
       if paged_full:subtype='paging_spec_available';paging=paged_full;flags.append('C')
       elif paged_reads and not previous_loop and visible_nonempty_list:subtype='visible_nonempty_single_page';paging=paged_reads;flags.append('C')
      if previous_full and not last_error:flags.append('B')
      summary_calls=[kw.get('app_name') for a,b,kw in previous_calls if a=='api_docs' and b=='show_api_descriptions' and isinstance(kw.get('app_name'),str)]
      first_summary=bool(summary_calls and previous['code'].strip() not in codes[:-1] and not last_error)
      missing_failed_spec=bool(last_error and any((a,b) not in known for a,b,kw in non_docs) and re.search(r'No API named|401|422|TypeError|unexpected keyword|missing.*argument',previous['observation'],re.I))
      if first_summary or missing_failed_spec:flags.append('A')
     # Priority makes mechanical panels disjoint; semantic eligibility is judged later, before candidates.
     stage='C' if 'C' in flags else 'B' if 'B' in flags else 'A' if 'A' in flags else ''
     prefix_sha=digest({'task':trace['public_task'],'initial_messages':initial,'history':history})
     row={'state_id':f'{group}:seed_{seed}:{task}:before_step_{i+1:02d}','task_id':task,'family':task.rsplit('_',1)[0],'source_group':group,'source_training_seed':seed,'source':str(src.relative_to(W)),'source_sha256':item['sha256'],'before_step':i+1,'prefix_steps':i,'prefix_execute_calls':sum(bool(x['code']) for x in history),'prompt_tokens':len(step['prompt_ids']),'prompt_ids_sha256':digest(step['prompt_ids']),'messages_sha256':digest(messages),'prefix_sha256':prefix_sha,'mechanical_stage':stage,'all_stage_flags':','.join(sorted(flags)),'paging_subtype':subtype,'paging_apis':','.join(a+'.'+b for a,b in paging),'previous_execution_error':last_error,'remaining_interactions_after_candidate':49-i,'response_budget':min(3000,32000-len(step['prompt_ids']))}
     assert row['response_budget']>0;rows.append(row)
     # Advance only after indexing this action-before state.
     previous={k:step[k] for k in ['step','code','observation','history_assistant_text']};history.append(previous);codes.append(previous['code'].strip());previous_calls,previous_loop=calls(previous['code']);previous_full=specs(previous['observation']) if not previous['observation'].startswith('Execution failed.') else {};known.update(previous_full)
     messages.append({'role':'assistant','content':previous['history_assistant_text']+'\n\n'})
     if previous['code']:messages.append({'role':'user','content':'Output:\n```\n'+previous['observation'].rstrip()+'\n```\n\n'})
    sources.append({'group':group,'seed':seed,'task_id':task,'source':str(src.relative_to(W)),'sha256':item['sha256'],'states':len(trace['steps'])})
 assert len(tasks)==57 and len(sources)==513 and len(models)==9
 return rows,sources,models,summary_files

def write_csv(name,rows):
 if not rows:return
 with (HERE/name).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def select_states(rows):
 used=set();anchor=[];focused=[];pilot=[];continuation=[]
 families=sorted({r['family'] for r in rows},key=lambda f:hashlib.sha256((SALT+':family|'+f).encode()).hexdigest())
 def choose(pool,domain,task_counts,family_counts,seed_counts):
  eligible=[r for r in pool if r['prefix_sha256'] not in used]
  assert eligible,('Insufficient frozen candidate capacity',domain)
  selected=min(eligible,key=lambda r:(task_counts[r['task_id']],family_counts[r['family']],seed_counts[r['source_training_seed']],rank(domain,r)))
  used.add(selected['prefix_sha256']);task_counts[selected['task_id']]+=1;family_counts[selected['family']]+=1;seed_counts[selected['source_training_seed']]+=1
  return selected
 # 57 task anchors: one task per cell, Latin assignment balances source groups/seeds.
 for fi,family in enumerate(families):
  tasks=sorted({r['task_id'] for r in rows if r['family']==family});assert len(tasks)==3
  for ti,task in enumerate(tasks):
   group=GROUPS[(fi+ti)%3];seed=SEEDS[(fi+2*ti)%3]
   pool=[r for r in rows if r['task_id']==task and r['source_group']==group and r['source_training_seed']==seed]
   r=choose(pool,'anchor',Counter(),Counter(),Counter());anchor.append(dict(r,panel='anchor'))
 # Three diagnostic panels; round-robin source quota 8, diversity before seeded hash.
 for stage in ['A','B','C']:
  tc=Counter();fc=Counter();sc={g:Counter() for g in GROUPS}
  for slot in range(8):
   subtype=('visible_nonempty_single_page' if slot%2==0 else 'paging_spec_available') if stage=='C' else None
   for group in GROUPS:
    pool=[r for r in rows if r['source_group']==group and r['mechanical_stage']==stage and (subtype is None or r['paging_subtype']==subtype)]
    r=choose(pool,'focus_'+stage,tc,fc,sc[group]);focused.append(dict(r,panel='focus_'+stage))
 # Calibration states excluded from every formal prefix (including exact cross-source duplicates).
 for stage in ['A','B','C']:
  for gi,group in enumerate(GROUPS):
   pool=[r for r in rows if r['source_group']==group and r['mechanical_stage']==stage]
   if stage=='C':pool=[r for r in pool if r['paging_subtype']==('visible_nonempty_single_page' if gi%2==0 else 'paging_spec_available')]
   r=choose(pool,'calibration_'+stage,Counter(),Counter(),Counter());pilot.append(dict(r,panel='calibration_'+stage))
 # Follow-up is a preselected formal subset; no generated actions/ratings can affect it.
 chosen=set();tc=Counter();fc=Counter()
 for stage in ['A','B','C']:
  for group in GROUPS:
   for slot in range(2):
    pool=[r for r in focused if r['mechanical_stage']==stage and r['source_group']==group and r['before_step']<=38 and r['state_id'] not in chosen]
    if stage=='C':pool=[r for r in pool if r['paging_subtype']==('visible_nonempty_single_page' if slot==0 else 'paging_spec_available')]
    assert pool,('Insufficient continuation budget cell',stage,group,slot)
    r=min(pool,key=lambda r:(tc[r['task_id']],fc[r['family']],rank('continuation',r)))
    continuation.append(dict(r,followup_calls_per_controller=12));chosen.add(r['state_id']);tc[r['task_id']]+=1;fc[r['family']]+=1
 assert len(anchor)==57 and len(focused)==72 and len(pilot)==9 and len(continuation)==18
 assert len({r['prefix_sha256'] for r in anchor+focused+pilot})==138
 # Separate, explicitly outcome-informed discovery-family bridge. Never pool into the core 18.
 bridge=[]
 for group in ['net3','zerofail3']:
  pool=[r for r in focused if r['mechanical_stage']=='C' and r['source_group']==group and r['family']=='d4e9306' and r['before_step']<=38 and r['state_id'] not in chosen]
  assert pool,('Missing prespecified d4e9306 bridge',group)
  r=min(pool,key=lambda r:rank('discovery_bridge',r));bridge.append(dict(r,followup_calls_per_controller=12))
 return anchor,focused,pilot,continuation,bridge

def describe(rows):
 return {'states':len(rows),'tasks':len({r['task_id'] for r in rows}),'families':len({r['family'] for r in rows}),'source_groups':dict(Counter(r['source_group'] for r in rows)),'source_seeds':dict(Counter(str(r['source_training_seed']) for r in rows)),'paging_subtypes':dict(Counter(r['paging_subtype'] for r in rows if r['paging_subtype'])),'prompt_tokens_max':max(r['prompt_tokens'] for r in rows),'prompt_tokens_mean':sum(r['prompt_tokens'] for r in rows)/len(rows),'long_context_over_29000':sum(r['prompt_tokens']>29000 for r in rows),'prefix_execute_calls_one_copy':sum(r['prefix_execute_calls'] for r in rows),'before_step_max':max(r['before_step'] for r in rows)}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--write-plan-index',action='store_true',required=True);p.add_argument('--reuse-verified-inventory',action='store_true');args=p.parse_args()
 if args.reuse_verified_inventory:
  previous_audit=json.loads((HERE/'selection_audit.json').read_text())
  assert sha(HERE/'state_inventory.csv')==previous_audit['files']['state_inventory.csv']
  rows=list(csv.DictReader((HERE/'state_inventory.csv').open()))
  for r in rows:
   for k in ['source_training_seed','before_step','prefix_steps','prefix_execute_calls','prompt_tokens','remaining_interactions_after_candidate','response_budget']:r[k]=int(r[k])
   r['previous_execution_error']=r['previous_execution_error']=='True'
  saved=json.loads((HERE/'source_manifest.json').read_text());sources=saved['trajectories'];summaries=saved['summaries'];models=json.loads((HERE/'models.json').read_text())['models']
  for src in sources:assert sha(W/src['source'])==src['sha256']
  for m in models:assert sha(W/m['adapter'])==m['adapter_sha256']
 else:
  rows,sources,models,summaries=inventory();write_csv('state_inventory.csv',rows);dump(HERE/'source_manifest.json',{'summaries':summaries,'trajectories':sources});dump(HERE/'models.json',{'status':'plan_only_not_authorized','models':models})
 capacities={g:{s:{'occurrences':sum(r['source_group']==g and r['mechanical_stage']==s for r in rows),'unique_prefixes':len({r['prefix_sha256'] for r in rows if r['source_group']==g and r['mechanical_stage']==s}),'tasks':len({r['task_id'] for r in rows if r['source_group']==g and r['mechanical_stage']==s}),'families':len({r['family'] for r in rows if r['source_group']==g and r['mechanical_stage']==s})} for s in ['A','B','C']} for g in GROUPS}
 for r in rows:r['public_state_id']='state_'+r['prefix_sha256'][:20]
 write_csv('state_inventory.csv',rows)
 anchor,focused,pilot,continuation,bridge=select_states(rows);formal=anchor+focused
 for r in continuation:r['continuation_panel']='core'
 for r in bridge:r['continuation_panel']='discovery_bridge'
 all_continuation=continuation+bridge
 write_csv('states_selected.csv',formal);write_csv('calibration_states.csv',pilot);write_csv('continuation_states.csv',all_continuation)
 # Store all provenance occurrences for selected identical prefixes without duplicating observations.
 selected_prefix={r['prefix_sha256']:r['state_id'] for r in formal+pilot};provenance=defaultdict(list)
 for r in rows:
  if r['prefix_sha256'] in selected_prefix:provenance[selected_prefix[r['prefix_sha256']]].append(r['state_id'])
 dump(HERE/'selected_prefix_provenance.json',dict(provenance))
 budget={'formal_states':129,'calibration_states':9,'models':9,'formal_first_actions':1161,'calibration_model_actions_max':27,'calibration_continuation_calls_max':27,'continuation_core_states':18,'continuation_discovery_states':2,'continuation_states_total':20,'continuation_first_action_variants':180,'continuation_controller_policies':3,'continuation_branches':540,'max_followup_calls_per_branch':12,'formal_continuation_calls_max':6480,'all_model_calls_max':7695,'formal_card_calls':129,'formal_action_judges_max':1161,'formal_repeat_judges':54,'calibration_judges_max_two_drafts':72,'external_judge_requests_max_before_transport_retries':1416,'formal_before_evaluations':129,'formal_after_first_evaluations':1161,'formal_followup_evaluations_max':1080,'formal_evaluator_runs_max':2370,'phase1_prefix_execute_calls_reference_plus_nine_models':10*sum(r['prefix_execute_calls'] for r in formal),'phase2_prefix_execute_calls_naive':27*sum(r['prefix_execute_calls'] for r in all_continuation),'phase2_first_action_replays':540}
 audit={'status':'plan_only_not_authorized','sampling_salt':SALT,'candidate_occurrences':len(rows),'unique_prefixes':len({r['prefix_sha256'] for r in rows}),'capacities':capacities,'models_verified':9,'trajectory_hashes_verified':513,'anchor':describe(anchor),'focused':{s:describe([r for r in focused if r['mechanical_stage']==s]) for s in ['A','B','C']},'formal':describe(formal),'calibration':describe(pilot),'continuation_core':describe(continuation),'continuation_discovery':describe(bridge),'continuation':describe(all_continuation),'budget':budget,'physical_gpu':1,'gpu_uuid':'GPU-35170b76-56ce-240a-19c0-0c092a3e8501','no_generation':True,'no_training':True,'no_replay':True,'no_judge_calls':True,'not_yet_verified':['prompt_retokenization','environment_replay','semantic_opportunity_labels','judge_calibration','continuation_executor'],'files':{n:sha(HERE/n) for n in ['state_inventory.csv','states_selected.csv','calibration_states.csv','continuation_states.csv','models.json','source_manifest.json']}}
 dump(HERE/'selection_audit.json',audit);print(json.dumps({k:audit[k] for k in ['status','candidate_occurrences','anchor','focused','formal','calibration','continuation','budget']},ensure_ascii=False))
if __name__=='__main__':main()
