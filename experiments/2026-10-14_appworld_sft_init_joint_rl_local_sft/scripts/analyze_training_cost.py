"""Read-only CPU accounting of the running step-wise trainer; not a GPU profiler."""
from pathlib import Path
import json,statistics,collections,math
from datetime import datetime
from common import ROOT,read,dump,now
from round_data import schedule

def main():
    cfg=read(ROOT/'config/round1_trial_15.json');pool=read(ROOT/'rollout/round_01/pool.json');data=read(ROOT/'data/data_manifest.json')
    task_cost=collections.defaultdict(lambda:collections.Counter());seqs=[];targets=[];prefixes=[];trajectory_max_sum=0;transition_counts=collections.Counter();examples=[]
    for ep in pool['episodes']:
        d=read(ep['trajectory']);cost=task_cost[ep['task_id']];cost['trajectories']+=1;last=None;lengths=[]
        for s in d['steps']:
            prompt=s['prompt_ids'];response=s['response_ids'];full=prompt+response;n=len(full)-1
            cost['actions']+=1;cost['backbone_token_positions']+=n;cost['target_tokens']+=len(response);cost['prompt_tokens']+=len(prompt)
            cost['attention_pair_proxy']+=n*n;lengths.append(n);seqs.append(n);targets.append(len(response));prefixes.append(len(prompt))
            if last is not None:
                transition_counts['pairs']+=1
                # Teacher forcing excludes the final target token from the model's input.
                # Exact prefix of inputs alone is insufficient: a shared target can still differ.
                raw=last;end=min(len(raw),len(prompt));lcp=0
                for a,b in zip(raw,prompt):
                    if a!=b:break
                    lcp+=1
                transition_counts['shared_prefix_tokens']+=lcp
                transition_counts['previous_sequence_tokens']+=len(raw)
                transition_counts['exact_previous_sequence_prefix']+=int(lcp==len(raw))
                transition_counts['previous_except_last_token_prefix']+=int(lcp>=len(raw)-1)
                transition_counts['previous_prompt_prefix']+=int(prompt[:len(last_prompt)]==last_prompt)
                if lcp<len(raw) and len(examples)<4:examples.append({'task':ep['task_id'],'sample':ep['sample'],'next_step':s['step'],'prior_sequence_len':len(raw),'lcp':lcp,'prior_suffix_token_ids':raw[lcp:lcp+8],'next_prompt_suffix_token_ids':prompt[lcp:lcp+8]})
            last=full;last_prompt=prompt
        trajectory_max_sum+=max(lengths)
    rows=schedule(cfg,pool['tasks'],len(data['samples']),1);batches=[]
    for row in rows:
        costs=sum((task_cost[t] for t in row['tasks']),collections.Counter());sft=[data['samples'][i] for i in row['sft_indices']]
        result={'batch':row['batch'],**dict(costs),'sft_steps':len(sft),'sft_target_tokens':sum(s['target_tokens'] for s in sft),
                'sft_backbone_token_positions':sum(s['total_tokens']-1 for s in sft),
                'same_action_RL_SFT_overlap_steps':sum(s['task_id'] in row['tasks'] for s in sft)}
        result['main_forward_backward_calls']=result['actions']+len(sft)
        result['joint_backbone_token_positions']=result['backbone_token_positions']+result['sft_backbone_token_positions']
        cp=ROOT/'smoke/full_pool_15'/f"step_{row['batch']:05d}"/'manifest.json'
        if cp.exists():
            m=read(cp);metrics=m['state']['metrics'];result['actual_elapsed_minutes']=metrics['elapsed_seconds']/60
            result['peak_allocated_gib']=metrics['peak_allocated_gib'];result['measured_seconds_per_main_call']=metrics['elapsed_seconds']/result['main_forward_backward_calls']
            result['backbone_positions_per_second']=result['joint_backbone_token_positions']/metrics['elapsed_seconds']
            diag=ROOT/'smoke/full_pool_15/diagnostics'/f"batch_{row['batch']:02d}.json"
            if row['batch']>1 and diag.exists():
                prev=read(ROOT/'smoke/full_pool_15'/f"step_{row['batch']-1:05d}"/'manifest.json')
                result['diagnostic_approx_seconds_since_previous_checkpoint']= (datetime.fromisoformat(read(diag)['at'])-datetime.fromisoformat(prev['created_at'])).total_seconds()
        batches.append(result)
    completed=[b for b in batches if 'actual_elapsed_minutes' in b]
    allcost=sum(task_cost.values(),collections.Counter())
    report={'at':now(),'scope':'CPU/static source-token and checkpoint timing accounting; no CUDA allocation, no kernel profiler, no change to running trainer',
       'RL':dict(allcost)|{'mean_actions_per_trajectory':len(seqs)/540,'mean_prompt_tokens':statistics.mean(prefixes),'mean_target_tokens':statistics.mean(targets),
         'max_input_tokens':max(seqs),'sum_max_input_once_per_trajectory':trajectory_max_sum,
         'linear_token_work_ratio_vs_one_max_context_per_trajectory':sum(seqs)/trajectory_max_sum,
         'warning':'This ratio counts positions, not wall-clock speedup. Exact multi-action fusion requires preserving all original contexts, EOS labels, masks and gradients.'},
       'SFT':{'steps':len(data['samples']),'target_tokens':data['T_SFT'],'backbone_token_positions':sum(s['total_tokens']-1 for s in data['samples'])},
       'combined':{'main_forward_backward_calls':sum(b['main_forward_backward_calls'] for b in batches),
         'backbone_token_positions':sum(b['joint_backbone_token_positions'] for b in batches),
         'loss_target_tokens':sum(targets)+data['T_SFT'],'same_batch_RL_SFT_overlap_steps':sum(b['same_action_RL_SFT_overlap_steps'] for b in batches)},
       'adjacent_step_prefix_reuse':dict(transition_counts),'non_prefix_examples':examples,'batches':batches,
       'completed_batch_minutes':[b['actual_elapsed_minutes'] for b in completed],
       'rough_total_batch_hours_if_mean_persists':statistics.mean([b['actual_elapsed_minutes'] for b in completed])*15/60}
    dump(ROOT/'checks/training_cost_analysis.json',report)
    print(json.dumps({k:v for k,v in report.items() if k not in ['batches','non_prefix_examples']},ensure_ascii=False,indent=2))
    print('BATCHES',json.dumps(batches,ensure_ascii=False))
if __name__=='__main__':main()
