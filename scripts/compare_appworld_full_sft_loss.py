#!/usr/bin/env python3
"""Compare full SFT histories on an epoch axis, preserving confounders."""
import argparse
import csv
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

parser=argparse.ArgumentParser()
parser.add_argument('--experiment',type=Path,required=True)
args=parser.parse_args()
exp=args.experiment.resolve()
old=exp.parent/'2026-09-15_130022_appworld_qwen3_8b_react_full_sft_67'
series=[]
for name,path,steps,color in [('Full SFT: 67 trajectories (old)',old,320,'#C67A35'),
                              ('Full SFT: 90 Codex trajectories (new)',exp,585,'#176B87')]:
    rows=[json.loads(line) for line in (path/'metrics/training_history.jsonl').read_text().splitlines() if line.strip()]
    assert len(rows)==5*steps
    assert [r['step'] for r in rows]==list(range(1,5*steps+1))
    loss=np.array([r['train_loss'] for r in rows],dtype=float)
    assert np.isfinite(loss).all()
    window=round(steps*.1)
    sums=np.r_[0.,np.cumsum(loss)]
    smooth=np.array([(sums[i+1]-sums[max(0,i+1-window)])/(i+1-max(0,i+1-window)) for i in range(len(loss))])
    series.append({'name':name,'source':str(path),'steps':steps,'loss':loss,
                   'x':np.arange(1,len(loss)+1)/steps,'smooth':smooth,'window':window,'color':color})
fig,ax=plt.subplots(figsize=(12,6.5),dpi=180)
for s in series:
    ax.plot(s['x'],s['loss'],color=s['color'],alpha=.1,lw=.45)
    ax.plot(s['x'],s['smooth'],color=s['color'],lw=2,label=s['name'])
for i in range(1,5):ax.axvline(i,color='#888888',lw=.7,ls='--',alpha=.5)
ax.set(xlim=(0,5),ylim=(0,None),xlabel='Completed epochs',ylabel='Completion-only cross-entropy loss',
       title='Qwen3-8B full-parameter SFT: 67 vs 90 trajectories')
ax.grid(alpha=.2);ax.legend()
fig.text(.5,.015,'Different training data, learning rates and precision; lower training loss is not a generalization score.',ha='center',fontsize=9,color='#555555')
fig.tight_layout(rect=[0,.035,1,1])
for suffix in ['png','pdf']:fig.savefig(exp/f'metrics/loss_curve_compare_full_sft_67_vs_90.{suffix}',bbox_inches='tight')
plt.close(fig)
with (exp/'metrics/loss_comparison_67_vs_90.csv').open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['series','completed_epochs','train_loss','causal_moving_average','window_steps'])
    for s in series:
        w.writerows((s['name'],x,y,sm,s['window']) for x,y,sm in zip(s['x'],s['loss'],s['smooth']))
summary={'smoothing':'causal moving average over about 0.1 epoch',
         'not_a_controlled_generalization_comparison':True,
         'confounders':['training tasks and trajectory source','640 vs 1170 decision samples','2e-4 constant vs 1e-5 warmup/cosine LR','32768 vs 40960 context limit','BF16 vs FP32 master parameters and optimizer state'],
         'series':[{'name':s['name'],'source':s['source'],'steps_per_epoch':s['steps'],'smoothing_window':s['window'],
                    'epoch_mean_loss':[float(s['loss'][i*s['steps']:(i+1)*s['steps']].mean()) for i in range(5)]} for s in series]}
(exp/'metrics/loss_comparison_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
