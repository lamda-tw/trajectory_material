from pathlib import Path
from collections import Counter,defaultdict
import csv,json,hashlib,array,random,sys,time
R=Path(__file__).resolve().parents[1];W=R.parents[1]
def dump(p,x):
 p=R/p;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
sys.path.insert(0,str(W/'plans/2026-10-12_appworld_step_rubric'))
from prepare_input_v3 import prepare
cfg=json.loads((R/'config/training.json').read_text());source=W/'experiments/2026-10-13_appworld_step_rubric_v6_language_prep/full_gpt61_sol'
assert sha(R/'config/scoring_prompt_v6_en_format.txt')==sha(source/'assets/prompt_v6_en.txt')=='df4e8fb406551f2d90e38bbe83838db181bda18e01d947b236ee10a05c633109'
labels=list(csv.DictReader((R/'references/step_labels.csv').open()));labelmap={(x['id'],int(x['step'])):x for x in labels};assert len(labelmap)==11254
manifest=json.loads((R/'references/source_manifest.json').read_text());assert len(manifest['samples'])==540
rows=[];index={};offset=0;source_hashes={};assert sys.byteorder=='little'
with (R/'data/tokens.bin').open('wb') as f:
 for entry in manifest['samples']:
  path=Path(entry['source']);assert sha(path)==entry['source_sha256'];source_hashes[str(path)]=entry['source_sha256'];d=json.loads(path.read_text());assert d['job']['policy_id'].startswith('base:')
  score_input=json.loads((source/entry['input']).read_text());assert sha(source/entry['input'])==entry['input_sha256'];assert len(score_input['steps'])==len(d['steps']);assert prepare(d,score_input['trajectory_id'])==score_input
  for st,si in zip(d['steps'],score_input['steps']):
   assert st['step']==si['id'];lab=labelmap[(entry['id'],st['step'])];a=st['prompt_ids'];b=st['response_ids'];assert a and b and len(a)+len(b)<=cfg['max_length']
   pattern=''.join(lab[f'R{i}'] for i in range(1,9));key=f"{entry['id']}:{st['step']}"
   row={'id':key,'trajectory_id':entry['id'],'task_id':entry['task_id'],'step':st['step'],'source':str(path),'labels':pattern,'P':pattern.count('P'),'F':pattern.count('F'),'U':pattern.count('U'),'prompt_tokens':len(a),'response_tokens':len(b),'selected_end':len(b),'exact_token_pair_sha256':hashlib.sha256(json.dumps([a,b],separators=(',',':')).encode()).hexdigest()};rows.append(row)
   index[key]={'offset':offset,'prompt_tokens':len(a),'response_tokens':len(b),'source':str(path),'step':st['step']};f.write(array.array('i',a+b).tobytes());offset+=len(a)+len(b)
assert len(rows)==11254
pred={'random':lambda r:True,'net3':lambda r:r['P']-r['F']>=3,'pass4':lambda r:r['P']>=4,'zerofail3':lambda r:r['F']==0 and r['P']>=3,'highfail3':lambda r:r['F']>=3}
pools={a:[r for r in rows if fn(r)] for a,fn in pred.items()};q=Counter(r['task_id'] for r in pools['zerofail3']);assert sum(q.values())==1710 and len(q)==90
summaries={};union=set()
for seed in cfg['seeds']:
 for arm in cfg['arms']:
  rng=random.Random(int(hashlib.sha256(f'{seed}:{arm}:selection'.encode()).hexdigest()[:16],16));by=defaultdict(list)
  for r in pools[arm]:by[r['task_id']].append(r)
  selected=[];short={}
  for task,n in sorted(q.items()):
   candidates=sorted(by[task],key=lambda r:r['id']);selected+=rng.sample(candidates,min(n,len(candidates)))
   if len(candidates)<n:short[task]={'target':n,'available':len(candidates),'deficit':n-len(candidates)}
  ids={r['id'] for r in selected};remaining=sorted([r for r in pools[arm] if r['id'] not in ids],key=lambda r:r['id']);fill=1710-len(selected);selected+=rng.sample(remaining,fill);selected.sort(key=lambda r:(r['task_id'],r['id']));assert len(selected)==len({r['id'] for r in selected})==1710
  union.update(r['id'] for r in selected);run=f'{arm}/seed_{seed}';folder=R/'data'/run;folder.mkdir(parents=True,exist_ok=True);(folder/'selection.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected));orders=[]
  for epoch in range(1,cfg['epochs']+1):
   o=list(range(1710));random.Random(seed+epoch*100000).shuffle(o);orders.append(o)
  dump(f'data/{run}/orders.json',{'orders':orders})
  actual=Counter(r['task_id'] for r in selected)
  summaries[run]={'candidate_count':len(pools[arm]),'selected_steps':1710,'selected_tasks':len(actual),'supervised_tokens':sum(r['response_tokens'] for r in selected),'input_tokens':sum(r['prompt_tokens']+r['response_tokens']-1 for r in selected),'max_sequence':max(r['prompt_tokens']+r['response_tokens'] for r in selected),'with_F':sum(r['F']>0 for r in selected),'with_U':sum(r['U']>0 for r in selected),'shortfall_tasks':short,'redistributed_steps':fill,'actual_task_quotas':dict(sorted(actual.items())),'task_quota_L1_distance':sum(abs(actual[t]-q[t]) for t in q)}
dump('data/token_index.json',index);dump('data/target_task_quotas.json',q);dump('data/SELECTION_SUMMARY.json',summaries);dump('references/source_hashes.json',source_hashes);dump('data/selected_union.json',sorted(union))
(R/'data/step_inventory.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
train=set((R/'config/train_all.txt').read_text().split());dev=set((R/'config/dev.txt').read_text().split());assert train==set(q) and len(dev)==57 and not {t.rsplit('_',1)[0] for t in train}&{t.rsplit('_',1)[0] for t in dev}
dump('data/DATA_MANIFEST.json',{'source':'raw Qwen3-8B 540 trajectories, English v6 format labels','legacy_source_manifest_prompt_field':'Inherited v5 provenance metadata only; actual score version verified using v6 asset hash and judge config; no v5 labels used','all_steps':len(rows),'selected_union':len(union),'mechanical_quality_filters':False,'artifacts':{str(p.relative_to(R)):sha(p) for name in ['config','data','references'] for p in (R/name).rglob('*') if p.is_file() and p.name!='DATA_MANIFEST.json'}})
print(json.dumps({'all_steps':len(rows),'unique_selected':len(union),'candidates':{k:len(v) for k,v in pools.items()},'runs':len(summaries)},indent=2))
