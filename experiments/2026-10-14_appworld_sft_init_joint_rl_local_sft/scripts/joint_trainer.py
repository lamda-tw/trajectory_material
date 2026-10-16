"""One complete rollout-pool training phase. GPU1, inherited LoRA, one pass, one update per minibatch."""
from pathlib import Path
import argparse, json, math, os, time, random, re
import numpy as np
import torch
from common import ROOT, read, dump, sha, require, now
from joint_core import (action_logprobs, advantages, terms, learning_rate, load_model, optimizer_for,
    gradients, grad_norm, grad_dot, save_checkpoint, restore_checkpoint, verify_checkpoint, assert_gpu1, digest)
from round_data import load_pool, schedule
from sft_dataset import LocalSFTDataset

def cache_reference(model, pool, groups, directory, cfg):
    """Called only while the sole adapter is exactly A0; frozen outputs cached per original action."""
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True); cache={};model.eval();started=time.monotonic()
    for task in pool['tasks']:
        for episode in groups[task]:
            key=f"{task}__{episode['sample']:02d}";path=directory/(key+'.npz');meta=path.with_suffix('.json')
            identity={'trajectory_sha256':episode['sha256'],'reference_sha256':cfg['model']['adapter_weights_sha256'],
                      'base':cfg['model']['base'],'precision':'bfloat16','attention':'sdpa','reference_kind':'base+initial_SFT_adapter'}
            if path.exists() and meta.exists():
                saved=read(meta);require(saved['identity']==identity and saved['sha256']==sha(path),'Reference cache mismatch')
            else:
                values={}
                with torch.no_grad():
                    for j,s in enumerate(episode['steps']):
                        values[str(j)]=action_logprobs(model,s['prompt_ids'],s['response_ids']).float().cpu().numpy()
                        dump(directory/'progress.json',{'at':now(),'phase':'reference','trajectory':key,'action':j+1,
                             'actions_in_trajectory':len(episode['steps']),'reference_episodes_done':len(cache),
                             'total':pool['count'],'elapsed_seconds':time.monotonic()-started})
                tmp=path.with_suffix('.tmp')
                with tmp.open('wb') as f:np.savez(f,**values)
                os.replace(tmp,path);dump(meta,{'identity':identity,'sha256':sha(path)})
            with np.load(path,allow_pickle=False) as a:
                refs=[a[str(j)].copy() for j in range(len(episode['steps']))]
            require(all(len(ref)==len(s['response_ids']) and np.isfinite(ref).all() for ref,s in zip(refs,episode['steps'])),'Invalid reference cache')
            cache[key]=refs
            dump(directory/'progress.json',{'at':now(),'reference_episodes_done':len(cache),'total':pool['count']})
    return cache

def sft_action(dataset,index):
    ex=dataset[index];row=dataset.rows[index];p=row['target_start'];ids=ex['input_ids'].tolist()
    require(all(x==-100 for x in ex['labels'][:p].tolist()),'Prompt labels unexpectedly supervised')
    require(ex['labels'][p:].tolist()==ids[p:] and len(ids[p:])==row['target_tokens'],'Target labels changed')
    return ids[:p],ids[p:]

