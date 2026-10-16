from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib,json,os,subprocess
ROOT=Path(__file__).resolve().parents[1]
WORKSPACE=ROOT.parents[1]
def now(): return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
def read(p): return json.loads(Path(p).read_text())
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for block in iter(lambda:f.read(8*1024*1024),b''): h.update(block)
 return h.hexdigest()
def dump(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);t=p.with_name(p.name+'.tmp');t.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n');os.replace(t,p)
def jsonl(p,rows):
 p=Path(p);t=p.with_name(p.name+'.tmp')
 with t.open('w') as f:
  for x in rows:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 os.replace(t,p)
def require(test,message):
 if not test:raise ValueError(message)
def gpu_env():
 p=read(ROOT/'config/resource_policy.json')
 require(p['physical_gpu_indices']==[1] and p['forbidden_physical_gpu_indices']==[0],'GPU policy mismatch')
 require(p['cuda_visible_devices']==p['physical_gpu_uuid'] and p['world_size']==1,'GPU UUID/world size mismatch')
 return {**os.environ,'CUDA_VISIBLE_DEVICES':p['physical_gpu_uuid'],'CUDA_DEVICE_ORDER':'PCI_BUS_ID','TOKENIZERS_PARALLELISM':'false','PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1'}
def run(cmd,timeout=180):
 result=subprocess.run(cmd,env=gpu_env(),text=True,capture_output=True,timeout=timeout)
 with (ROOT/'commands.jsonl').open('a') as f:f.write(json.dumps({'at':now(),'argv':cmd,'CUDA_VISIBLE_DEVICES':gpu_env()['CUDA_VISIBLE_DEVICES'],'returncode':result.returncode})+'\n')
 return result
