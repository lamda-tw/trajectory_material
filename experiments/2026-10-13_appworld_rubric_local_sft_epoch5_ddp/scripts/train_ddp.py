"""Fresh two-rank completion-only LoRA SFT using unchanged original token masks."""
from pathlib import Path
from datetime import timedelta
import argparse,hashlib,json,math,os,random,time
import numpy as np
import torch
import torch.distributed as dist
from torch.nn.parallel import DistributedDataParallel as DDP
from torch.utils.checkpoint import checkpoint
from transformers import AutoModelForCausalLM
from peft import LoraConfig,get_peft_model,get_peft_model_state_dict,set_peft_model_state_dict
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text())
def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);tmp=p.with_name(p.name+f'.tmp.{os.getpid()}');tmp.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(p)
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
 return h.hexdigest()
def state_sha(state):
 h=hashlib.sha256()
 for k,v in sorted(state.items()):h.update(k.encode());h.update(v.detach().cpu().contiguous().view(torch.uint8).numpy().tobytes())
 return h.hexdigest()
def response_loss_sum(policy,tokens,prompt,end,chunk_size=128):
 base=policy.get_base_model()
 hidden=base.model(input_ids=tokens[:,:prompt+end-1],use_cache=False,return_dict=True).last_hidden_state[0,prompt-1:prompt+end-1]
 targets=tokens[0,prompt:prompt+end];assert len(hidden)==len(targets)==end>0
 def ce(h,y):return torch.nn.functional.cross_entropy(base.lm_head(h).float(),y,reduction='sum')
 return torch.stack([checkpoint(ce,hidden[i:i+chunk_size],targets[i:i+chunk_size],use_reentrant=False) for i in range(0,end,chunk_size)]).sum()
