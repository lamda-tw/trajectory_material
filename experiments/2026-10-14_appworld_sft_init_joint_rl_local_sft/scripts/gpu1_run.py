"""Launch a process pinned to the verified physical GPU1 UUID, never GPU0.
Usage: python scripts/gpu1_run.py -- <executable> <arguments...>
Every future GPU entrypoint must use this launcher and preserve its child environment.
"""
from common import *
import sys,fcntl
if __name__=='__main__':
 argv=sys.argv[1:]
 if argv and argv[0]=='--':argv=argv[1:]
 require(bool(argv),'Expected executable and arguments')
 p=read(ROOT/'config/resource_policy.json')
 q=subprocess.run(['nvidia-smi','--id=1','--query-gpu=uuid','--format=csv,noheader'],text=True,capture_output=True,check=True)
 require(q.stdout.strip()==p['physical_gpu_uuid'],'GPU1 UUID changed; refuse automatic remapping')
 lock=open(ROOT/'runtime/gpu1.lock','a+')
 try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 except BlockingIOError:raise RuntimeError('This experiment already owns GPU1; wait for its active phase')
 os.set_inheritable(lock.fileno(),True)
 env=gpu_env();env['WORLD_SIZE']='1';env['LOCAL_WORLD_SIZE']='1';env['LOCAL_RANK']='0';env['RANK']='0'
 with (ROOT/'commands.jsonl').open('a') as f:f.write(json.dumps({'at':now(),'launcher':'gpu1_run','argv':argv,'physical_gpu_index':1,'CUDA_VISIBLE_DEVICES':env['CUDA_VISIBLE_DEVICES']})+'\n')
 os.execvpe(argv[0],argv,env)
