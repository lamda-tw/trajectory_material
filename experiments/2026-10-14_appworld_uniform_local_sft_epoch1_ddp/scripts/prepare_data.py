"""Uniform sampling from the frozen common pool; labels/outcomes never enter selection."""
from pathlib import Path
from collections import defaultdict,Counter
import array,hashlib,json,random,sys,time
R=Path(__file__).resolve().parents[1]
def dump(rel,x):(R/rel).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(rel):return json.loads((R/rel).read_text())
cfg=read('config/training.json');reference=[json.loads(s) for s in (R/'references/rubric_selection.jsonl').read_text().splitlines()];inventory=[json.loads(s) for s in (R/'references/source_step_inventory.jsonl').read_text().splitlines()]
pool=defaultdict(list)
for x in inventory:
 if x['common_pool']:pool[x['task_id']].append(x)
counts=Counter(x['task_id'] for x in reference);assert len(counts)==90 and sum(counts.values())==2440 and sum(map(len,pool.values()))==5234
rng=random.Random(cfg['selection_seed']);chosen={}
for task in sorted(counts):
 candidates=sorted(pool[task],key=lambda x:x['id']);assert len(candidates)>=counts[task]
 chosen[task]=iter(rng.sample(candidates,counts[task]))
selected=[]
for slot,ref in enumerate(reference):
 x=dict(next(chosen[ref['task_id']]));x.update(selected_end=x['response_tokens'],matched_reference_index=slot,matched_reference_id=ref['id']);selected.append(x)
assert len({x['id'] for x in selected})==2440 and Counter(x['task_id'] for x in selected)==counts
assert all(x['common_pool'] and not x['mechanical_exclusions'] for x in selected)
(R/'data/uniform_selection.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in selected));dump('data/task_step_quotas.json',dict(sorted(counts.items())))
order=read('references/rubric_epoch_orders.json')['orders'][0];assert sorted(order)==list(range(2440));dump('data/epoch_orders.json',{'method':'Exact reference epoch1 permutation; selected row slots retain reference task identities; two ranks stride without padding','orders':[order]})
assert [selected[i]['task_id'] for i in order]==[reference[i]['task_id'] for i in order]
by_source=defaultdict(list)
for x in selected:by_source[x['source']].append(x)
index={};offset=0;assert sys.byteorder=='little'
with (R/'data/tokens.bin').open('wb') as out:
 for path,rows in sorted(by_source.items()):
  raw=Path(path).read_bytes();h=hashlib.sha256(raw).hexdigest();assert all(x['source_sha256']==h for x in rows);d=json.loads(raw);steps={st['step']:st for st in d['steps']}
  for row in sorted(rows,key=lambda x:x['step']):
   st=steps[row['step']];a,b=st['prompt_ids'],st['response_ids'];assert len(a)==row['prompt_tokens'] and len(b)==row['response_tokens'];assert hashlib.sha256(json.dumps([a,b],separators=(',',':')).encode()).hexdigest()==row['exact_token_pair_sha256']
   seq=array.array('i',a+b);assert seq.itemsize==4;out.write(seq.tobytes());index[row['id']]={'offset':offset,'prompt_tokens':len(a),'response_tokens':len(b),'source':path,'step':st['step']};offset+=len(seq)
assert len(index)==2440;dump('data/token_index.json',index)
total=sum(x['selected_end'] for x in selected);cfg.update(supervised_tokens_per_epoch=total,total_supervised_tokens=total);dump('config/training.json',cfg)
train=set((R/'config/train_all.txt').read_text().split());dev=set((R/'config/dev.txt').read_text().split());assert train==set(counts) and len(dev)==57 and not train&dev and not {x.rsplit('_',1)[0] for x in train}&{x.rsplit('_',1)[0] for x in dev}
summary={'selection_seed':cfg['selection_seed'],'training_seed':cfg['seed'],'selected_steps':2440,'tasks':90,'common_pool_steps':5234,'supervised_tokens':total,'input_tokens':sum(x['prompt_tokens']+x['selected_end']-1 for x in selected),'full_responses':2440,'reference_supervised_tokens':sum(x['selected_end'] for x in reference),'reference_partial_responses':sum(x['selected_end']<x['response_tokens'] for x in reference),'shared_selected_steps':len({x['id'] for x in selected}&{x['id'] for x in reference}),'source_trajectories_represented':len(by_source),'max_sequence':max(x['prompt_tokens']+x['selected_end'] for x in selected),'per_task_counts_identical':True,'per_update_task_pairs_identical':True,'uniform_without_replacement_within_task':True,'labels_used_for_selection':False,'official_outcomes_used_for_selection':False,'labels_post_selection_only':{f'R{i+1}':dict(Counter(x['labels'][i] for x in selected)) for i in range(8)}}
dump('data/SELECTION_SUMMARY.json',summary)
paths=[p for folder in ['data','references'] for p in (R/folder).iterdir() if p.is_file()]+[R/'config/training.json',R/'config/dev.txt',R/'config/train_all.txt']
dump('data/DATA_MANIFEST.json',{'method':'task-step-matched uniform control; original full responses','scope':'matched steps and updates, not matched supervised tokens or masks','artifacts':{str(p.relative_to(R)):sha(p) for p in paths}})
print(json.dumps(summary,ensure_ascii=False,indent=2))
