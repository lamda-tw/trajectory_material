"""Render v6 rubric label shares from saved summary; no model calls."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

def main():
    summary = json.loads((ROOT / 'analysis/summary.json').read_text())
    groups = summary['counts_by_official_outcome']
    rubrics = [f'R{i}' for i in range(1, 9)]
    labels = ['P', 'F', 'U', 'N']
    group_steps = {g: sum(groups[g]['R1'].values()) for g in groups}
    assert sum(group_steps.values()) == summary['steps']
    for r in rubrics:
        for g in groups:
            assert sum(groups[g][r].values()) == group_steps[g]
        for label in labels:
            assert sum(groups[g][r].get(label, 0) for g in groups) == summary['counts'][r].get(label, 0)
    output = ROOT / 'analysis/figures'
    output.mkdir(exist_ok=True)
    colors = {'P': '#3c9169', 'F': '#c65451', 'U': '#d9a441', 'N': '#bfc7ce'}
    plt.rcParams.update({'font.size': 10, 'axes.spines.top': False, 'axes.spines.right': False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.6), sharey=True, constrained_layout=True)
    successes = summary['official_successes']
    titles = [f'Official success ({successes} trajectories)',
              f"Official failure ({summary['trajectories'] - successes} trajectories)"]
    for axis, group, title in zip(axes, ['success', 'failure'], titles):
        counts = groups[group]
        bottom = np.zeros(8)
        for label in labels:
            values = np.array([100 * counts[r].get(label, 0) / group_steps[group] for r in rubrics])
            axis.bar(rubrics, values, bottom=bottom, color=colors[label], label=label, width=.7)
            bottom += values
        assert np.allclose(bottom, 100)
        axis.set_title(title)
        axis.set_ylim(0, 100)
        axis.set_ylabel('Share of step labels (%)')
    axes[-1].legend(ncol=4, loc='upper center', bbox_to_anchor=(.5, -.12))
    for ext in ['png', 'svg']:
        path = output / f'rubric_distribution.{ext}'
        fig.savefig(path, dpi=180)
        print(path)
    plt.close(fig)
    print(f'Validated: {summary["trajectories"]} trajectories, {summary["steps"]} steps; group steps: {group_steps}')

if __name__ == '__main__':
    main()
