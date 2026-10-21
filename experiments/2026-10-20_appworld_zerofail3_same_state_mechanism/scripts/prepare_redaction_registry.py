"""Local privacy-only registry. Never enters policy, judge evidence, or metrics."""
from experiment import *
import argparse

def task_registry(task):
 runtime=R/'runtime/redaction'/task;runtime.mkdir(parents=True,exist_ok=True)
 if not (runtime/'data').exists():(runtime/'data').symlink_to(C['paths']['appworld_data'],target_is_directory=True)
 os.environ['APPWORLD_ROOT']=str(runtime);os.environ['APPWORLD_CACHE']=str(runtime/'cache');os.chdir(runtime)
 from appworld import AppWorld,update_root
 update_root(str(runtime))
 with AppWorld(task_id=task,experiment_name='redaction_only',load_ground_truth=False,random_seed=100) as world:
  values=[x['password'] for x in world.apis.supervisor.show_account_passwords()]
 assert values and all(isinstance(x,str) and x for x in values)
 atomic_json(R/'runtime/redaction_credentials'/f'{task}.json',values)

def main():
 tasks=sorted({x['task_id'] for x in rows()+rows('calibration_states.csv')})
 def one(task):
  dest=R/'runtime/redaction_credentials'/f'{task}.json'
  if not dest.exists():run_worker([C['paths']['appworld_python'],__file__,'--task',task],R/'logs/redaction'/f'{task}.log')
  return {'task_id':task,'credential_count':len(read(dest)),'registry_sha256':file_sha(dest)}
 result=list(ThreadPoolExecutor(max_workers=4).map(one,tasks))
 atomic_json(R/'config/redaction_registry_audit.json',{'complete':True,'tasks':result,'use':'Local replacement only; never supplies unknown values or account metadata to policy/judge.'})
 print(json.dumps({'tasks':len(result),'complete':True}),flush=True)

if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--task');args=ap.parse_args()
 if args.task:task_registry(args.task)
 else:main()
