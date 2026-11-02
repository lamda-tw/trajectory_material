"""CPU-only paired official-check, action and configuration analysis; no model calls."""
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime
import ast, csv, hashlib, json, re

O=Path(__file__).resolve().parent
B=O.parents[1]; R=B.parent
ROOTS={'mixed':R/'phase_b/runs/mixed','sdpo':R/'phase_b_sdpo_only/runs/sdpo','sft':B/'runs/sft'}

def read(p):return json.loads(p.read_text())
def write(n,v):(O/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
def csvwrite(n,rows):
 with (O/n).open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def action(s):
 code=(s.get('code') or '').strip()
 try:
  tree=ast.parse(code);sig=ast.dump(tree,include_attributes=False)
  nodes=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and ast.unparse(n.func).startswith('apis.')]
 except SyntaxError:sig=code;nodes=[]
 calls=[ast.unparse(n.func) for n in nodes]
 docs=bool(calls) and all(n.startswith('apis.api_docs.') for n in calls)
 nondoc=any(not n.startswith('apis.api_docs.') for n in calls)
 business=any(not n.startswith(('apis.api_docs.','apis.supervisor.')) and n.rsplit('.',1)[-1] not in ('login','logout') for n in calls)
 # Publish docs calls and API names only: never include credentials or user profile literals.
 detail=[]
 for n in nodes:
  name=ast.unparse(n.func)
  if name.startswith('apis.api_docs.'):
   args={kw.arg:kw.value.value for kw in n.keywords if kw.arg in ('app_name','api_name') and isinstance(kw.value,ast.Constant)}
   detail.append(name+str(args))
  else:detail.append(name)
 return dict(signature=sig,docs=docs,nondoc=nondoc,business=business,calls=calls,action='; '.join(detail) or 'no_static_api_call')
def report_parse(p):
 parsed={}
 for m in re.finditer(r'>> (Passed|Failed) Requirement\n(.*?)(?=>> (?:Passed|Failed) Requirement|\Z)',p.read_text(),re.S):
  desc=m[2].split('```')[0]
  desc=' '.join(l.strip() for l in desc.splitlines() if not l.startswith('─') and l.strip()!='None').strip()
  desc=' '.join(desc.split())
  if desc=='assert user_id to message mapping from notifications match private_data.venmo_user_id_to_notification_messages':
   assert m[1]=='Failed'
   identity=re.findall(r'(venmo_user_id_to_notification_(?:messages|payment_request_ids)) =',m[2].split('```python',1)[1]);assert len(identity)==1
   desc+=' [code: '+identity[0]+']'
  assert desc and desc not in parsed,(p,desc)
  parsed[desc]=m[1]=='Passed'
 return parsed

