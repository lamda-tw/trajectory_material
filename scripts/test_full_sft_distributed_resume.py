"""Two CPU ranks exercise asynchronous progress metadata and exact restoration."""
import os
from pathlib import Path
import torch
import torch.distributed as dist
from full_sft_runtime import save_restart, load_restart

dist.init_process_group('gloo')
rank=dist.get_rank()
torch.set_num_threads(2)
torch.manual_seed(100+rank)
model=torch.nn.Linear(5,3)
opt=torch.optim.AdamW(model.parameters(),lr=.001)
scheduler=torch.optim.lr_scheduler.LambdaLR(opt,lambda n:1/(n+1))
x=torch.randn(4,5)
def step(m,o,s):
 o.zero_grad(set_to_none=True);loss=m(x).square().mean();loss.backward();o.step();s.step();o.zero_grad(set_to_none=True);return loss.detach()
step(model,opt,scheduler)
root=Path(os.environ['TMPDIR'])/'two_rank_restart_test'
contract={'test':'two-rank-v1'}
progress={'global_step':1,'epoch_index':0,'consumed_batches':1,'elapsed_seconds':100.+rank}
save_restart(model,opt,scheduler,root,progress,contract,reserve_gib=0)
expected_loss=step(model,opt,scheduler)
restored_model=torch.nn.Linear(5,3)
opt2=torch.optim.AdamW(restored_model.parameters(),lr=.001)
sched2=torch.optim.lr_scheduler.LambdaLR(opt2,lambda n:1/(n+1))
restored=load_restart(restored_model,opt2,sched2,root,contract)
assert restored['elapsed_seconds']==100.
actual_loss=step(restored_model,opt2,sched2)
torch.testing.assert_close(actual_loss,expected_loss,rtol=0,atol=0)
for expected,actual in zip(model.parameters(),restored_model.parameters()):torch.testing.assert_close(actual,expected,rtol=0,atol=0)
assert sched2.state_dict()==scheduler.state_dict()
print(f'PASS rank={rank}: shared metadata and exact next update',flush=True)
dist.barrier()
if rank==0:
 import shutil
 shutil.rmtree(root)
dist.destroy_process_group()
