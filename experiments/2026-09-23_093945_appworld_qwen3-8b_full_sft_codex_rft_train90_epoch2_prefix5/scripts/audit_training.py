#!/usr/bin/env python3
"""Audit an actual retrained prefix against the original five-epoch history."""
import argparse, collections, json, math, os, statistics, sys
from pathlib import Path
T=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(T/'scripts_snapshot'))
from verify_codex_rft_full_sft_artifacts import sha256
p=argparse.ArgumentParser();p.add_argument('--partial',action='store_true');args=p.parse_args()
manifest=json.loads((T/'manifest.json').read_text()); O=Path(manifest['reference_training_experiment'])
def history(root): return [json.loads(x) for x in (root/'metrics/training_history.jsonl').read_text().splitlines() if x.strip()]
a,b=history(T),history(O)
assert a and len(a)<=1170 and len(b)==2925
assert [x['step'] for x in a]==list(range(1,len(a)+1))
if not args.partial: assert len(a)==1170
rank=lambda row:[(r['rank'],r['sequence_length'],r['completion_tokens']) for r in row['ranks']]
lr_diff=[abs(x['learning_rate']-y['learning_rate']) for x,y in zip(a,b)]
loss_diff=[abs(x['train_loss']-y['train_loss']) for x,y in zip(a,b)]
grad_diff=[abs(x['grad_norm']-y['grad_norm']) for x,y in zip(a,b)]
sequence_match=[x['step'] for x,y in zip(a,b) if rank(x)==rank(y)]
assert max(lr_diff)==0, 'LR prefix differs'
assert len(sequence_match)==len(a), 'Sample-length/completion order differs'
assert all(x['epoch']==y['epoch'] for x,y in zip(a,b))
epochs=[]
for epoch in range(1,6):
    aa=[x for x in a if x['epoch']==epoch];bb=[x for x in b if x['epoch']==epoch]
    epochs.append({'epoch':epoch,'epoch2_run_steps':len(aa),'epoch2_run_mean_loss':statistics.mean(x['train_loss'] for x in aa) if aa else None,'epoch5_run_mean_loss':statistics.mean(x['train_loss'] for x in bb),
        'epoch2_completion_tokens':sum(r['completion_tokens'] for x in aa for r in x['ranks']) if aa else None})
cfg=json.loads((T/'config/training_config.json').read_text())
assert sha256(cfg['train_json'])==cfg['train_sha256']
summary={'status':'PARTIAL' if args.partial else 'PASS','steps_compared':len(a),'expected_steps':1170,'schedule_steps':2925,'warmup_steps':88,
    'lr_max_abs_difference':max(lr_diff),'rank_length_and_completion_order_matches':len(sequence_match),
    'train_loss_max_abs_difference':max(loss_diff),'train_loss_mean_abs_difference':statistics.mean(loss_diff),
    'train_loss_exact_matches':sum(d==0 for d in loss_diff),'grad_norm_max_abs_difference':max(grad_diff),
    'first_loss_difference_step':next((i+1 for i,d in enumerate(loss_diff) if d!=0),None),
    'first_100_loss_max_abs_difference':max(loss_diff[:100]),'epochs':epochs,
    'interpretation':'Same data SHA, seed, update logic and LR prefix; replay similarity is measured, not assumed. Old epoch2 weights are unavailable, so bitwise weight identity cannot be checked.'}
if not args.partial:
    assert all(r['epoch2_completion_tokens']==94553 for r in epochs[:2])
    metrics=json.loads((T/'metrics/metrics.json').read_text());tr=metrics['training']
    assert metrics['status']=='SUCCESS' and tr['epochs_completed']==2 and tr['global_steps']==1170
    assert metrics['training']['history']==a
    summary['train_overlap_diagnostic']=metrics['validation']
    summary['elapsed_seconds']=tr['elapsed_seconds']
    import csv
    with (T/'metrics/training_prefix_comparison.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(['step','epoch','learning_rate','new_epoch2_loss','old_epoch5_prefix_loss','loss_difference','new_grad_norm','old_grad_norm'])
        writer.writerows([x['step'],x['epoch'],x['learning_rate'],x['train_loss'],y['train_loss'],x['train_loss']-y['train_loss'],x['grad_norm'],y['grad_norm']] for x,y in zip(a,b))
    (T/'metrics/prefix_replay_audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    os.environ['MPLCONFIGDIR']=str(T/'cache/matplotlib')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    fig,axes=plt.subplots(1,2,figsize=(12,4.4),layout='constrained')
    for rows,label,col in [(b,'Full SFT: original 5 epochs','#d66140'),(a,'Full SFT: stop at epoch 2','#2878b5')]:
        vals=np.array([x['train_loss'] for x in rows]);smooth=np.convolve(vals,np.ones(50)/50,mode='valid')
        axes[0].plot(np.arange(50,len(vals)+1)/585,smooth,label=label,color=col,lw=1.7,alpha=.9)
    axes[0].axvline(2,color='#777',ls='--',lw=1)
    axes[0].set(xlabel='Training epoch',ylabel='Completion-only loss (50-step mean)',yscale='log',title='Actual training loss; same original LR schedule')
    axes[0].legend(frameon=False,fontsize=8);axes[0].grid(alpha=.2)
    axes[1].plot([x['epoch'] for x in epochs],[x['epoch5_run_mean_loss'] for x in epochs],marker='o',color='#d66140',label='Original 5 epochs')
    axes[1].plot([1,2],[x['epoch2_run_mean_loss'] for x in epochs[:2]],marker='s',color='#2878b5',label='New 2 epochs')
    axes[1].set(xticks=range(1,6),xlabel='Completed epoch',ylabel='Mean training loss',yscale='log',title='Epoch means (not held-out validation)')
    axes[1].legend(frameon=False);axes[1].grid(alpha=.2)
    for ext in ['png','pdf']: fig.savefig(T/('metrics/loss_comparison.'+ext),dpi=180)
    plt.close(fig)
print(json.dumps(summary,ensure_ascii=False,indent=2))