checks=[]; rows=[]; schemas={}; actions_out=[]; input_hashes={}; task_text={}
for arm,root in ROOTS.items():
 for ep in (1,2):
  folder=root/f'epoch_{ep:02d}_dev57';summ=read(folder/'summary.json');input_hashes[str((folder/'summary.json').relative_to(R))]=sha(folder/'summary.json')
  for item in summ['results']:
   task=item['task_id'];p=folder/'trajectories'/f'{task}.json';t=read(p)
   report=Path(t['job']['runtime'])/'experiments/outputs'/t['job']['episode_id']/'tasks'/task/'evaluation/report.md'
   pp=report_parse(report);assert len(pp)==item['num_tests'] and sum(pp.values())==item['num_passes']
   if task in schemas:assert schemas[task]==set(pp)
   schemas[task]=set(pp)
   input_hashes[str(report.relative_to(R))]=sha(report)
   for desc,passed in pp.items():checks.append(dict(arm=arm,epoch=ep,task_id=task,family=task.rsplit('_',1)[0],requirement=desc,passed=int(passed),source=str(report.relative_to(R))))
   seq=[action(s) for s in t['steps']];seen=set();repeat=0;docrepeat=0;groups=[];streak=0;longest=0;last=None
   for s,a in zip(t['steps'],seq):
    rep=bool((s.get('code') or '').strip()) and a['signature'] in seen
    repeat+=rep;docrepeat+=rep and a['docs'];seen.add(a['signature'])
    streak=streak+1 if a['docs'] and a['signature']==last else int(a['docs']);longest=max(longest,streak);last=a['signature'] if a['docs'] else None
    # Run lengths based on the complete AST, even when rendered action labels omit arguments.
    if groups and a['signature']==groups[-1]['signature']:groups[-1]['end']=s['step'];groups[-1]['count']+=1
    else:groups.append(dict(start=s['step'],end=s['step'],count=1,action=a['action'],signature=a['signature']))
   c=Counter(a['action'] for a in seq if a['docs'])
   row=dict(arm=arm,epoch=ep,**item,family=task.rsplit('_',1)[0],docs=sum(a['docs'] for a in seq),repeated_docs=docrepeat,repeated_code=repeat,non_doc_steps=sum(a['nondoc'] for a in seq),business_code_steps=sum(a['business'] for a in seq),longest_docs=longest,report=str(report.relative_to(R)),trajectory=str(p.relative_to(R)))
   rows.append(row)
   task_text[task]=t['initial_messages'][-1]['content'].split('Task:',1)[-1].strip()
   for g in groups:g.pop('signature')
   actions_out.append(dict(arm=arm,epoch=ep,task_id=task,task=task_text[task],groups=groups,top_docs=c.most_common(3),checks=pp,**{k:row[k] for k in ('steps','termination','num_tests','num_passes','docs','repeated_docs','non_doc_steps','business_code_steps','longest_docs','trajectory','report')}))

lookup={(x['arm'],x['epoch'],x['task_id'],x['requirement']):x['passed'] for x in checks}
rowmap={(x['arm'],x['epoch'],x['task_id']):x for x in rows}
pairs=[];pair_summary={}
for la,le,ra,re_ in [('mixed',1,'mixed',2),('sdpo',1,'sdpo',2),('sft',1,'sft',2)]+[(a,e,'sft',e) for e in (1,2) for a in ('mixed','sdpo')]:
 label=f'{ra}{re_}_vs_{la}{le}';group=[]
 for task in sorted(schemas):
  a=rowmap[la,le,task];b=rowmap[ra,re_,task]
  gains=sum(lookup[ra,re_,task,q]>lookup[la,le,task,q] for q in schemas[task]);losses=sum(lookup[ra,re_,task,q]<lookup[la,le,task,q] for q in schemas[task])
  r=dict(comparison=label,task_id=task,gains=gains,losses=losses,net=gains-losses,success_gained=int(b['success'] and not a['success']),success_lost=int(a['success'] and not b['success']),both_fail=not a['success'] and not b['success'],macro_delta=(b['num_passes']-a['num_passes'])/b['num_tests'])
  group.append(r);pairs.append(r)
 pair_summary[label]=dict(gained_success=[x['task_id'] for x in group if x['success_gained']],lost_success=[x['task_id'] for x in group if x['success_lost']],more_checks=sum(x['net']>0 for x in group),fewer_checks=sum(x['net']<0 for x in group),same_checks=sum(x['net']==0 for x in group),gained_checks=sum(x['gains'] for x in group),lost_checks=sum(x['losses'] for x in group),both_fail_tasks=sum(x['both_fail'] for x in group),both_fail_net_checks=sum(x['net'] for x in group if x['both_fail']))

