"""Actual collected mini-pool + full SFT targets; two disposable updates test commit/reload. Not batch tuning."""
from pathlib import Path
import json,time
import torch
from common import ROOT,read,dump,sha,require,now
from round_data import load_pool
from joint_core import *
from joint_trainer import cache_reference,accumulate_joint,commit_update
from sft_dataset import LocalSFTDataset

def main():
    assert_gpu1();torch.set_num_threads(8);cfg=read(ROOT/'config/pool_training_draft.json');out=ROOT/'smoke/joint_integration';out.mkdir(parents=True,exist_ok=True)
    pool,groups=load_pool(ROOT/'smoke/collection_protocol/pool.json');model=load_model(cfg)
    refs=cache_reference(model,pool,groups,out/'reference',cfg);ref_hashes={p.name:sha(p) for p in (out/'reference').glob('*.npz')}
    for group in groups.values():
        for e,value in zip(group,advantages([e['reward'] for e in group]).tolist()):e['advantage']=value
    episodes=[e for t in pool['tasks'] for e in groups[t]];dataset=LocalSFTDataset(ROOT/'data/data_manifest.json');opt=optimizer_for(model,cfg);records=[]
    original_weights=[p.detach().float().cpu().clone() for p in model.parameters() if p.requires_grad]
    for u,indices in [(1,[0,len(dataset)//2]),(2,[1,len(dataset)//2+1])]:
        t=time.monotonic();torch.cuda.reset_peak_memory_stats()
        metrics=accumulate_joint(model,episodes,refs,dataset,indices,cfg)
        metrics.update(commit_update(model,opt,cfg,u));metrics['peak_allocated_gib']=torch.cuda.max_memory_allocated()/2**30
        path=out/f'step_{u:05d}';save_checkpoint(path,model,opt,{'identity':'gpu-integration-only','update':u,'metrics':metrics})
        before=[p.detach().cpu().clone() for p in model.parameters() if p.requires_grad]
        state=restore_checkpoint(path,model,opt,'gpu-integration-only')
        metrics['reload_parameter_max_error']=max(float((a-p.detach().cpu()).abs().max()) for a,p in zip(before,[p for p in model.parameters() if p.requires_grad]))
        require(metrics['reload_parameter_max_error']==0,'GPU saved adapter mismatch')
        metrics['elapsed_seconds']=time.monotonic()-t;records.append(metrics)
        dump(out/'progress.json',{'at':now(),'completed_updates':u,'metrics':metrics});print(json.dumps(metrics),flush=True)
    final=[p.detach().float().cpu() for p in model.parameters() if p.requires_grad]
    change=max(float((a-b).abs().max()) for a,b in zip(original_weights,final));require(change>0,'No LoRA update')
    require(ref_hashes=={p.name:sha(p) for p in (out/'reference').glob('*.npz')},'Reference probabilities mutated')
    dump(out/'report.json',{'at':now(),'status':'passed','physical_gpu':1,'updates':records,'parameter_max_change':change,
         'official_rewards':[e['reward'] for e in episodes],'reference_unchanged':True,'formal_training_updates':0,
         'scope':'Two disposable updates reuse a 2-rollout, 2-action-cap engineering pool to test integration and GPU checkpoint recovery. Not the full 540 pool; not evidence that 15 minibatches have acceptable drift.'})
if __name__=='__main__':main()
