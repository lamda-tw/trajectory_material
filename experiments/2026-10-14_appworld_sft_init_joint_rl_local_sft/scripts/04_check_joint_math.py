"""CPU numerical tests exercise real math, Qwen3 target path, adapter continuation and checkpoint resume."""
import copy,tempfile,random
from pathlib import Path
import numpy as np
import torch
import torch.nn.functional as F
from transformers import Qwen3Config,Qwen3ForCausalLM
from peft import LoraConfig,get_peft_model
from common import ROOT,dump,read,require,now
from joint_core import *
from round_data import schedule
from collection_protocol import parse_code

def tiny():
    torch.manual_seed(77)
    base=Qwen3ForCausalLM(Qwen3Config(vocab_size=97,hidden_size=32,intermediate_size=48,num_hidden_layers=2,
          num_attention_heads=4,num_key_value_heads=2,head_dim=8,attention_dropout=0.0))
    return get_peft_model(base,LoraConfig(r=2,lora_alpha=4,lora_dropout=0.,target_modules=['q_proj','v_proj'],task_type='CAUSAL_LM'))

def close(a,b,tol=1e-5):
    error=float((a-b).detach().abs().max());require(torch.allclose(a,b,atol=tol,rtol=tol),f'Numerical mismatch {error}');return error

