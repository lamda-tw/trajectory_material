"""Post-run paired DEV57 analysis; no model calls or training decisions."""
from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import csv,hashlib,json,math,random,statistics
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def dump(p,x):(R/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def pair(a,b):
 # a is the treatment named first; improvements compare a against b.
 wins=[t for t in a if a[t]['success'] and not b[t]['success']];losses=[t for t in a if not a[t]['success'] and b[t]['success']];n=len(wins)+len(losses)
 p=min(1.0,2*sum(math.comb(n,k) for k in range(min(len(wins),len(losses))+1))/2**n) if n else 1.0
 fam=defaultdict(list)
 for t in a:fam[t.rsplit('_',1)[0]].append(int(a[t]['success'])-int(b[t]['success']))
 rng=random.Random(20261013);keys=sorted(fam);boot=[]
 for _ in range(20000):
  draws=[rng.choice(keys) for _ in keys];vals=[v for k in draws for v in fam[k]];boot.append(sum(vals)/len(vals))
 boot.sort()
 return {'new_successes':wins,'regressions':losses,'delta_tasks':len(wins)-len(losses),'delta_TGC':(len(wins)-len(losses))/57,'mcnemar_exact_two_sided_p_descriptive':p,'task_family_count':len(keys),'paired_family_bootstrap_95_percent_interval':[boot[499],boot[19499]],'bootstrap_seed':20261013,'inference_limit':'One initialization seed; task dependence and small DEV57 limit inference. No threshold/checkpoint tuning on DEV57.'}

def main():
 (R/'analysis').mkdir(exist_ok=True)
 frozen=read('EXECUTION_MANIFEST.json')
 for p,h in frozen['files'].items():assert sha(R/p)==h,p
 data=read('data/DATA_MANIFEST.json');cfg=read('config/training.json');runs={};maps={};models={}
 for arm in ['base','rubric','uniform']:
  d=read(f'evaluation/{arm}/SUMMARY.json');assert d['phase']=='complete' and d['tasks']==57
  maps[arm]={r['task_id']:r for r in d['results']};assert len(maps[arm])==57
  for x in d['results']:assert sha(Path(x['source']))==x['sha256']
  runs[arm]={k:v for k,v in d.items() if k!='results'};runs[arm]['termination_counts']=dict(Counter(x['termination'] for x in d['results']))
  runs[arm]['mean_steps']=d['steps']/57;runs[arm]['total_task_seconds_sum']=sum(x['elapsed_seconds'] for x in d['results'])
  if arm!='base':
   models[arm]=read(f'training/{arm}/COMPLETE.json');history=read(f'training/{arm}/metrics.json')
   assert len(history)==48 and [x['update'] for x in history]==list(range(1,49))
   assert sum(x['supervised_tokens'] for x in history)==196608
   for n,h in models[arm]['adapter_files'].items():assert sha(R/f'training/{arm}/adapter'/n)==h
 assert set(maps['base'])==set(maps['rubric'])==set(maps['uniform'])
 assert models['rubric']['initial_adapter_tensor_sha256']==models['uniform']['initial_adapter_tensor_sha256']
 comparisons={f'{a}_vs_{b}':pair(maps[a],maps[b]) for a,b in [('rubric','uniform'),('rubric','base'),('uniform','base')]}
 rows=[]
 for t in maps['base']:
  rows.append({'task_id':t,**{f'{a}_{k}':maps[a][t][k] for a in maps for k in ['success','passes','tests','steps','termination']}})
 with (R/'analysis/task_comparison.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
 summary={'generated_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'arms':runs,'training':models,'comparisons':comparisons,'same_initial_adapter':True,'matched_task_supervised_tokens':True,'external_judge_calls':0,'generated_training_actions':0,'v5_scores_unchanged':True,'one_training_seed':True}
 dump('analysis/summary.json',summary)
 import matplotlib
 matplotlib.use('Agg')
 import matplotlib.pyplot as plt
 fig,ax=plt.subplots(figsize=(7,4))
 for a in ['rubric','uniform']:
  h=read(f'training/{a}/metrics.json');ax.plot([x['cumulative_supervised_tokens'] for x in h],[x['loss'] for x in h],label=a)
 ax.set(xlabel='Supervised tokens',ylabel='Training cross entropy',title='Same token budget; different selected data');ax.legend();fig.tight_layout();fig.savefig(R/'analysis/training_loss.png',dpi=160);plt.close(fig)
 print(json.dumps({'arms':{a:{k:v for k,v in d.items() if k in ['successes','TGC','steps','generated_tokens']} for a,d in runs.items()},'comparisons':comparisons},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
