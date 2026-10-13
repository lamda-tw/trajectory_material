"""Check availability of exact-history preferences without rewriting or outcomes."""
from pathlib import Path
from collections import defaultdict,Counter
import json,hashlib
R=Path(__file__).resolve().parents[1]
rows=[json.loads(x) for x in (R/'data/step_inventory.jsonl').read_text().splitlines()];byid={x['id']:x for x in rows};sources=sorted({x['source'] for x in rows});groups=defaultdict(list)
for p in sources:
 sid=Path(p).stem;d=json.loads(Path(p).read_text())
 for st in d['steps']:
  row=byid[f"{sid}:{st['step']}"]
  if not st['code'].strip() or st['finish_reason']!='stop':continue
  key=hashlib.sha256(json.dumps(st['prompt_ids'],separators=(',',':')).encode()).hexdigest()
  groups[key].append({'id':row['id'],'task_id':row['task_id'],'step':row['step'],'positive':row['rubric_pool'],'negative':any(c=='F' for c in row['labels'][:7]),'labels':row['labels']})
pairs=[]
for key,values in groups.items():
 pos=[x for x in values if x['positive']];neg=[x for x in values if x['negative']]
 if pos and neg:pairs.append({'prompt_sha256':key,'positives':pos,'negatives':neg,'potential_pairs':len(pos)*len(neg)})
summary={'scope':'Exploratory post-freeze inventory only; did not affect training. Exact prompt-token equality; candidate preferences from existing labels, no new actions and no outcome-flip verification.','total_exact_prompt_groups':len(groups),'groups_with_multiple_actions':sum(len(v)>1 for v in groups.values()),'groups_with_both_positive_and_negative':len(pairs),'tasks_with_pairs':len({x['task_id'] for p in pairs for x in p['positives']}),'potential_pairs_not_independent':sum(p['potential_pairs'] for p in pairs),'positive_step_positions':dict(Counter(x['step'] for p in pairs for x in p['positives'])),'groups':pairs}
(R/'analysis/existing_same_history_pairs.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n');print(json.dumps({k:v for k,v in summary.items() if k!='groups'},indent=2))
