"""GPU1 inference only, using separately frozen inputs; resume completed jobs exactly."""
from pathlib import Path
import sys,os,subprocess,concurrent.futures,fcntl,time,argparse
D=Path(__file__).resolve().parents[1];R=D.parent;sys.path.insert(0,str(R/'scripts'))
from a_common import read,write_json,frozen_json,file_sha,CPU,now,require_free_gpu,W
from a_policy_server import owned_server
cfg=read(D/'config/runtime.json');manifest=read(D/'config/manifest.json');provenance=read(D/'config/model_provenance.json')
assert not read(D/'config/authorization.json')['training']
def status(stage,**kw):
 value={'stage':stage,'updated_at':now(),'parameter_updates':0,'physical_gpu':1,**kw};write_json(D/'STATUS.json',value);print(value,flush=True)
def execute(item,model,condition,served=None):
 ident=item['id'];folder=D/('replay' if condition=='replay' else f'runs/{model}_{condition}')/ident
 job={'state_path':item['path'],'state_sha256':item['sha256'],'model':model,'condition':condition,'served_model':served,'runtime':str(folder/'runtime'),'output':str(folder/'result.json')}
 frozen_json(folder/'job.json',job)
 if (folder/'result.json').exists():return
 with (folder/'worker.log').open('a') as log:
  proc=subprocess.run([cfg['paths']['appworld_python'],str(D/'scripts/worker.py'),'--job',str(folder/'job.json')],env=CPU,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
 if proc.returncode:raise RuntimeError(f'Worker failed: {folder}/worker.log')
 r=read(folder/'result.json');assert r['all_observations_exact'];print({'completed':f'{model}_{condition}/{ident}','actions':len(r['actions'])},flush=True)
def pool(jobs,stage):
 with concurrent.futures.ThreadPoolExecutor(max_workers=3) as p:
  fs=[p.submit(execute,*args) for args in jobs]
  for i,f in enumerate(concurrent.futures.as_completed(fs),1):f.result();status(stage,completed=i,total=len(jobs))
def main():
 pool([(x,None,'replay') for x in manifest['states']],'replaying_32_original_states')
 lock=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock'
 with lock.open('a+') as handle:
  fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB);require_free_gpu(cfg['server']['gpu'],80)
  os.environ['CUDA_VISIBLE_DEVICES']=cfg['server']['gpu']
  for model in ['base','ema36','student36']:
   conditions=['C0'] if model=='student36' else ['C0','C2']
   pending=[(s,c) for s in manifest['states'] for c in conditions if not(c=='C2' and s['stratum']=='clean') and not (D/f'runs/{model}_{c}'/s['id']/'result.json').exists()]
   if not pending:continue
   status('starting_inference_server',model=model,pending=len(pending))
   with owned_server(cfg,D/'logs'/model,None if model=='base' else str(D/'models'/model)) as served:
    pool([(s,model,c,served) for s,c in pending],f'generating_{model}')
  status('generation_and_execution_complete',branches=144)
if __name__=='__main__':main()
