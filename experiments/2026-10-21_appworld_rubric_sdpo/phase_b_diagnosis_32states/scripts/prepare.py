"""Freeze train-only states and export an existing EMA adapter; no model inference/updates."""
from pathlib import Path
import sys,csv,collections,shutil
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from common import read,write_json,frozen_json,digest,now
from a_common import file_sha
from analyze_sources import render_message
from validate_v7_feedback import feedback_text
from transformers import AutoTokenizer
B=R/'phase_b';cfg=read(B/'config/run.json');tok=AutoTokenizer.from_pretrained(cfg['paths']['base_model'],local_files_only=True)
rows=list(csv.DictReader((B/'analysis/failure_diagnosis/training_step_features.csv').open()))
pools=collections.defaultdict(list)
for x in rows:
 if int(x['step'])>35 or int(x['prompt_tokens'])>22000:continue
 l=x['labels'];kind=None
 if l[5]=='F' and x['repeat_docs_literal']=='True':kind='R6'
 elif l[0]=='F' and l[5]!='F' and x['traceback']=='True':kind='R1'
 elif l[7]=='F' and l[0]!='F' and l[5]!='F' and x['business_non_auth_step']=='True':kind='R8'
 elif x['branch']=='sft' and x['business_non_auth_step']=='True' and 'U' not in l and x['repeat_code']!='True':kind='clean'
 if kind:pools[kind,int(x['epoch'])].append(x)
# Scarcer clean/epoch2 strata first. Unique task across the entire panel, no outcome-based selection.
selected=[];used=set()
for kind in ['clean','R8','R1','R6']:
 for epoch in [2,1]:
  ranked=sorted(pools[kind,epoch],key=lambda x:digest([20261024,kind,epoch,x['trajectory_id'],int(x['step'])]))
  count=0
  for x in ranked:
   if x['task_id'] in used:continue
   selected.append((kind,x));used.add(x['task_id']);count+=1
   if count==4:break
  assert count==4,(kind,epoch,count)
manifest=[];cache={};train=set((B/'config/train90.txt').read_text().split());dev=set((B/'config/dev57.txt').read_text().split())
for kind,x in sorted(selected,key=lambda z:(z[0],int(z[1]['epoch']),z[1]['trajectory_id'])):
 folder=B/'runs/mixed'/f"batch_{int(x['batch']):03d}";tid=x['trajectory_id'];step=int(x['step'])
 source=folder/'trajectories'/(tid+'.json');judge=folder/'judging'/tid/'judgement.json';dataset=folder/'dataset.json'
 tr=read(source);j=read(judge);e=next(e for e in read(dataset)['examples'] if e['trajectory_id']==tid and e['step']==step)
 f=next((f for f in j['feedback'] if f['step_id']==step),None);old=tr['steps'][step-1]
 messages=list(tr['initial_messages'])
 for h in tr['steps'][:step-1]:
  messages.append({'role':'assistant','content':h['history_assistant_text']+'\n\n'})
  if h['code']:messages.append({'role':'user','content':'Output:\n```\n'+h['observation'].rstrip()+'\n```\n\n'})
 ids=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False)
 assert ids==e['prompt_ids']==old['prompt_ids']
 c2=None
 if kind!='clean':
  assert f and f['usable'] and e['branch']=='sdpo'
  c2=render_message('C2_feedback',f['failed_rules'],feedback_text(f),'')
  q=tok.apply_chat_template(messages+[{'role':'user','content':c2}],tokenize=True,add_generation_prompt=True,enable_thinking=False)
  assert q==e['teacher_prompt_ids']
 assert x['task_id'] in train and x['task_id'] not in dev
 ident=f"{kind}_{tid}_s{step:02d}"
 package={'id':ident,'stratum':kind,'epoch':int(x['epoch']),'batch':int(x['batch']),'task_id':x['task_id'],'target_step':step,
 'features':x,'labels':e['labels'],'feedback':f,'messages':messages,'c2_message':c2,'example':e,
 'history':tr['steps'][:step-1],'original':old,'source':str(source),'source_sha256':file_sha(source),
 'judgment':str(judge),'judgment_sha256':file_sha(judge),'dataset_sha256':file_sha(dataset)}
 path=D/'states'/(ident+'.json');frozen_json(path,package)
 manifest.append({'id':ident,'stratum':kind,'epoch':int(x['epoch']),'task_id':x['task_id'],'target_step':step,'path':str(path),'sha256':file_sha(path)})
cfg['server'].update(port=8194,adapter_name='diagnostic-adapter');cfg['evaluation'].update(temperature=0.0,seed=100)
frozen_json(D/'config/runtime.json',cfg)
frozen_json(D/'config/authorization.json',{'physical_gpu':1,'gpu_uuid':cfg['server']['gpu'],'inference':True,'environment_replay':True,'training':False,'optimizer_steps':0,'new_codex_calls':False,'source':'User requested fixed-state 32 diagnosis with GPU1 and existing feedback.'})
frozen_json(D/'config/manifest.json',{'seed':20261024,'selection':'sha256 ranking within 4 strata x 2 source epochs; four states per cell; task unique globally; clean,R8,R1,R6 and epoch2,epoch1 priority; target step<=35; prompt<=22000; no outcome-based reselection',
 'pool_counts':{f'{k[0]}_epoch{k[1]}':len(v) for k,v in pools.items()},'states':manifest,
 'arms':{'base':['C0','C2_FAIL_only'],'ema36':['C0','C2_FAIL_only'],'student36':['C0']},
 'actions_per_branch':4,'feedback_first_action_only':True,'parameter_updates':0,'greedy':True,'count':len(manifest)})
import torch
from safetensors.torch import load_file,save_file
checkpoint=B/'runs/mixed/batch_036/checkpoint';state=torch.load(checkpoint/'state.pt',map_location='cpu',weights_only=False)
safe=load_file(str(checkpoint/'adapters/student/adapter_model.safetensors'))
assert safe.keys()==state['student'].keys()==state['teacher'].keys()
assert all(torch.equal(safe[k],state['student'][k]) for k in safe)
out=D/'models/ema36';out.mkdir(parents=True,exist_ok=True)
if not (out/'adapter_model.safetensors').exists():
 save_file({k:v.contiguous() for k,v in state['teacher'].items()},str(out/'adapter_model.safetensors'))
 shutil.copy2(checkpoint/'adapters/student/adapter_config.json',out/'adapter_config.json')
export=load_file(str(out/'adapter_model.safetensors'));assert all(torch.equal(export[k],state['teacher'][k]) for k in export)
frozen_json(D/'config/model_provenance.json',{'base':cfg['paths']['base_model'],'ema36':str(out),'student36':str(checkpoint/'adapters/student'),
 'checkpoint_sha256':file_sha(checkpoint/'state.pt'),'ema_adapter_sha256':file_sha(out/'adapter_model.safetensors'),'student_adapter_sha256':file_sha(checkpoint/'adapters/student/adapter_model.safetensors'),
 'optimizer_updates_already_in_source':state['optimizer_updates'],'new_updates':0,'ema_export_exact_fp32':True})
print({'states':len(manifest),'by_stratum':dict(collections.Counter(x['stratum'] for x in manifest)),'prompt_tokens_range':[min(len(read(x['path'])['example']['prompt_ids']) for x in manifest),max(len(read(x['path'])['example']['prompt_ids']) for x in manifest)]})
