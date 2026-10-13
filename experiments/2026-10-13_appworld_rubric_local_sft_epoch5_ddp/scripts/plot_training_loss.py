"""Export the complete five-epoch training loss independently of DEV evaluation."""
from pathlib import Path
import csv,json,math
R=Path(__file__).resolve().parents[1]
done=json.loads((R/'training/rubric/COMPLETE.json').read_text())
hist=json.loads((R/'training/rubric/metrics.json').read_text())
assert done['epochs']==5 and done['updates']==6100 and not done['probe']
assert len(hist)==6100 and [x['update'] for x in hist]==list(range(1,6101))
assert all(math.isfinite(x['loss']) for x in hist)
(R/'analysis').mkdir(exist_ok=True)
with (R/'analysis/loss_history.csv').open('w',newline='') as f:
 fields=['epoch','update','loss','token_weighted_loss','supervised_tokens','input_tokens','grad_norm','elapsed_seconds'];w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows({k:x[k] for k in fields} for x in hist)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,ax=plt.subplots(figsize=(15.6,8.3));xx=[x['update'] for x in hist];ys=[x['loss'] for x in hist];ma=[sum(ys[max(0,i-49):i+1])/len(ys[max(0,i-49):i+1]) for i in range(len(ys))]
ax.plot(xx,ys,color='#78a9de',alpha=.3,linewidth=.6,label='Per-update loss');ax.plot(xx,ma,color='#c83748',linewidth=2,label='Causal moving average (50 updates)')
for n in range(1,5):ax.axvline(n*1220,color='gray',linestyle='--',linewidth=.8)
for n in range(5):ax.text((n+.5)*1220,.985,f'Epoch {n+1}',transform=ax.get_xaxis_transform(),ha='center',va='top',color='#444444')
ax.set(xlim=(0,6100),ylim=(0,max(ys)*1.06),xlabel='Global optimizer step (one synchronized update across 2 GPUs)',ylabel='Completion-only cross entropy (mean of two response means)',title='Qwen3-8B AppWorld rubric-selected LoRA SFT training loss - 5 epochs');ax.grid(alpha=.25);ax.legend(loc='center right');fig.tight_layout()
for ext in ['png','pdf']:fig.savefig(R/f'analysis/loss_5epochs.{ext}',dpi=160)
plt.close(fig)
print(R/'analysis/loss_5epochs.png')
