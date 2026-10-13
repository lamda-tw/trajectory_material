"""Describe original-policy uncertainty using saved logprobs; no new inference."""
from pathlib import Path
from collections import defaultdict
from statistics import median
import json
R=Path(__file__).resolve().parents[1]
selected={a:[json.loads(x) for x in (R/f'data/{a}_selection.jsonl').read_text().splitlines()] for a in ['rubric','uniform']}
need=defaultdict(set)
for rows in selected.values():
 for x in rows:need[x['source']].add(x['step'])
source={}
for p,steps in need.items():
 d=json.loads(Path(p).read_text())
 for s in d['steps']:
  if s['step'] in steps:source[p,s['step']]=s['old_logprobs']
out={'scope':'Post-freeze description from existing base-policy rollout logprobs (temperature1). No new forward/judge call; not used to alter this experiment selection. NLL is not correctness or causal learning value.','arms':{}}
for arm,rows in selected.items():
 vals=[];total_nll=0;tokens=0;business=[]
 for x in rows:
  lp=source[x['source'],x['step']][:x['selected_end']];value=-sum(lp);n=len(lp)
  vals.append(value/n);total_nll+=value;tokens+=n
  if x['labels'][3]=='P' or x['labels'][4]=='P':business.append(value/n)
 assert tokens==196608
 out['arms'][arm]={'mean_token_NLL_original_policy':total_nll/tokens,'median_step_mean_NLL':median(vals),'business_pass_steps':len(business),'median_business_pass_step_NLL':median(business) if business else None}
(R/'analysis/original_policy_logprobs.json').write_text(json.dumps(out,ensure_ascii=False,indent=2)+'\n');print(json.dumps(out,ensure_ascii=False,indent=2))
