from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime
import csv,hashlib,json,math,random
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def dump(p,x):(R/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
assert read('STATUS.json')['phase'] in ['runs_complete_awaiting_analysis','complete']
for m in ['EXECUTION_MANIFEST.json','data/DATA_MANIFEST.json']:
 d=read(m)
 for p,h in d.get('files',d.get('artifacts',{})).items():assert sha(R/p)==h,p
cfg=read('config/training.json');done=read('training/uniform/COMPLETE.json');hist=read('training/uniform/metrics.json');init=read('training/uniform/INITIALIZATION.json');refinit=read('references/rubric_initialization.json')
assert done['epochs']==1 and done['updates']==1220 and not done['probe'] and len(hist)==1220
assert init['initial_lora_B_all_zero'] and init['fresh_base_no_old_adapter'] and init['same_initial_state_on_both_ranks'] and init['initial_adapter_tensor_sha256']==refinit['initial_adapter_tensor_sha256']
assert all(math.isfinite(x['loss']) and math.isfinite(x['grad_norm']) for x in hist)
rows=[json.loads(x) for x in (R/'data/uniform_selection.jsonl').read_text().splitlines()];refs=[json.loads(x) for x in (R/'references/rubric_selection.jsonl').read_text().splitlines()];order=read('data/epoch_orders.json')['orders'][0];refhist=read('references/rubric_training_metrics.json')[:1220];refmap={x['id']:x for x in refs};m={x['id']:x for x in rows}
assert Counter(x['task_id'] for x in rows)==Counter(x['task_id'] for x in refs)
assert [x['update'] for x in hist]==list(range(1,1221))
assert [i for x in hist for i in x['sample_ids']]==[rows[i]['id'] for i in order]
assert Counter(i for x in hist for i in x['sample_ids'])==Counter(m.keys())
for a,b in zip(hist,refhist):assert [m[i]['task_id'] for i in a['sample_ids']]==[refmap[i]['task_id'] for i in b['sample_ids']]
assert sum(x['supervised_tokens'] for x in hist)==done['supervised_tokens']==cfg['total_supervised_tokens']
assert sum(x['input_tokens'] for x in hist)==read('data/SELECTION_SUMMARY.json')['input_tokens']
assert read('training/uniform/epoch_01.json')['ranks_synchronized'] and read('MODEL_VERIFICATION.json')['phase']=='passed'
rc=read('references/rubric_training.json')
for key in ['base_model','seed','learning_rate','scheduler','optimizer','weight_decay','gradient_clipping','dtype','attention','gradient_checkpointing','max_length','head_chunk_size','loss_reduction','lora','world_size','per_gpu_batch_size','global_batch_size','updates_per_epoch','samples_per_epoch']:assert cfg[key]==rc[key],key
new_eval=read('config/eval_uniform.json');old_eval=read('references/rubric_eval_epoch1.json')
for key in ['agent','evaluation','worker_count']:assert new_eval[key]==old_eval[key],key
results={'random_epoch1':read('evaluation/uniform/SUMMARY.json'),'rubric_epoch1':read('references/rubric_epoch1_dev57.json'),'base':read('references/base_dev57.json')};tasks=set((R/'config/dev.txt').read_text().split());maps={}
assert results['random_epoch1']['policy_id']==done['adapter_files']['adapter_model.safetensors']
for name,d in results.items():
 assert d['phase']=='complete' and d['tasks']==57;maps[name]={x['task_id']:x for x in d['results']};assert set(maps[name])==tasks
 for x in d['results']:assert x['tests']>0 and sha(x['source'])==x['sha256']
comp={}
for name in ['rubric_epoch1','base']:
 a=maps['random_epoch1'];b=maps[name];wins=sorted(t for t in tasks if a[t]['success'] and not b[t]['success']);losses=sorted(t for t in tasks if b[t]['success'] and not a[t]['success']);families=defaultdict(list)
 for t in sorted(tasks):families[t.rsplit('_',1)[0]].append(int(a[t]['success'])-int(b[t]['success']))
 rng=random.Random(20261014);keys=sorted(families);boot=[]
 for _ in range(20000):
  v=[x for k in rng.choices(keys,k=len(keys)) for x in families[k]];boot.append(sum(v)/len(v))
 boot.sort();n=len(wins)+len(losses);p=min(1,2*sum(math.comb(n,k) for k in range(min(len(wins),len(losses))+1))/2**n) if n else 1
 comp[name]={'direction':'random minus reference','new_successes':wins,'regressions':losses,'delta_tasks':len(wins)-len(losses),'delta_TGC':(len(wins)-len(losses))/57,'descriptive_mcnemar_p':p,'task_family_bootstrap_95_interval':[boot[499],boot[19499]]}
diagnostics={}
for name,d in results.items():
 rr=d['results'];families=defaultdict(list)
 for x in rr:families[x['task_id'].rsplit('_',1)[0]].append(x['success'])
 diagnostics[name]={'termination_counts':dict(Counter(x['termination'] for x in rr)),'completion_api_but_failed':sum(x['termination']=='completion_api' and not x['success'] for x in rr),'successful_tasks_by_family':{k:sum(v) for k,v in sorted(families.items())},'families_with_any_success':sum(any(v) for v in families.values())}
with (R/'analysis/task_comparison.csv').open('w',newline='') as f:
 out=[{'task_id':t,**{f'{a}_{k}':maps[a][t][k] for a in maps for k in ['success','passes','tests','steps','termination']}} for t in sorted(tasks)];w=csv.DictWriter(f,fieldnames=list(out[0]));w.writeheader();w.writerows(out)
summary={'checked_at':datetime.now().astimezone().isoformat(),'all_checks_passed':True,'training':done,'epoch':read('training/uniform/epoch_01.json'),'selection':read('data/SELECTION_SUMMARY.json'),'results':{n:{k:v for k,v in d.items() if k!='results'} for n,d in results.items()},'comparisons':comp,'diagnostics':diagnostics,'control_checks':{'identical_initial_LoRA':True,'identical_per_update_task_pairs':True,'identical_train_hyperparameters':True,'identical_DEV_protocol':True,'no_old_adapter_resume':True,'one_pass_exactly':True},'limitations':['One sampling seed and one training seed','Epoch1 chosen after prior DEV inspection; exploratory comparison','Step/update matched, not token/context/mask matched; rubric includes 88 partial targets','Task quotas derived from rubric arm; conditional task-matched baseline','No isolation of individual rubric dimensions']}
dump('analysis/summary.json',summary);print(json.dumps({'successes':{n:d['successes'] for n,d in results.items()},'comparisons':comp},ensure_ascii=False,indent=2))
