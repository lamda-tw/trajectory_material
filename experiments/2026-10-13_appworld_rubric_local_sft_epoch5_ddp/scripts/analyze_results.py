"""Post-training/DEV checks and descriptive historical comparisons; no inference."""
from pathlib import Path
from datetime import datetime
from collections import Counter,defaultdict
import csv,hashlib,json,math,random
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,x):(R/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
state=read('STATUS.json');assert state['phase'] in ['runs_complete_awaiting_analysis','complete']
for rel,h in read('EXECUTION_MANIFEST.json')['files'].items():assert sha(R/rel)==h,rel
for rel,h in read('AMENDMENT_01.json')['files'].items():assert sha(R/rel)==h,rel
for rel,h in read('data/DATA_MANIFEST.json')['artifacts'].items():assert sha(R/rel)==h,rel
cfg=read('config/training.json');done=read('training/rubric/COMPLETE.json');hist=read('training/rubric/metrics.json');initial=read('training/rubric/INITIALIZATION.json')
assert done['epochs']==5 and done['updates']==6100 and done['supervised_tokens']==983040 and not done['probe']
assert initial['initial_lora_B_all_zero'] and initial['fresh_base_no_old_adapter'] and initial['same_initial_state_on_both_ranks']
assert len(hist)==6100 and [x['update'] for x in hist]==list(range(1,6101))
assert all(math.isfinite(x['loss']) and math.isfinite(x['grad_norm']) for x in hist)
rows={r['id']:r for r in map(json.loads,(R/'data/rubric_selection.jsonl').read_text().splitlines())};orders=read('data/epoch_orders.json')['orders'];selection=list(rows)
epochs=[]
for epoch in range(1,6):
 h=[x for x in hist if x['epoch']==epoch];assert len(h)==1220
 ids=[i for x in h for i in x['sample_ids']];assert len(ids)==2440 and Counter(ids)==Counter(rows.keys())
 assert ids==[selection[i] for i in orders[epoch-1]]
 assert sum(x['supervised_tokens'] for x in h)==196608
 e=read(f'training/rubric/epoch_{epoch:02d}.json');assert e['ranks_synchronized'];epochs.append(e)
for p,h in done['adapter_files'].items():assert sha(R/'training/rubric/adapter'/p)==h
results={'rubric_epoch5':read('evaluation/rubric/SUMMARY.json'),'rubric_epoch1_new_recipe':read('evaluation/epoch1/SUMMARY.json'),'rubric_epoch3':read('evaluation/epoch3/SUMMARY.json')}
for name,old in [('base','base'),('rubric_epoch1_old_recipe','rubric'),('uniform_epoch1_old_recipe','uniform')]:results[name]=read(f'references/{old}_dev57_summary.json')
new=results['rubric_epoch5'];assert new['phase']=='complete' and new['tasks']==57 and new['policy_id']==done['adapter_files']['adapter_model.safetensors']
checkpoints=read('CHECKPOINTS_135.json')
for ep,key in [(1,'rubric_epoch1_new_recipe'),(3,'rubric_epoch3'),(5,'rubric_epoch5')]:
 c=checkpoints['checkpoints'][str(ep)];assert results[key]['policy_id']==c['adapter_files']['adapter_model.safetensors']
 for n,h in c['adapter_files'].items():assert sha(Path(c['path'])/n)==h
expected=set((R/'config/dev.txt').read_text().split());maps={}
for name,result in results.items():
 maps[name]={x['task_id']:x for x in result['results']};assert set(maps[name])==expected
 for x in result['results']:assert x['tests']>0 and sha(Path(x['source']))==x['sha256']
comparison={}
for name in ['base','rubric_epoch1_old_recipe','uniform_epoch1_old_recipe','rubric_epoch1_new_recipe','rubric_epoch3']:
 a=maps['rubric_epoch5'];b=maps[name];wins=[t for t in expected if a[t]['success'] and not b[t]['success']];losses=[t for t in expected if b[t]['success'] and not a[t]['success']]
 fam=defaultdict(list)
 for t in sorted(expected):fam[t.rsplit('_',1)[0]].append(int(a[t]['success'])-int(b[t]['success']))
 rng=random.Random(20261013);keys=sorted(fam);boot=[]
 for _ in range(20000):
  v=[d for k in rng.choices(keys,k=len(keys)) for d in fam[k]];boot.append(sum(v)/len(v))
 boot.sort();n=len(wins)+len(losses);p=min(1,2*sum(math.comb(n,k) for k in range(min(len(wins),len(losses))+1))/2**n) if n else 1
 comparison[name]={'new_successes':sorted(wins),'regressions':sorted(losses),'delta_tasks':len(wins)-len(losses),'delta_TGC':(len(wins)-len(losses))/57,'descriptive_mcnemar_p':p,'family_bootstrap_95_percent_interval':[boot[499],boot[19499]],'same_continuous_training_run':name in ['rubric_epoch1_new_recipe','rubric_epoch3']}
with (R/'analysis/task_comparison.csv').open('w',newline='') as f:
 out=[{'task_id':t,**{f'{a}_{k}':maps[a][t][k] for a in maps for k in ['success','passes','tests','steps','termination']}} for t in sorted(expected)]
 writer=csv.DictWriter(f,fieldnames=list(out[0]));writer.writeheader();writer.writerows(out)
diagnostics={}
for name,result in results.items():
 rr=result['results'];families=defaultdict(list)
 for x in rr:families[x['task_id'].rsplit('_',1)[0]].append(bool(x['success']))
 diagnostics[name]={'termination_counts':dict(Counter(x['termination'] for x in rr)),'completion_api_but_failed':sum(x['termination']=='completion_api' and not x['success'] for x in rr),'successful_tasks_by_family':{k:sum(v) for k,v in sorted(families.items()) if any(v)},'families_with_any_success':sum(any(v) for v in families.values()),'families_with_all_success':sum(all(v) for v in families.values()),'task_families':len(families)}
dump('analysis/termination_and_family_diagnostics.json',diagnostics)
summary={'checked_at':datetime.now().astimezone().isoformat(),'training':done,'epochs':epochs,'results':{a:{k:v for k,v in d.items() if k!='results'} for a,d in results.items()},'comparisons':comparison,'diagnostics':diagnostics,'all_checks_passed':True,'exactly_five_passes_of_identical_selected_targets':True,'seed_count':1,'same_recipe_uniform_epoch5_available':False,'user_requested_checkpoints':[1,3,5],'new_external_judge_calls':0,'new_training_actions':0}
dump('analysis/summary.json',summary)
import runpy
runpy.run_path(str(R/'scripts/plot_training_loss.py'),run_name='__main__')
print(json.dumps({'results':{a:d['successes'] for a,d in results.items()},'comparisons':comparison,'epochs':epochs},ensure_ascii=False,indent=2))
