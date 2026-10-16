"""Numerical gates stop whole runs, never select/drop/reweight individual samples."""
import math
import numpy as np
import torch
from common import now, require
from joint_core import action_logprobs, terms, grad_norm, capture_rng, restore_rng

def alignment_report(pool, groups, refs, cfg):
    absolute=[]; means=[]; clipped=[]
    for task in pool['tasks']:
        for e in groups[task]:
            key=f"{task}__{e['sample']:02d}"
            delta=np.concatenate([r-np.asarray(s['old_logprobs'],dtype=np.float64) for r,s in zip(refs[key],e['steps'])])
            require(np.isfinite(delta).all(),'Nonfinite backend comparison')
            absolute.append(np.abs(delta));means.append(float(np.abs(delta).mean()))
            clipped.append(float(((delta<math.log(.8))|(delta>math.log(1.2))).mean()))
    allabs=np.concatenate(absolute);lim=cfg['engineering_checks']['backend_alignment']
    report={'at':now(),'scope':'entire original 540 pool; HF A0 against saved vLLM behavior, before updates',
            'trajectories':len(means),'tokens':len(allabs),'trajectory_mean_absolute_logp':float(np.mean(means)),
            'trajectory_mean_ratio_outside_clip':float(np.mean(clipped)),
            'token_absolute_logp_quantiles':dict(zip(['p50','p90','p99','p999','maximum'],np.quantile(allabs,[.5,.9,.99,.999,1]).tolist())),
            'limits':lim,'old_logprobs_overwritten':False}
    report['passed']=(report['trajectory_mean_absolute_logp']<=lim['mean_abs_logp_max'] and
                      report['trajectory_mean_ratio_outside_clip']<=lim['outside_clip_fraction_max'])
    return report

def check_drift(metrics,cfg):
    limits=cfg['engineering_checks']['pool_drift'];failures=[]
    for field,limit in limits.items():
        if not math.isfinite(metrics[field]) or metrics[field]>limit:failures.append({'metric':field,'value':metrics[field],'maximum':limit})
    return failures

def _gradients(loss,params,retain_graph=False):
    values=torch.autograd.grad(loss,params,retain_graph=retain_graph,allow_unused=True)
    return [g.detach().float().cpu() if g is not None else torch.zeros_like(p,device='cpu',dtype=torch.float32) for g,p in zip(values,params)]

def branch_diagnostics(model,episodes,refs,dataset,indices,cfg):
    """One representative action per batch. Full-batch RL+KL/SFT norms remain in trainer metrics."""
    from joint_trainer import sft_action
    rng=capture_rng();model.train();model.zero_grad(set_to_none=True)
    e=next((e for e in episodes if e['advantage']!=0),episodes[0]);s=e['steps'][0]
    params=[p for p in model.parameters() if p.requires_grad];device=next(model.parameters()).device
    try:
        new=action_logprobs(model,s['prompt_ids'],s['response_ids'])
        old=torch.tensor(s['old_logprobs'],device=device,dtype=torch.float32)
        ref=torch.as_tensor(refs[f"{e['task_id']}__{e['sample']:02d}"][0],device=device,dtype=torch.float32)
        pg,kl,_=terms(new,old,ref,e['advantage'],cfg['loss_candidate']['clip_epsilon'])
        pg_norm=grad_norm(_gradients(pg.mean(),params,True));kl_norm=grad_norm(_gradients(kl.mean(),params))
        prompt,target=sft_action(dataset,indices[0])
        sft_norm=grad_norm(_gradients(-action_logprobs(model,prompt,target).mean(),params))
        # Exact categorical entropy over the full vocabulary at the selected action's target states.
        # This is an audit of selected states, not full-pool entropy and not sampled-action NLL.
        model.eval();base=model.get_base_model();entropy=[]
        with torch.no_grad():
            ids=torch.tensor([s['prompt_ids']+s['response_ids']],device=device)
            h=base.model(input_ids=ids[:,:-1],use_cache=False,return_dict=True).last_hidden_state[0,len(s['prompt_ids'])-1:]
            for offset in range(0,len(h),128):
                logp=base.lm_head(h[offset:offset+128]).float().log_softmax(-1)
                entropy.append(-(logp.exp()*logp).sum(-1).cpu())
        report={'at':now(),'scope':'representative action/step diagnostics only; not whole-batch branch norms',
                'rl_task':e['task_id'],'rl_sample':e['sample'],'rl_action_index':0,'advantage':e['advantage'],
                'sft_index':indices[0],'grad_norm_rl_unscaled':pg_norm,'grad_norm_kl_unscaled':kl_norm,
                'grad_norm_sft_unscaled':sft_norm,'grad_norm_kl_weighted':kl_norm*cfg['loss_candidate']['kl_beta'],
                'grad_norm_sft_weighted':sft_norm*cfg['loss_candidate']['sft_lambda'],
                'categorical_entropy_mean_at_audited_states':float(torch.cat(entropy).mean()),
                'parameter_updates':0}
        require(all(math.isfinite(report[k]) for k in report if k.startswith('grad_norm') or k.startswith('categorical_')),'Nonfinite diagnostic')
        return report
    finally:
        model.zero_grad(set_to_none=True);model.train();restore_rng(rng)

def final_policy_probe(model,pool,groups,refs,cfg):
    model.eval();scores=[]
    # Deterministic one original action per task; never a reward-selected subset.
    with torch.no_grad():
        for task in pool['tasks']:
            e=sorted(groups[task],key=lambda x:x['sample'])[0];s=e['steps'][0]
            new=action_logprobs(model,s['prompt_ids'],s['response_ids'])
            old=torch.tensor(s['old_logprobs'],device=new.device,dtype=torch.float32)
            ref=torch.as_tensor(refs[f'{task}__00'][0],device=new.device,dtype=torch.float32)
            _,kl,ratio=terms(new,old,ref,e['advantage'])
            scores.append({'task':task,'kl_sampled_k3':float(kl.mean()),'old_new_abs_logp':float((new-old).abs().mean()),
                           'ratio_outside_clip_interval':float(((ratio-1).abs()>.2).float().mean())})
    means={k:float(np.mean([s[k] for s in scores])) for k in ['kl_sampled_k3','old_new_abs_logp','ratio_outside_clip_interval']}
    failures=check_drift(means,cfg)
    return {'at':now(),'scope':'post-final-update first action of sample 0 for all 90 train tasks; additional deterministic probe',
            'passed':not failures,'metrics':means,'failures':failures,'tasks':scores}
