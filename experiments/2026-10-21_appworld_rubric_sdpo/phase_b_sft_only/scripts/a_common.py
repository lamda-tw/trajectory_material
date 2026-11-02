"""Phase A execution helpers; no work runs on import."""
from common import R, W, read, write_json, frozen_json, digest, now, check_frozen
from pathlib import Path
from contextlib import contextmanager
import os, sys, json, hashlib, math, re, subprocess, fcntl
sys.path.insert(0,str(R/'runtime_code'))
GPU='GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
CPU=dict(os.environ,CUDA_VISIBLE_DEVICES='',HIP_VISIBLE_DEVICES='',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONHASHSEED='0',PYTHONUNBUFFERED='1',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1')
atomic_json=write_json
def file_sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''):h.update(block)
 return h.hexdigest()
def parse_code(text):
 m=re.search(r'```python\n(.*?)```',text,re.S)
 if m:return m.group(1).strip(),text
 m=re.search(r'```python\n(.*)',text,re.S)
 return (m.group(1).strip(),text.rstrip()+'\n```') if m else ('',text)
def validate_tokens(prompt_ids,response_ids,old_logprobs):
 if not prompt_ids or len(response_ids)!=len(old_logprobs):raise ValueError('Misaligned token IDs')
 if any(type(t) is not int or t<0 for t in prompt_ids+response_ids):raise ValueError('Invalid token IDs')
 if any(type(x) not in (int,float) or not math.isfinite(x) or x>1e-5 for x in old_logprobs):raise ValueError('Invalid log probabilities')
def config():return read(R/'config/phase_a_runtime.json')
def authorize():
 g=read(R/'config/execution_gate.json');assert g['gpu_allowed'] and g['candidate_execution_allowed'] and g['qwen_generation_allowed'] and not g['training_allowed']
 assert read(R/'config/phase_a_execution_authorization.json')['physical_gpu']==1
 check_frozen()
def status(stage,**values):
 d={'updated_at':now(),'stage':stage,'phase':'A','gpu_allowed':True,'physical_gpu':1,'training_started':False,'training_updates':0,'phase_b_started':False,'phase_c_started':False,**values}
 write_json(R/'STATUS.json',d);print(json.dumps(d,ensure_ascii=False),flush=True)
def packages(stage):
 name='calibration_manifest.json' if stage=='calibration' else 'manifest.json'
 out=[]
 for x in read(R/'phase_a/ready'/name)['states']:
  p=R/x['path'];assert file_sha(p)==x['sha256'];out.append((x,read(p)))
 return out
def require_free_gpu(gpu,minimum):
 assert gpu==GPU
 lines=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.free','--format=csv,noheader,nounits'],text=True).splitlines()
 row=[x.split(',') for x in lines if GPU in x];assert len(row)==1 and row[0][0].strip()=='1'
 assert int(row[0][2].strip())>=minimum*1024,'GPU1 has insufficient free memory'
 procs=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader'],text=True)
 assert not any(x.split(',')[0].strip()==GPU for x in procs.splitlines()),'GPU1 is occupied; do not preempt'
@contextmanager
def gpu_lock():
 authorize();p=W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock';p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('a+') as f:
  fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB);require_free_gpu(GPU,config()['server']['minimum_free_gpu_gib'])
  old=os.environ.get('CUDA_VISIBLE_DEVICES');os.environ['CUDA_VISIBLE_DEVICES']=GPU
  try:yield
  finally:
   if old is None:os.environ.pop('CUDA_VISIBLE_DEVICES',None)
   else:os.environ['CUDA_VISIBLE_DEVICES']=old
   fcntl.flock(f,fcntl.LOCK_UN)
