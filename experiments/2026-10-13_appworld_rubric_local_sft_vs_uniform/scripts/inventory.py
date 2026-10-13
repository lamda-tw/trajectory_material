"""Read existing trajectories/labels only; no inference, rewriting or training."""
from pathlib import Path
import ast,collections,hashlib,json,re
R=Path(__file__).resolve().parents[1]
S=R.parent/'2026-10-13_appworld_qwen3_8b_step_rubric_v5_full'
def sha(b):return hashlib.sha256(b).hexdigest()
manifest=json.loads((S/'manifest.json').read_text())['samples']
rows=[];seen={};reasons=collections.Counter()
for sample in manifest:
 raw=Path(sample['source']).read_bytes();assert sha(raw)==sample['source_sha256']
 d=json.loads(raw);j=json.loads((S/'runs/scoring'/sample['id']/'judgement.json').read_text());labels={x[0]:x[1] for x in j['steps']}
 for st in d['steps']:
  lab=labels[st['step']];why=[]
  blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',st['text'],re.S|re.I)
  if not st['code'].strip():why.append('no_code')
  if st['observation'].startswith('Execution failed.'):why.append('execution_failed')
  if len(blocks)!=1:why.append('not_one_closed_python_block')
  if st['finish_reason']!='stop':why.append('truncated_generation')
  if len(st['prompt_ids'])+len(st['response_ids'])>32000:why.append('over_context')
  try:
   tree=ast.parse(st['code'])
   if any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='complete_task' for n in ast.walk(tree)):why.append('completion_submission')
  except SyntaxError:why.append('syntax_error')
  key=sha(json.dumps([st['prompt_ids'],st['response_ids']],separators=(',',':')).encode())
  duplicate=seen.get(key)
  if duplicate:why.append('exact_duplicate')
  else:seen[key]=f"{sample['id']}:{st['step']}"
  core=(lab[0]=='P' and lab[6]=='N' and all(c in 'PN' for c in lab[1:6]))
  row={'id':f"{sample['id']}:{st['step']}",'trajectory_id':sample['id'],'task_id':sample['task_id'],'step':st['step'],'source':sample['source'],'source_sha256':sample['source_sha256'],'labels':lab,'prompt_tokens':len(st['prompt_ids']),'response_tokens':len(st['response_ids']),'mechanical_exclusions':why,'common_pool':not why,'rubric_pool':not why and core,'exact_token_pair_sha256':key,'duplicate_of':duplicate}
  rows.append(row);reasons.update(why)
(R/'data/step_inventory.jsonl').write_text(''.join(json.dumps(x,ensure_ascii=False)+'\n' for x in rows))
summary={'all_steps':len(rows),'source_trajectories':len(manifest),'exclusions_nonexclusive':dict(reasons),'pools':{}}
for flag in ['common_pool','rubric_pool']:
 a=[x for x in rows if x[flag]]
 summary['pools'][flag]={'steps':len(a),'tasks':len({x['task_id'] for x in a}),'response_tokens':sum(x['response_tokens'] for x in a),'prompt_tokens':sum(x['prompt_tokens'] for x in a),'max_sequence':max(x['prompt_tokens']+x['response_tokens'] for x in a),'pass_counts':{f'R{i+1}':sum(x['labels'][i]=='P' for x in a) for i in range(8)},'by_task':dict(collections.Counter(x['task_id'] for x in a))}
(R/'data/inventory_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({**summary,'pools':{k:{a:b for a,b in v.items() if a!='by_task'} for k,v in summary['pools'].items()}},indent=2))
