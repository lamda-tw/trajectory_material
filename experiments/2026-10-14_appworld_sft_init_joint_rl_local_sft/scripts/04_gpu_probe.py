"""Isolated GPU1 engineering probe. Does not produce a formal training checkpoint."""
from pathlib import Path
import json,time
import torch
from common import ROOT,read,dump,now
from joint_core import *
from sft_dataset import LocalSFTDataset
from joint_trainer import sft_action

def main():
    assert_gpu1();torch.set_num_threads(8);cfg=read(ROOT/'config/pool_training_draft.json')
    out=ROOT/'smoke/gpu_probe';out.mkdir(parents=True,exist_ok=True);started=time.monotonic()
    model=load_model(cfg);model.eval();dataset=LocalSFTDataset(ROOT/'data/data_manifest.json')
    sample_indices=[0,len(dataset)//2,max(range(len(dataset)),key=lambda i:dataset.rows[i]['total_tokens'])]
    checks=[]
    for index in sample_indices:
        row=dataset.rows[index];raw=read(row['source']);step=raw['steps'][row['step_id']-1]
        torch.cuda.reset_peak_memory_stats();t=time.monotonic()
        with torch.no_grad():new=action_logprobs(model,step['prompt_ids'],step['response_ids'])
        old=torch.tensor(step['old_logprobs'],device=new.device);diff=(new-old).abs();ratio=(new-old).exp()
        result={'sample_id':row['sample_id'],'total_tokens':row['total_tokens'],'target_tokens':row['target_tokens'],
                'mean_abs_logp_difference':diff.mean().item(),'max_abs_logp_difference':diff.max().item(),
                'ratio_outside_0_8_1_2':((ratio<.8)|(ratio>1.2)).float().mean().item(),
                'elapsed_seconds':time.monotonic()-t,'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30}
        checks.append(result);dump(out/'progress.json',{'at':now(),'alignment':checks});print(json.dumps(result),flush=True)
    index=sample_indices[-1];prompt,target=sft_action(dataset,index);model.train();model.zero_grad(set_to_none=True)
    torch.cuda.reset_peak_memory_stats();t=time.monotonic();loss=-action_logprobs(model,prompt,target).mean();loss.backward()
    grad=grad_norm(gradients(model));require(grad>0,'No continuation LoRA gradient')
    long={'sample_id':dataset.rows[index]['sample_id'],'tokens':len(prompt)+len(target),'loss':loss.item(),
          'gradient_norm':grad,'elapsed_seconds':time.monotonic()-t,'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,
          'base_grads_absent':all(p.grad is None for p in model.parameters() if not p.requires_grad)}
    require(long['base_grads_absent'],'Frozen base gradient')
    dump(out/'report.json',{'at':now(),'status':'passed','alignment':checks,'longest_sft_backward':long,
          'elapsed_seconds':time.monotonic()-started,'physical_gpu':1,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),
          'optimizer_updates':0,'limitation':'Alignment sampled at three real actions; numerical max/mean tolerance must be measured, not assumed. Not a full-pool drift test.'})
    print(json.dumps(long),flush=True)
if __name__=='__main__':main()
