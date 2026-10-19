"""Single GPU completion-only SFT; two per-step token means per update."""
from pathlib import Path
import argparse,hashlib,json,os,random,time,math
import numpy as np
import torch
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
def response_mean(policy,tokens,prompt,end,chunk=128):
 base=policy.get_base_model();hidden=base.model(input_ids=tokens[:,:prompt+end-1],use_cache=False,return_dict=True).last_hidden_state[0,prompt-1:prompt+end-1];target=tokens[0,prompt:prompt+end];assert len(hidden)==len(target)==end>0
 def ce(h,y):return torch.nn.functional.cross_entropy(base.lm_head(h).float(),y,reduction='sum')
 return torch.stack([checkpoint(ce,hidden[i:i+chunk],target[i:i+chunk],use_reentrant=False) for i in range(0,end,chunk)]).sum()/end

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--arm',required=True);ap.add_argument('--seed',type=int,required=True);ap.add_argument('--until-epoch',type=int,default=1);ap.add_argument('--probe',action='store_true');args=ap.parse_args()
 cfg=read(R/'config/training.json');assert os.environ.get('CUDA_VISIBLE_DEVICES')==cfg['gpu_uuid'];assert torch.cuda.device_count()==1;assert args.arm in cfg['arms'];assert args.seed in cfg['seeds'];assert 1<=args.until_epoch<=cfg['epochs']
 torch.set_num_threads(4);device=torch.device('cuda:0');torch.cuda.set_device(device)
 run=f'{args.arm}/seed_{args.seed}';folder=R/'data'/run;rows=[json.loads(s) for s in (folder/'selection.jsonl').read_text().splitlines()];orders=read(folder/'orders.json')['orders'];out=R/('probe' if args.probe else 'training')/run
 if args.probe:
  inv=[json.loads(s) for s in (R/'data/step_inventory.jsonl').read_text().splitlines()];selected=set(read(R/'data/selected_union.json'));rows=sorted([r for r in inv if r['id'] in selected],key=lambda r:r['prompt_tokens']+r['response_tokens'],reverse=True)[:2];orders=[[0,1]]
 target_epoch=1 if args.probe else args.until_epoch;per_epoch=math.ceil(len(orders[0])/2);out.mkdir(parents=True,exist_ok=True)
 if (out/f'epoch_{target_epoch:02d}.json').exists():print('Requested epoch already complete',flush=True);return
 random.seed(args.seed);np.random.seed(args.seed);torch.manual_seed(args.seed);torch.cuda.manual_seed_all(args.seed);torch.backends.cuda.matmul.allow_tf32=True
 started=time.monotonic();base=AutoModelForCausalLM.from_pretrained(cfg['base_model'],local_files_only=True,dtype=torch.bfloat16,attn_implementation='sdpa');base.config.use_cache=False;torch.manual_seed(args.seed);torch.cuda.manual_seed_all(args.seed)
 model=get_peft_model(base,LoraConfig(**cfg['lora']));model.to(device);model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False});model.enable_input_require_grads();model.train();params=[p for p in model.parameters() if p.requires_grad];assert all('lora_' in n for n,p in model.named_parameters() if p.requires_grad)
 initial=state_sha(get_peft_model_state_dict(model));assert all(torch.count_nonzero(v)==0 for k,v in get_peft_model_state_dict(model).items() if 'lora_B' in k)
 init={'seed':args.seed,'initial_adapter_tensor_sha256':initial,'config_sha256':sha(R/'config/training.json'),'selection_sha256':sha(folder/'selection.jsonl'),'orders_sha256':sha(folder/'orders.json'),'trainable_parameters':sum(p.numel() for p in params),'probe':args.probe,'fresh_base_no_old_adapter':True}
 if (out/'INITIALIZATION.json').exists():assert read(out/'INITIALIZATION.json')==init
 else:dump(out/'INITIALIZATION.json',init)
 opt=torch.optim.AdamW(params,lr=cfg['learning_rate'],weight_decay=cfg['weight_decay']);completed=0;history=[];prior=0
 if (out/'resume.pt').exists():
  saved=torch.load(out/'resume.pt',map_location='cpu',weights_only=False);assert saved['init']==init;set_peft_model_state_dict(model,saved['adapter']);opt.load_state_dict(saved['optimizer']);completed=saved['completed'];history=saved['history'];prior=saved['elapsed_seconds'];torch.set_rng_state(saved['torch_rng']);torch.cuda.set_rng_state(saved['cuda_rng']);del saved
 data=np.memmap(R/'data/tokens.bin',dtype='<i4',mode='r');index=read(R/'data/token_index.json');global_update=0;torch.cuda.reset_peak_memory_stats()
 def save():
  state={'init':init,'adapter':{k:v.detach().cpu().clone() for k,v in get_peft_model_state_dict(model).items()},'optimizer':opt.state_dict(),'completed':global_update,'history':history,'elapsed_seconds':prior+time.monotonic()-started,'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state()};torch.save(state,out/'resume.tmp.pt');(out/'resume.tmp.pt').replace(out/'resume.pt');dump(out/'metrics.json',history)
 for epoch,order in enumerate(orders[:target_epoch],1):
  if global_update+math.ceil(len(order)/2)<=completed:
   global_update+=math.ceil(len(order)/2)
   continue
  for start in range(0,len(order),2):
   global_update+=1
   if global_update<=completed:continue
   batch=[rows[i] for i in order[start:start+2]];opt.zero_grad(set_to_none=True);tick=time.monotonic();losses=[]
   for row in batch:
    info=index[row['id']];p=info['prompt_tokens'];e=info['response_tokens'];n=p+e;assert n<=cfg['max_length'];tokens=torch.as_tensor(np.array(data[info['offset']:info['offset']+n],dtype=np.int64),device=device).unsqueeze(0)
    with torch.autocast('cuda',dtype=torch.bfloat16):loss=response_mean(model,tokens,p,e,cfg['head_chunk_size'])
    assert torch.isfinite(loss).item(),row['id'];losses.append(float(loss.detach()));(loss/len(batch)).backward();del tokens,loss
   norm=torch.linalg.vector_norm(torch.stack([torch.linalg.vector_norm(p.grad.detach().float()) for p in params if p.grad is not None]));assert torch.isfinite(norm).item();opt.step()
   event={'epoch':epoch,'update':global_update,'update_in_epoch':start//2+1,'total_updates':len(orders)*per_epoch,'loss':sum(losses)/len(batch),'token_weighted_loss':sum(x*r['response_tokens'] for x,r in zip(losses,batch))/sum(r['response_tokens'] for r in batch),'supervised_tokens':sum(r['response_tokens'] for r in batch),'sample_ids':[r['id'] for r in batch],'grad_norm':float(norm),'learning_rate':cfg['learning_rate'],'update_seconds':time.monotonic()-tick,'elapsed_seconds':prior+time.monotonic()-started}
   history.append(event);dump(out/'PROGRESS.json',{'phase':'training',**event});print(json.dumps(event),flush=True)
   if global_update%cfg['checkpoint_interval']==0:save()
  if not (out/f'epoch_{epoch:02d}.json').exists():
   ep=[h for h in history if h['epoch']==epoch];assert len(ep)==per_epoch;assert sum(h['supervised_tokens'] for h in ep)==sum(r['response_tokens'] for r in rows);assert all(torch.isfinite(v).all().item() for v in get_peft_model_state_dict(model).values());adapter=out/f'epoch_{epoch:02d}_adapter';model.save_pretrained(adapter,safe_serialization=True)
   info={'phase':'complete','epoch':epoch,'updates':len(ep),'cumulative_updates':global_update,'samples':len(rows),'supervised_tokens':sum(h['supervised_tokens'] for h in ep),'mean_step_loss':sum(h['loss'] for h in ep)/len(ep),'adapter_tensor_sha256':state_sha(get_peft_model_state_dict(model)),'adapter_files':{p.name:sha(p) for p in adapter.iterdir() if p.is_file()},'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'elapsed_seconds':prior+time.monotonic()-started,'probe':args.probe};assert info['adapter_tensor_sha256']!=initial;dump(out/f'epoch_{epoch:02d}.json',info)
  save()
 dump(out/'PROGRESS.json',{'phase':'checkpoint_complete','epoch':target_epoch,'updates':global_update})
 if target_epoch==len(orders):dump(out/'COMPLETE.json',read(out/f'epoch_{target_epoch:02d}.json'))
if __name__=='__main__':main()
