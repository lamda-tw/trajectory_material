from pathlib import Path
import csv,json,math
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
R=Path(__file__).resolve().parents[1];hist=json.loads((R/'training/uniform/metrics.json').read_text());done=json.loads((R/'training/uniform/COMPLETE.json').read_text())
assert done['epochs']==1 and done['updates']==1220 and len(hist)==1220
assert [x['update'] for x in hist]==list(range(1,1221)) and all(math.isfinite(x['loss']) for x in hist)
with (R/'analysis/loss_history.csv').open('w',newline='') as f:
 fields=['epoch','update','loss','token_weighted_loss','supervised_tokens','input_tokens','grad_norm','elapsed_seconds'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:x[k] for k in fields} for x in hist)
xx=[x['update'] for x in hist];ys=[x['loss'] for x in hist];ma=[sum(ys[max(0,i-49):i+1])/len(ys[max(0,i-49):i+1]) for i in range(len(ys))]
fig,ax=plt.subplots(figsize=(12,6));ax.plot(xx,ys,color='#78a9de',alpha=.3,linewidth=.7,label='Per-update loss');ax.plot(xx,ma,color='#c83748',linewidth=1.8,label='Causal moving average (50 updates)');ax.set(xlim=(0,1220),ylim=(0,max(ys)*1.06),xlabel='Global optimizer step (synchronized across 2 GPUs)',ylabel='Completion-only cross entropy (mean of two response means)',title='Qwen3-8B AppWorld task-matched random steps: one LoRA SFT epoch');ax.grid(alpha=.25);ax.legend();fig.tight_layout()
for ext in ['png','pdf']:fig.savefig(R/f'analysis/loss_epoch1.{ext}',dpi=160)
plt.close(fig);print(R/'analysis/loss_epoch1.png')
