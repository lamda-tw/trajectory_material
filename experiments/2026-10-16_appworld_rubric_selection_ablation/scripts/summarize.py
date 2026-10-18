from pathlib import Path
import json,csv,statistics,random,math
from collections import defaultdict,Counter
R=Path(__file__).resolve().parents[1];out=R/'analysis';out.mkdir(exist_ok=True);cfg=json.loads((R/'config/training.json').read_text());data=[];by={}
for p in sorted((R/'evaluation').rglob('SUMMARY.json')):
 d=json.loads(p.read_text());row={k:d[k] for k in ['arm','seed','epoch','tasks','successes','TGC','steps','generated_tokens']};row['source']=str(p);data.append(row);by[(d['arm'],d['seed'],d['epoch'])]=d
(out/'results.json').write_text(json.dumps(data,indent=2)+'\n')
if data:
 with (out/'results.csv').open('w') as f:
  w=csv.DictWriter(f,fieldnames=list(data[0]));w.writeheader();w.writerows(data)
comparisons=[]
for epoch in cfg['eval_epochs']:
 for arm in cfg['arms'][1:]:
  paired=[]
  for seed in cfg['seeds']:
   if (arm,seed,epoch) in by and ('random',seed,epoch) in by:
    a={r['task_id']:r for r in by[(arm,seed,epoch)]['results']};b={r['task_id']:r for r in by[('random',seed,epoch)]['results']};paired.append({t:int(a[t]['success'])-int(b[t]['success']) for t in a})
  if paired:
   avg={t:statistics.mean(d[t] for d in paired) for t in paired[0]};families=defaultdict(list)
   for t,v in avg.items():families[t.rsplit('_',1)[0]].append(v)
   rng=random.Random(20261016);keys=sorted(families);boot=[]
   for _ in range(5000):
    vals=[v for k in rng.choices(keys,k=len(keys)) for v in families[k]];boot.append(statistics.mean(vals))
   boot.sort();comparisons.append({'arm':arm,'epoch':epoch,'completed_seed_pairs':len(paired),'difference_vs_random':statistics.mean(avg.values()),'family_bootstrap_95':[boot[125],boot[4874]],'scope':'descriptive family bootstrap after averaging same-task seed results; not a significance claim'})
(out/'comparisons.json').write_text(json.dumps(comparisons,indent=2)+'\n')
text='# Rubric 选样消融运行结果\n\n五组各 1,710 步，无额外质量过滤。各组任务分配不完全相同，不能把差异只归因于标签。未完成的运行不填为零分。\n\n|组|seed|epoch|成功|TGC|\n|---|---:|---:|---:|---:|\n'
for r in data:text+=f"|{r['arm']}|{r['seed']}|{r['epoch']}|{r['successes']}/{r['tasks']}|{r['TGC']:.2%}|\n"
text+='\n逐题原始轨迹保存在 evaluation；描述性家族配对统计见 analysis/comparisons.json。所有完成结果均列出，不挑选最佳 seed 或轮次。\n'
(R/'REPORT.md').write_text(text)