def accumulate_joint(model, episodes, refs, dataset, indices, cfg, progress=None):
    """Full trajectory token normalization for RL/KL, original-step normalization for SFT."""
    require(episodes and indices,'Empty joint branch');model.train();model.zero_grad(set_to_none=True)
    c=cfg['loss_candidate'];device=next(model.parameters()).device
    metrics={'rl':0.,'kl_sampled_k3':0.,'sft_step_mean':0.,'ratio_mean':0.,'ratio_min':float('inf'),'ratio_max':0.,
             'ratio_outside_clip_interval':0.,'old_new_abs_logp':0.,'sampled_action_nll':0.,'rl_tokens':0,
             'sft_steps':len(indices),'sft_tokens':0,'rl_trajectories':len(episodes)}
    for i,e in enumerate(episodes):
        divisor=len(episodes)*e['tokens'];key=f"{e['task_id']}__{e['sample']:02d}"
        for j,s in enumerate(e['steps']):
            new=action_logprobs(model,s['prompt_ids'],s['response_ids'])
            old=torch.tensor(s['old_logprobs'],device=device,dtype=torch.float32)
            ref=torch.as_tensor(refs[key][j],device=device,dtype=torch.float32)
            pg,kl,ratio=terms(new,old,ref,e['advantage'],c['clip_epsilon'])
            loss=(pg.sum()+c['kl_beta']*kl.sum())/divisor
            loss.backward()
            with torch.no_grad():
                metrics['rl']+=pg.sum().item()/divisor;metrics['kl_sampled_k3']+=kl.sum().item()/divisor
                metrics['ratio_mean']+=ratio.sum().item()/divisor
                metrics['ratio_min']=min(metrics['ratio_min'],ratio.min().item());metrics['ratio_max']=max(metrics['ratio_max'],ratio.max().item())
                metrics['ratio_outside_clip_interval']+=((ratio-1).abs()>c['clip_epsilon']).float().sum().item()/divisor
                metrics['old_new_abs_logp']+=(new-old).abs().sum().item()/divisor
                metrics['sampled_action_nll']-=new.sum().item()/divisor
                metrics['rl_tokens']+=len(s['response_ids'])
            if progress:progress('rl',i,j)
    rl_kl_grad=gradients(model)
    for k,index in enumerate(indices):
        prompt,target=sft_action(dataset,index)
        new=action_logprobs(model,prompt,target)
        ce=-new.mean()/len(indices)
        (c['sft_lambda']*ce).backward()
        metrics['sft_step_mean']+=ce.item();metrics['sft_tokens']+=len(target)
        if progress:progress('sft',k,0)
    combined=gradients(model);weighted_sft=[b-a for a,b in zip(rl_kl_grad,combined)]
    nr,ns=grad_norm(rl_kl_grad),grad_norm(weighted_sft)
    metrics.update(grad_norm_rl_plus_weighted_kl=nr,grad_norm_weighted_sft=ns,
        grad_cosine_rl_kl_vs_sft=grad_dot(rl_kl_grad,weighted_sft)/(nr*ns) if nr*ns else None,
        grad_norm_combined=grad_norm(combined),
        total_loss=metrics['rl']+c['kl_beta']*metrics['kl_sampled_k3']+c['sft_lambda']*metrics['sft_step_mean'])
    require(all(v is None or math.isfinite(v) for v in metrics.values()),'Nonfinite metrics')
    return metrics