groups={}
for arm in ROOTS:
 groups[arm]={}
 for ep in (1,2):
  rr=[x for x in rows if x['arm']==arm and x['epoch']==ep];loop=[x for x in rr if x['longest_docs']>=5]
  groups[arm][ep]=dict(passes=sum(x['num_passes'] for x in rr),tests=sum(x['num_tests'] for x in rr),zero=sum(x['num_passes']==0 for x in rr),partial=sum(0<x['num_passes']<x['num_tests'] for x in rr),full=sum(x['success'] for x in rr),successful_families=sorted({x['family'] for x in rr if x['success']}),non_doc_tasks=sum(x['non_doc_steps']>0 for x in rr),business_code_tasks=sum(x['business_code_steps']>0 for x in rr),business_code_steps=sum(x['business_code_steps'] for x in rr),only_docs_tasks=sum(x['docs']==x['steps'] for x in rr),loop_tasks=[x['task_id'] for x in loop],loop_repeat_docs=sum(x['repeated_docs'] for x in loop),false_completion_tasks=[x['task_id'] for x in rr if x['termination']=='completion_api' and not x['success']],context_or_step_limit=sum(x['termination'] in ('context_limit','step_limit') for x in rr))
familyrows=[]
for fam in sorted({x['family'] for x in rows}):
 d={'family':fam,'task_example':task_text[fam+'_1']}
 for arm in ROOTS:
  for ep in (1,2):
   rr=[x for x in rows if x['arm']==arm and x['epoch']==ep and x['family']==fam]
   d[f'{arm}{ep}_successes']=sum(x['success'] for x in rr);d[f'{arm}{ep}_passes']=sum(x['num_passes'] for x in rr);d[f'{arm}{ep}_macro']=sum(x['num_passes']/x['num_tests'] for x in rr)/3
 familyrows.append(d)

# Verify frozen configs and compare experimental parameters and task schedules.
config_audit={'manifests':{},'shared':{}}
for arm,root in ROOTS.items():
 p=root.parents[1]/'config/preparation_manifest.json';m=read(p);n=0
 for rel,h in m['files'].items():
  fp=R/rel;assert sha(fp)==h,fp;n+=1
 config_audit['manifests'][arm]={'entries_checked':n,'manifest_sha256':sha(p)}
configs={a:read(p.parents[1]/'config/run.json') for a,p in ROOTS.items()}
for key in ('training','agent','sampling','collection'):
 entries={a:{k:v for k,v in c[key].items() if k!='tasks'} for a,c in configs.items()}
 assert entries['mixed']==entries['sdpo']==entries['sft'],(key,entries)
 config_audit['shared'][key]=entries['sft']
for file in ('train90.txt','dev57.txt','schedule.json'):
 vals={a:sha(p.parents[1]/'config'/file) for a,p in ROOTS.items()};assert len(set(vals.values()))==1,(file,vals);config_audit['shared'][file]=vals['sft']

# Characterize exactly which online steps were selected for loss.
selected=[]
for arm,root in ROOTS.items():
 agg=defaultdict(Counter)
 for num in range(1,37):
  epoch=(num-1)//18+1;folder=root/f'batch_{num:03d}';data=read(folder/'dataset.json');collection=read(folder/'collection.json')
  trajectories={x['id']:read(folder/x['path']) for x in collection['trajectories']}
  for ex in data['examples']:
   s=trajectories[ex['trajectory_id']]['steps'][ex['step']-1];assert s['step']==ex['step'];a=action(s)
   c=agg[epoch,ex['branch']];c['steps']+=1;c['docs_only']+=a['docs'];c['non_doc_steps']+=a['nondoc'];c['business_code_steps']+=a['business'];c['R6_fail']+=ex['labels'][5]=='F';c['contains_U']+='U' in ex['labels'];c['response_tokens']+=len(ex['response_ids'])
 for (ep,br),c in agg.items():selected.append(dict(arm=arm,epoch=ep,branch=br,**c))

csvwrite('official_checks.csv',checks);csvwrite('paired_checks.csv',pairs);csvwrite('families.csv',familyrows);csvwrite('dev_detailed.csv',rows);csvwrite('selected_training_steps.csv',selected)
write('details_summary.json',{'groups':groups,'paired':pair_summary,'selected':selected,'official_reports':len(rows),'checks_per_evaluation':sum(map(len,schemas.values()))})
write('case_actions.json',actions_out);write('configuration_audit.json',config_audit);write('input_hashes.json',input_hashes)
print(json.dumps({'groups':groups,'paired':pair_summary,'selected':selected},ensure_ascii=False,indent=2))