class CompletionLoss(torch.nn.Module):
 def __init__(self,policy,chunk=128):super().__init__();self.policy=policy;self.chunk=chunk
 def forward(self,tokens,prompt,end):return response_loss_sum(self.policy,tokens,prompt,end,self.chunk)/end

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--execute',action='store_true');ap.add_argument('--probe',action='store_true');args=ap.parse_args();assert args.execute
 rank=int(os.environ['RANK']);local=int(os.environ['LOCAL_RANK']);world=int(os.environ['WORLD_SIZE']);assert world==2
 torch.cuda.set_device(local);device=torch.device('cuda',local);dist.init_process_group('nccl',timeout=timedelta(minutes=30))
 cfg=read(R/'config/training.json');manifest=read(R/'data/DATA_MANIFEST.json')
 for p,h in manifest['artifacts'].items():assert sha(R/p)==h,p
 rows=[json.loads(x) for x in (R/'data/rubric_selection.jsonl').read_text().splitlines()]
 orders=read(R/'data/epoch_orders.json')['orders']
 if args.probe:
  chosen=sorted(range(len(rows)),key=lambda i:rows[i]['prompt_tokens']+rows[i]['selected_end'],reverse=True)[:2];orders=[chosen]
 out=R/('probe' if args.probe else 'training/rubric');out.mkdir(parents=True,exist_ok=True)
 if (out/'COMPLETE.json').exists():
  if rank==0:print('Already complete; no repeated updates.',flush=True)
  dist.destroy_process_group();return
 seed=cfg['seed'];random.seed(seed);np.random.seed(seed);torch.manual_seed(seed);torch.cuda.manual_seed_all(seed);torch.backends.cuda.matmul.allow_tf32=True
 started=time.monotonic();base=AutoModelForCausalLM.from_pretrained(cfg['base_model'],local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa');base.config.use_cache=False
 torch.manual_seed(seed);torch.cuda.manual_seed_all(seed)
 model=get_peft_model(base,LoraConfig(**cfg['lora']));model.to(device);model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads();model.train()
 trainable=[p for p in model.parameters() if p.requires_grad];assert all('lora_' in n for n,p in model.named_parameters() if p.requires_grad)
 state=get_peft_model_state_dict(model);initial_hash=state_sha(state);assert all(torch.count_nonzero(v)==0 for k,v in state.items() if 'lora_B' in k)
 wrapper=DDP(CompletionLoss(model,cfg['head_chunk_size']),device_ids=[local],output_device=local,broadcast_buffers=False,find_unused_parameters=False)
 hashes=[None]*world;dist.all_gather_object(hashes,initial_hash);assert len(set(hashes))==1
 init={'base_model':cfg['base_model'],'initial_adapter_tensor_sha256':initial_hash,'initial_lora_B_all_zero':True,'fresh_base_no_old_adapter':True,'same_initial_state_on_both_ranks':True,'trainable_parameters':sum(p.numel() for p in trainable),'config_sha256':sha(R/'config/training.json'),'schedule_sha256':sha(R/'data/epoch_orders.json'),'world_size':world,'probe':args.probe}
 if rank==0:
  if (out/'INITIALIZATION.json').exists():assert read(out/'INITIALIZATION.json')==init
  else:dump(out/'INITIALIZATION.json',init)
 optimizer=torch.optim.AdamW(trainable,lr=cfg['learning_rate'],weight_decay=cfg['weight_decay'])
 completed=0;history=[];prior_seconds=0.0
 if (out/'resume.pt').exists():
  saved=torch.load(out/'resume.pt',map_location='cpu',weights_only=False);assert saved['config_sha256']==init['config_sha256'] and saved['schedule_sha256']==init['schedule_sha256']
  set_peft_model_state_dict(model,saved['adapter']);optimizer.load_state_dict(saved['optimizer']);completed=saved['completed_updates'];history=saved['history'];prior_seconds=saved['elapsed_seconds']
  torch.set_rng_state(saved['rng'][rank]['torch']);torch.cuda.set_rng_state(saved['rng'][rank]['cuda'],device=device);del saved
 index=read(R/'data/token_index.json');data=np.memmap(R/'data/tokens.bin',dtype='<i4',mode='r');total_updates=sum(len(o)//world for o in orders);global_update=0
 def save_resume():
  rng=[None]*world;dist.all_gather_object(rng,{'torch':torch.get_rng_state(),'cuda':torch.cuda.get_rng_state(device)})
  if rank==0:
   saved={'completed_updates':global_update,'adapter':{k:v.detach().cpu().clone() for k,v in get_peft_model_state_dict(model).items()},'optimizer':optimizer.state_dict(),'history':history,'elapsed_seconds':prior_seconds+time.monotonic()-started,'config_sha256':init['config_sha256'],'schedule_sha256':init['schedule_sha256'],'rng':rng}
   torch.save(saved,out/'resume.tmp.pt');(out/'resume.tmp.pt').replace(out/'resume.pt');dump(out/'metrics.json',history)
  dist.barrier()
 torch.cuda.reset_peak_memory_stats(device)
 for epoch,order in enumerate(orders,1):
  if global_update+len(order)//world<=completed:
   global_update+=len(order)//world
   continue
  for start in range(0,len(order),world):
   global_update+=1
   if global_update<=completed:continue
   row=rows[order[start+rank]];info=index[row['id']];end=row['selected_end'];n=info['prompt_tokens']+end
   assert n<=cfg['max_length'] and end<=info['response_tokens']
   tokens=torch.as_tensor(np.array(data[info['offset']:info['offset']+n],dtype=np.int64),device=device).unsqueeze(0)
   optimizer.zero_grad(set_to_none=True);tick=time.monotonic()
   with torch.autocast('cuda',dtype=torch.bfloat16):loss=wrapper(tokens,info['prompt_tokens'],end)
   assert torch.isfinite(loss).item(),row['id'];loss.backward()
   norm=torch.linalg.vector_norm(torch.stack([torch.linalg.vector_norm(p.grad.detach().float()) for p in trainable if p.grad is not None]));assert torch.isfinite(norm).item()
   optimizer.step()
   stats=torch.tensor([float(loss.detach()),float(loss.detach())*end,end,n-1],device=device,dtype=torch.float64);dist.all_reduce(stats)
   if rank==0:
    vals=stats.tolist();event={'epoch':epoch,'update':global_update,'update_in_epoch':start//world+1,'total_updates':total_updates,'loss':vals[0]/world,'token_weighted_loss':vals[1]/vals[2],'supervised_tokens':int(vals[2]),'input_tokens':int(vals[3]),'sample_ids':[rows[order[start+i]]['id'] for i in range(world)],'learning_rate':cfg['learning_rate'],'grad_norm':float(norm),'elapsed_seconds':prior_seconds+time.monotonic()-started,'update_seconds':time.monotonic()-tick}
    history.append(event);dump(out/'PROGRESS.json',{'phase':'training',**event,'epochs':len(orders),'updates_per_epoch':len(order)//world,'cumulative_supervised_tokens':sum(x['supervised_tokens'] for x in history)})
    print(json.dumps({'event':'update',**event}),flush=True)
   del tokens,loss,stats,norm
   if global_update%cfg['checkpoint_interval']==0 and start+world<len(order):save_resume()
  hashes=[None]*world;dist.all_gather_object(hashes,state_sha(get_peft_model_state_dict(model)));assert len(set(hashes))==1
  if rank==0:
   ep=[x for x in history if x['epoch']==epoch];assert len(ep)==len(order)//world
   info={'epoch':epoch,'updates':len(ep),'samples':len(order),'supervised_tokens':sum(x['supervised_tokens'] for x in ep),'mean_step_loss':sum(x['loss'] for x in ep)/len(ep),'token_weighted_loss':sum(x['token_weighted_loss']*x['supervised_tokens'] for x in ep)/sum(x['supervised_tokens'] for x in ep),'ranks_synchronized':True,'adapter_tensor_sha256':hashes[0],'elapsed_seconds':prior_seconds+time.monotonic()-started}
   dump(out/f'epoch_{epoch:02d}.json',info);model.save_pretrained(out/f'epoch_{epoch:02d}_adapter',safe_serialization=True);print(json.dumps({'event':'epoch_complete',**info}),flush=True)
  dist.barrier();save_resume()
 ranks=[None]*world;dist.all_gather_object(ranks,{'rank':rank,'device':torch.cuda.get_device_name(local),'peak_allocated_gib':torch.cuda.max_memory_allocated(device)/2**30,'peak_reserved_gib':torch.cuda.max_memory_reserved(device)/2**30})
 if rank==0:
  assert len(history)==total_updates
  expected=sum(rows[i]['selected_end'] for order in orders for i in order);assert sum(x['supervised_tokens'] for x in history)==expected
  final_hash=state_sha(get_peft_model_state_dict(model));assert final_hash!=initial_hash
  adapter=out/'adapter';model.save_pretrained(adapter,safe_serialization=True)
  result={'phase':'complete','arm':'rubric','epochs':len(orders),'updates':total_updates,'supervised_tokens':expected,'initial_adapter_tensor_sha256':initial_hash,'final_adapter_tensor_sha256':final_hash,'adapter_files':{p.name:sha(p) for p in adapter.iterdir() if p.is_file()},'training_wall_seconds':prior_seconds+time.monotonic()-started,'distributed_ranks':ranks,'external_judge_calls':0,'new_training_actions':0,'probe':args.probe}
  dump(out/'COMPLETE.json',result);dump(out/'PROGRESS.json',result);print(json.dumps(result),flush=True)
 dist.barrier();dist.destroy_process_group()
if __name__=='__main__':main()