def commit_update(model, optimizer, cfg, update):
    lr=learning_rate(cfg,update)
    for group in optimizer.param_groups:group['lr']=lr
    norm=torch.nn.utils.clip_grad_norm_([p for p in model.parameters() if p.requires_grad],cfg['optimizer_candidate']['max_grad_norm'],error_if_nonfinite=True)
    optimizer.step()  # Exactly one mutation after all three loss gradients.
    return {'learning_rate':lr,'gradient_norm_before_clip':float(norm),'optimizer_steps_this_batch':1,
            'scheduler_update':update}  # Scheduler is a pure function of committed global update.

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--config',type=Path,default=ROOT/'config/pool_training_draft.json');ap.add_argument('--pool',type=Path,required=True)
    ap.add_argument('--output',type=Path,required=True);ap.add_argument('--previous',type=Path)
    ap.add_argument('--mode',choices=['smoke','formal'],default='smoke');ap.add_argument('--limit-updates',type=int)
    ap.add_argument('--reference-dir',type=Path);ap.add_argument('--reference-only',action='store_true')
    ap.add_argument('--execute',action='store_true');a=ap.parse_args();require(a.execute,'Pass --execute after CPU checks')
    assert_gpu1();cfg=read(a.config);a.output=a.output.resolve();require(a.output.is_relative_to(ROOT),'Output must be in isolated experiment')
    if a.mode=='smoke':require(a.output.is_relative_to(ROOT/'smoke'),'Smoke must not write formal checkpoints')
    else:
        freeze=read(ROOT/'FREEZE.json')
        require(sha(a.config)==freeze['training_config_sha256'],'Formal config is not frozen')
        require(freeze.get('files'),'Frozen code/data hashes required')
        for filename,expected in freeze['files'].items():require(sha(ROOT/filename)==expected,'Frozen artifact changed: '+filename)
        baseline=read(ROOT/'evaluation/initial/baseline_complete.json')
        require(baseline['passed'] and baseline['adapter_sha256']==cfg['model']['adapter_weights_sha256'],'Initial baseline incomplete')
        require(baseline['summary_sha256']==sha(ROOT/'evaluation/initial/SUMMARY.json') and baseline['freeze_sha256']==sha(ROOT/'FREEZE.json'),'Baseline evidence changed')
        require(a.limit_updates is None,'No partial formal schedule')
    pool,groups=load_pool(a.pool);dataset=LocalSFTDataset(ROOT/'data/data_manifest.json')
    require(set(pool['tasks'])==set((ROOT/'config/train90.txt').read_text().split()),'Formal-sized trainer requires exact train90 pool')
    require(pool['group_size']==cfg['schedule_candidate']['rollouts_per_task'] and pool['count']==540,'Incomplete 540 pool')
    require(len(dataset)==cfg['selection']['expected_steps'],'SFT dataset size changed')
    for row in dataset.rows:require(sha(ROOT/row['encoded_file'])==row['encoded_sha256'],'SFT encoded file changed')
    rows=schedule(cfg,pool['tasks'],len(dataset),pool['round']);n=len(rows)
    require(n==cfg['schedule_candidate']['batches_per_round'],'Budget/config mismatch')
    for group in groups.values():
        adv=advantages([e['reward'] for e in group],cfg['loss_candidate']['advantage_epsilon']).tolist()
        for e,value in zip(group,adv):e['advantage']=value
    identity=digest({'config':sha(a.config),'data':sha(ROOT/'data/data_manifest.json'),'mode':a.mode})
    a.output.mkdir(parents=True,exist_ok=True)
    for incomplete in a.output.glob('step_*.incomplete'):
        incomplete.rename(incomplete.with_name(incomplete.name+'.archived.'+str(time.time_ns())))
    checkpoints=sorted(p for p in a.output.glob('step_*') if re.fullmatch(r'step_\d{5}',p.name) and (p/'manifest.json').exists())
    previous=checkpoints[-1] if checkpoints else a.previous
    next_batch=0
    if previous:
        m=verify_checkpoint(previous);s=m['state'];require(s['identity']==identity,'Parent run identity mismatch')
        if s['round']==pool['round']:
            require(s['pool_sha256']==sha(a.pool),'Cannot resume with different rollout pool');next_batch=s['batch']
        else:
            require(s['round']==pool['round']-1 and s['batch']==n,'Previous round incomplete')
            require(m['adapter_sha256']==pool['behavior_adapter_sha256'],'New pool was not sampled by round-final policy')
    else:require(pool['round']==1 and pool['behavior_adapter_sha256']==cfg['model']['adapter_weights_sha256'],'Initial pool/model mismatch')
    random.seed(cfg['schedule_candidate']['seed']);np.random.seed(cfg['schedule_candidate']['seed']);torch.manual_seed(cfg['schedule_candidate']['seed'])
    refdir=(a.reference_dir or a.output/'reference').resolve();require(refdir.is_relative_to(ROOT),'Reference cache must be experiment-local')
    model=load_model(cfg);refs=cache_reference(model,pool,groups,refdir,cfg)
    if cfg.get('engineering_checks'):
        from run_checks import alignment_report
        report=alignment_report(pool,groups,refs,cfg)
        dump(a.output/'alignment.json',report)
        require(report['passed'],'Full-pool serving/training alignment gate failed; see alignment.json')
    if a.reference_only:
        require(a.mode=='smoke','Reference-only is an engineering phase')
        dump(a.output/'reference_complete.json',{'at':now(),'episodes':len(refs),'pool_sha256':sha(a.pool),'reference_dir':str(refdir)})
        return
    optimizer=optimizer_for(model,cfg)
    if previous:restore_checkpoint(previous,model,optimizer,identity)
    for row in rows[next_batch:]:
        if a.limit_updates is not None and row['batch']>a.limit_updates:break
        started=time.monotonic();episodes=[e for task in row['tasks'] for e in groups[task]];last=[0.]
        torch.cuda.reset_peak_memory_stats()
        if cfg.get('engineering_checks',{}).get('representative_branch_diagnostics'):
            from run_checks import branch_diagnostics
            diagnostics=branch_diagnostics(model,episodes,refs,dataset,row['sft_indices'],cfg)
            dump(a.output/'diagnostics'/f"batch_{row['batch']:02d}.json",diagnostics)
        def heartbeat(branch,i,j):
            if time.monotonic()-last[0]>10:
                dump(a.output/'progress.json',{'at':now(),'round':pool['round'],'batch':row['batch'],'branch':branch,'item':i,'action':j,'elapsed':time.monotonic()-started});last[0]=time.monotonic()
        metrics=accumulate_joint(model,episodes,refs,dataset,row['sft_indices'],cfg,heartbeat)
        metrics['peak_allocated_gib']=torch.cuda.max_memory_allocated()/2**30
        if cfg.get('engineering_checks'):
            from run_checks import check_drift
            failures=check_drift(metrics,cfg)
            if failures:
                dump(a.output/'drift_rejected.json',{'at':now(),'batch':row['batch'],'failures':failures,'metrics':metrics})
                raise ValueError('Policy drift gate failed before optimizer update; no sample removed')
        metrics.update(commit_update(model,optimizer,cfg,row['global_update']));metrics['elapsed_seconds']=time.monotonic()-started
        state={'identity':identity,'round':pool['round'],'batch':row['batch'],'global_update':row['global_update'],
               'pool_sha256':sha(a.pool),'behavior_policy_id':pool['behavior_policy_id'],'sft_indices':row['sft_indices'],
               'task_ids':row['tasks'],'trajectory_ids':[f"{e['task_id']}__{e['sample']:02d}" for e in episodes],
               'round_sft_consumed':sum(len(x['sft_indices']) for x in rows[:row['batch']]),'metrics':metrics,'mode':a.mode}
        save_checkpoint(a.output/f"step_{row['global_update']:05d}",model,optimizer,state)
        dump(a.output/'progress.json',{'at':now(),'state':'UPDATE_COMMITTED',**state})
        print(json.dumps({'round':pool['round'],'batch':row['batch'],**metrics}),flush=True)
    checkpoints=sorted(p for p in a.output.glob('step_*') if re.fullmatch(r'step_\d{5}',p.name) and (p/'manifest.json').exists())
    if len(checkpoints)==n and cfg.get('engineering_checks'):
        from run_checks import final_policy_probe
        probe=final_policy_probe(model,pool,groups,refs,cfg)
        dump(a.output/'final_policy_probe.json',probe)
        require(probe['passed'],'Round-final policy probe failed; preserve checkpoints for diagnosis')
    dump(a.output/'result.json',{'at':now(),'round':pool['round'],'completed_batches':len(checkpoints),
                               'expected_batches':n,'mode':a.mode,'new_collection_during_updates':False,
                               'last_checkpoint':str(checkpoints[-1]) if checkpoints else None})
if __name__=='__main__':main()
