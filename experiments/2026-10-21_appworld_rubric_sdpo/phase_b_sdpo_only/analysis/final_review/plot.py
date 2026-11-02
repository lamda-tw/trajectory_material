"""Render a static figure from audited local statistics; no model inference."""
from pathlib import Path
import csv
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root = Path(__file__).resolve().parent
s = json.loads((root / 'summary.json').read_text())
rows = list(csv.DictReader((root / 'batches.csv').open()))
colors = {'mixed': '#4666ad', 'sdpo': '#cb674a'}
fig, axes = plt.subplots(2, 2, figsize=(12, 8), layout='constrained')
order = [('mixed', '1'), ('sdpo', '1'), ('mixed', '2'), ('sdpo', '2')]
labels = ['Mix E1', 'SDPO E1', 'Mix E2', 'SDPO E2']
values = [s[a]['dev'][e]['successes'] for a, e in order]
bars = axes[0, 0].bar(labels, values, color=[colors[a] for a, _ in order])
axes[0, 0].bar_label(bars, labels=[f'{n}/57' for n in values], padding=4)
axes[0, 0].set(title='A. Dev57 task success', ylabel='Tasks solved', ylim=(0, 6))
values = [100 * s[a]['dev'][e]['repeated_docs_fraction'] for a, e in order]
bars = axes[0, 1].bar(labels, values, color=[colors[a] for a, _ in order])
axes[0, 1].bar_label(bars, labels=[f'{n:.1f}%' for n in values], padding=3)
axes[0, 1].set(title='B. Repeated documentation code on dev57', ylabel='% of all agent steps', ylim=(0, 105))
for arm in ['mixed', 'sdpo']:
    r = [x for x in rows if x['arm'] == arm]
    axes[1, 0].plot([int(x['batch']) for x in r], [float(x['sdpo_loss']) for x in r], color=colors[arm], label=arm)
axes[1, 0].axvline(18.5, color='grey', linestyle=':', linewidth=1)
axes[1, 0].set(title='C. SDPO loss by online batch', xlabel='Batch', ylabel='Mean step KL', yscale='log')
axes[1, 0].legend(frameon=False)
bottom = [0., 0.]
for key, name, color in [('training_seconds', 'Training', '#50699e'), ('judge_wall_seconds', 'Codex judging', '#c9a048'),
                         ('evaluation_wall_seconds', 'Dev57', '#65a68e'), ('other_wall_seconds', 'Other', '#c0c3c8')]:
    values = [s[a]['timing'][key] / 3600 for a in ['mixed', 'sdpo']]
    axes[1, 1].barh(['mixed', 'sdpo'], values, left=bottom, label=name, color=color)
    bottom = [a + b for a, b in zip(bottom, values)]
axes[1, 1].set(title='D. End-to-end elapsed time', xlabel='Hours')
axes[1, 1].legend(frameon=False, fontsize=8, loc='upper center', bbox_to_anchor=(0.5, -0.15), ncol=4)
for ax in axes.flat:
    ax.spines[['top', 'right']].set_visible(False)
fig.suptitle('AppWorld: original SFT + SDPO vs SDPO-only control', fontsize=15)
fig.savefig(root / 'overview.png', dpi=170)
fig.savefig(root / 'overview.pdf')
