"""Read-only exact-token accounting for all 540 real trajectories; CPU only."""
import collections
import json
from pathlib import Path
import sys
import time
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT/'scripts'))
from common import read, dump, now
from round_data import schedule
from tree_core import build_layout, bounded_layouts


def stats(actions):
    layout = build_layout(actions)
    original = sum(len(p)+len(r)-1 for p,r in actions)
    old_pairs = sum((len(p)+len(r)-1)*(len(p)+len(r))/2 for p,r in actions)
    # All original token paths must be retained, including unscored prefix tokens.
    for (prompt,response), queries, targets in zip(actions,layout.queries,layout.targets):
        node=queries[-1];path=[]
        while node != -1:
            path.append(layout.tokens[node]);node=layout.parents[node]
        assert path[::-1] == (prompt+response)[:-1]
        assert targets == response
        assert [layout.positions[i] for i in queries] == list(range(len(prompt)-1,len(prompt)+len(response)-1))
    bounded = bounded_layouts(actions, 32000) if len(layout.tokens)>32000 else [layout]
    assert [target for group in bounded for target in group.targets] == [r for p,r in actions]
    return dict(original_input_positions=original, shared_input_positions=len(layout.tokens),
                original_causal_pairs=int(old_pairs), shared_causal_pairs=layout.causal_pairs,
                chains=len(layout.chains), original_actions=len(actions),
                bounded_input_positions=sum(len(g.tokens) for g in bounded),
                bounded_causal_pairs=sum(g.causal_pairs for g in bounded),
                bounded_groups=len(bounded),
                max_original_context=max(len(p)+len(r)-1 for p,r in actions))


def main():
    started=time.monotonic()
    cfg=read(ROOT/'config/round1_trial_15.json');pool=read(ROOT/'rollout/round_01/pool.json')
    data=read(ROOT/'data/data_manifest.json');rows=schedule(cfg,pool['tasks'],len(data['samples']),1)
    task_batches={task:row['batch'] for row in rows for task in row['tasks']}
    results=[];totals=collections.Counter()
    for i,entry in enumerate(pool['episodes']):
        trajectory=read(entry['trajectory'])
        actions=[(s['prompt_ids'],s['response_ids']) for s in trajectory['steps']]
        counts=stats(actions)
        results.append(dict(task=entry['task_id'],sample=entry['sample'],batch=task_batches[entry['task_id']],**counts))
        totals.update({k:v for k,v in counts.items() if k!='max_original_context'})
        if (i+1)%90==0:
            print(f'Validated original contexts/targets for {i+1}/540 trajectories',flush=True)
    batches=[]
    for row in rows:
        counts=collections.Counter()
        for ep in results:
            if ep['batch']==row['batch']:
                counts.update({k:v for k,v in ep.items() if k not in ['task','sample','batch','max_original_context']})
        sft_positions=sum(data['samples'][i]['total_tokens']-1 for i in row['sft_indices'])
        cp=ROOT/'smoke/full_pool_15'/f"step_{row['batch']:05d}"/'manifest.json'
        seconds=read(cp)['state']['metrics']['elapsed_seconds'] if cp.exists() else None
        batches.append(dict(batch=row['batch'],**counts,sft_positions_unchanged=sft_positions,
                            original_total_positions=counts['original_input_positions']+sft_positions,
                            proposed_total_positions=counts['shared_input_positions']+sft_positions,
                            measured_original_seconds=seconds))
    completed=[r for r in batches if r['measured_original_seconds'] is not None]
    seconds_per_position=sum(r['measured_original_seconds'] for r in completed)/sum(r['original_total_positions'] for r in completed)
    sft_positions=sum(r['sft_positions_unchanged'] for r in batches)
    original_positions=totals['original_input_positions']+sft_positions
    proposed_positions=totals['shared_input_positions']+sft_positions
    bounded_positions=totals['bounded_input_positions']+sft_positions
    original_hours=seconds_per_position*original_positions/3600
    remain_hours=seconds_per_position*sum(r['original_total_positions'] for r in batches if r['measured_original_seconds'] is None)/3600
    report=dict(at=now(),scope='Exact raw-token layout verification only; no GPU execution, training changes, or wall-clock speedup claim',
                trajectories=len(results),RL=dict(totals),SFT_positions_unchanged=sft_positions,
                joint_original_positions=original_positions,joint_proposed_positions=proposed_positions,
                RL_position_reduction_factor=totals['original_input_positions']/totals['shared_input_positions'],
                joint_position_reduction_factor=original_positions/proposed_positions,
                bounded_joint_positions=bounded_positions,
                bounded_joint_position_reduction_factor=original_positions/bounded_positions,
                bounded_full_pool_hours_linear_proxy=seconds_per_position*bounded_positions/3600,
                candidate_max_nodes=32000,
                max_tree_nodes=max(x['shared_input_positions'] for x in results),
                trees_over_32000=sum(x['shared_input_positions']>32000 for x in results),
                completed_batches=len(completed),original_full_pool_hours_linear_proxy=original_hours,
                remaining_whole_uncommitted_batches_hours_linear_proxy=remain_hours,
                proposed_full_pool_hours_linear_proxy=seconds_per_position*proposed_positions/3600,
                proxy_warning='Position scaling ignores attention backend, gather/backward cost, kernel launch overhead, checkpoint memory and current partial-batch progress. NOT a measured ETA and NOT sufficient to stop the running job.',
                restart_comparisons=[dict(future_validation_hours=v,minimum_measured_speedup_to_beat_user_18h=original_hours/(18-v)) for v in [0,1,2,3]],
                elapsed_cpu_seconds=time.monotonic()-started,batches=batches,episodes=results)
    dump(ROOT/'checks/prefix_sharing_layouts.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['episodes','batches']},indent=2))


if __name__=='__main__':main()