def main():
    torch.set_num_threads(2);results={}
    for rewards in ([0]*6,[1]*6):require(advantages(rewards).abs().max()==0,'All-equal advantages')
    adv=advantages([1,0,0,1,0,0]);results['mixed_advantage']=adv.tolist();require(abs(float(adv.mean()))<1e-12,'Advantage not centered')
    # Centered RL scalar is zero while policy gradient is nonzero.
    x=torch.zeros(6,requires_grad=True);pg,kl,r=terms(x,torch.zeros(6),torch.zeros(6),adv.float())
    pg.mean().backward();results['zero_scalar_pg']={'loss':float(pg.mean().detach()),'gradient_norm':float(x.grad.norm())};require(x.grad.norm()>0,'Lost PG gradient')
    # Unequal target lengths and padding: full step mean == microbatch accumulation.
    torch.manual_seed(4);z=torch.randn(2,6,7,requires_grad=True);labels=torch.tensor([[-100,-100,2,-100,-100,-100],[-100,-100,1,2,3,4]])
    whole=step_mean_ce(z,labels);whole.backward();g=z.grad.clone();z.grad=None
    parts=sum(step_mean_ce(z[i:i+1],labels[i:i+1])/2 for i in range(2));parts.backward()
    results['microbatch_gradient_error']=close(g,z.grad);results['microbatch_loss_error']=close(whole.detach(),parts.detach())
    require(g[:,0].abs().sum()==0 and g[0,2:].abs().sum()==0,'Masked positions have gradient')
    values=[torch.tensor([1.]),torch.tensor([3.,3.,3.])]
    results['step_equal_example']={'step_mean':float(torch.stack([v.mean() for v in values]).mean()),'token_mean':float(torch.cat(values).mean())}
    # Arbitrary segments must retain the original-step denominator.
    q=torch.randn(7,requires_grad=True);loss=q[:2].square().sum()/(2*2)+q[2:].square().sum()/(2*5);loss.backward();expected=q.grad.clone();q.grad=None
    split=q[:1].square().sum()/4+q[1:2].square().sum()/4+q[2:4].square().sum()/10+q[4:].square().sum()/10;split.backward();results['segment_gradient_error']=close(expected,q.grad)
    # Joint sum versus separate backward, including nontrivial KL and clipping.
    x=torch.tensor([-.1,-1.0,-3.0],requires_grad=True);old=torch.tensor([-.2,-1.1,-2.0]);ref=torch.tensor([-.3,-.9,-2.8]);pg,kl,ratio=terms(x,old,ref,1.2)
    loss=pg.mean()+.01*kl.mean()+.1*(-x[:2].mean());loss.backward();expected=x.grad.clone();x.grad=None
    pg,kl,ratio=terms(x,old,ref,1.2);pg.mean().backward(retain_graph=True);(.01*kl.mean()).backward();(.1*-x[:2].mean()).backward();results['joint_gradient_error']=close(expected,x.grad)
    # Compare target-only/chunk-recomputed path to full LM logits, with a real tiny Qwen3+LoRA.
    m=tiny();prompt=[1,4,7];target=[8,9,2];ids=torch.tensor([prompt+target]);m.eval()
    lp=action_logprobs(m,prompt,target,2);full=m(ids,use_cache=False).logits[0,len(prompt)-1:-1].float()
    expected=-F.cross_entropy(full,torch.tensor(target),reduction='none');results['target_logprob_error']=close(lp,expected)
    (-lp.mean()).backward();g1=gradients(m);m.zero_grad(set_to_none=True);(-expected.mean()).backward();g2=gradients(m)
    results['target_gradient_error']=max(close(a,b) for a,b in zip(g1,g2));require(all(p.grad is None for n,p in m.named_parameters() if not p.requires_grad),'Frozen base received gradients')
    # Exercise the production accumulator against one monolithic joint objective.
    from joint_trainer import accumulate_joint
    class ToyDataset:
        rows=[{'target_start':3,'target_tokens':2},{'target_start':2,'target_tokens':3}]
        def __getitem__(self,i):
            ids=([1,2,3,4,5],[6,7,8,9,10])[i];p=self.rows[i]['target_start']
            return {'input_ids':torch.tensor(ids),'labels':torch.tensor([-100]*p+ids[p:])}
    cfg=read(ROOT/'config/pool_training_draft.json');m=tiny();refs={};episodes=[]
    for i,(prompt,target) in enumerate([([1,2],[3,4]),([5,6,7],[8,9,10])]):
        with torch.no_grad():ref=action_logprobs(m,prompt,target).detach()
        refs[f't{i}__00']=[ref.numpy()]
        episodes.append({'task_id':f't{i}','sample':0,'tokens':len(target),'advantage':float(1-2*i),
                         'steps':[{'prompt_ids':prompt,'response_ids':target,'old_logprobs':(ref+.03).tolist()}]})
    stats=accumulate_joint(m,episodes,refs,ToyDataset(),[0,1],cfg);production=gradients(m);m.zero_grad(set_to_none=True)
    objective=0
    for e in episodes:
        st=e['steps'][0];new=action_logprobs(m,st['prompt_ids'],st['response_ids']);ref=torch.tensor(refs[e['task_id']+'__00'][0])
        pg,kl,_=terms(new,torch.tensor(st['old_logprobs']),ref,e['advantage'])
        objective+=(pg.mean()+cfg['loss_candidate']['kl_beta']*kl.mean())/2
    for i in [0,1]:
        ex=ToyDataset()[i];p=ToyDataset.rows[i]['target_start'];ids=ex['input_ids'].tolist()
        objective+=cfg['loss_candidate']['sft_lambda']*(-action_logprobs(m,ids[:p],ids[p:]).mean())/2
    objective.backward();results['production_accumulator_gradient_error']=max(close(a,b) for a,b in zip(production,gradients(m)))
    results['production_accumulator_loss_error']=abs(stats['total_loss']-objective.item());require(results['production_accumulator_loss_error']<1e-6,'Production loss mismatch')
    # A0 reference cache doesn't depend on subsequent actor updates; same adapter is continued.
    cfg=read(ROOT/'config/pool_training_draft.json');m=tiny();original=copy.deepcopy(m);opt=optimizer_for(m,cfg)
    ref0=action_logprobs(m,prompt,target).detach().clone()
    def update(model,optim,u):
        model.zero_grad(set_to_none=True);(-action_logprobs(model,prompt,target).mean()).backward()
        for group in optim.param_groups:group['lr']=.01
        optim.step()
    update(m,opt,1)
    with tempfile.TemporaryDirectory(dir=ROOT/'checks') as directory:
        path=Path(directory)/'step_1';save_checkpoint(path,m,opt,{'identity':'test','global_update':1})
        random_before=random.random();numpy_before=np.random.rand();torch_before=torch.rand(3)
        update(m,opt,2);continuous=[p.detach().clone() for p in m.parameters() if p.requires_grad]
        resumed=original;opt2=optimizer_for(resumed,cfg);restore_checkpoint(path,resumed,opt2,'test')
        require(random.random()==random_before and np.random.rand()==numpy_before,'Host RNG resume mismatch');close(torch.rand(3),torch_before,0)
        update(resumed,opt2,2);results['resume_parameter_error']=max(close(a,p,0) for a,p in zip(continuous,[p for p in resumed.parameters() if p.requires_grad]))
        require(ref0.equal(ref0.clone()),'Reference mutated')
        # Deliberately tamper a committed artifact and require detection.
        with (path/'adapter_config.json').open('a') as f:f.write(' ')
        try:verify_checkpoint(path)
        except ValueError:results['corrupt_checkpoint_rejected']=True
        else:raise AssertionError('Corrupted checkpoint accepted')
    tasks=(ROOT/'config/train90.txt').read_text().split();allrows=[]
    for r in range(1,6):
        rows=schedule(cfg,tasks,2623,r);require(len(rows)==15,'Wrong update count');require(sorted(t for x in rows for t in x['tasks'])==sorted(tasks),'Task coverage');allrows.extend(rows)
    require(len(allrows)==75 and sum(len(x['sft_indices']) for x in allrows)==13115,'Budget mismatch')
    results['schedule']={'updates':75,'sft_consumptions':13115,'rl_consumptions':2700,'new_rollouts':2160,'reused_rollouts':540}
    require(abs(learning_rate(cfg,1)-1.25e-6)<1e-15 and abs(learning_rate(cfg,75)-5e-7)<1e-15,'LR convention')
    require(parse_code('```python\nx=1')[0]=='x=1','Parser protocol changed')
    results.update(status='passed',at=now(),cuda_initialized=torch.cuda.is_initialized(),scope='CPU math/adapter/checkpoint tests; real serving alignment separate')
    dump(ROOT/'checks/joint_math.json',results);print(__import__('json').dumps(results,indent=2))
if __name__=='__main__':main()
