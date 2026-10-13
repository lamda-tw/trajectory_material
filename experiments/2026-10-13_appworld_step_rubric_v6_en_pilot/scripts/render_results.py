"""Render existing pilot results and comparison figures locally."""
from pathlib import Path
import json,collections
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(p.read_text())
def esc(s):return str(s).replace('|','\\|').replace('\n',' ')
def main():
 summary=read(R/'analysis/summary.json'); out=['# 英文评分轨迹结果\n','仅展示已保存的有效输出；原始请求、所有无效尝试和重复结果见 runs/。\n']
 for stage in ['development','development_r1','development_r2','development_format','holdout_format']:
  out.append(f'## {stage}\n')
  for p in sorted((R/'runs'/stage).glob('*/judgement.json')):
   d=read(p);inp=read(p.parent/'input.json');out.extend([f'### {p.parent.name}\n',esc(inp['task'].split('Task:')[-1])+'\n','| Step | R1–R8 | Reason |','|---:|---|---|'])
   out.extend(f'| {n} | {lab} | {esc(why)} |' for n,lab,why in d['steps']);out.append('')
 (R/'review/SCORED_TRAJECTORIES.md').write_text('\n'.join(out)+'\n')
 stages=[s for s in ['development','development_r1','development_r2','development_format','holdout_format'] if summary['stages'].get(s,{}).get('steps')]
 fig,axes=plt.subplots(1,len(stages),figsize=(4.4*len(stages),4.3),squeeze=False,layout='constrained')
 colors={'P':'#3c9169','F':'#c65451','U':'#d9a441','N':'#bfc7ce'}
 for ax,stage in zip(axes[0],stages):
  d=summary['stages'][stage];bottom=[0]*8
  for label in 'PFUN':
   vals=[100*d['label_counts'][f'R{i}'].get(label,0)/d['steps'] for i in range(1,9)]
   ax.bar([f'R{i}' for i in range(1,9)],vals,bottom=bottom,color=colors[label],label=label);bottom=[a+b for a,b in zip(bottom,vals)]
  ax.set(title=f'{stage}\n{d["trajectories"]} trajectories, {d["steps"]} steps',ylim=(0,100),ylabel='Share of labels (%)');ax.spines[['top','right']].set_visible(False)
 axes[0][-1].legend(ncol=4,loc='upper center',bbox_to_anchor=(.5,-.12))
 fig.savefig(R/'analysis/rubric_distributions.png',dpi=160);plt.close(fig)
 # Final candidate holdout alone avoids treating different datasets as paired comparisons.
 if summary['stages'].get('holdout_format',{}).get('steps'):
  d=summary['stages']['holdout_format'];fig,ax=plt.subplots(figsize=(9,4.6),layout='constrained');bottom=[0]*8
  for label in 'PFUN':
   vals=[100*d['label_counts'][f'R{i}'].get(label,0)/d['steps'] for i in range(1,9)]
   ax.bar([f'R{i}' for i in range(1,9)],vals,bottom=bottom,color=colors[label],label=label);bottom=[a+b for a,b in zip(bottom,vals)]
  ax.set(title=f'Frozen English v6 — held-out diagnostic sample\n{d["trajectories"]} trajectories / {d["steps"]} steps',ylabel='Share of step labels (%)',ylim=(0,100));ax.spines[['top','right']].set_visible(False);ax.legend(ncol=4,loc='upper center',bbox_to_anchor=(.5,-.1))
  fig.savefig(R/'analysis/final_holdout_distribution.png',dpi=180);plt.close(fig)
 print('Rendered saved results only.')
if __name__=='__main__':main()
