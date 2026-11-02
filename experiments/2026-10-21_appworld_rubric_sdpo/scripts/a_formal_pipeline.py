"""Run authorized phase A to automatic results, stopping before any training."""
from a_common import *
from a_candidates import jobs,path_for
import signal,time,argparse
def main(wait_for_cached_generation=False):
 authorize();gate=read(R/'phase_a/config/calibration_execution_gate.json');assert gate['allow_formal_generation']
 for rel,expected in gate['frozen_execution_files'].items():assert file_sha(R/rel)==expected,rel
 logs=R/'logs/formal_pipeline';logs.mkdir(parents=True,exist_ok=True)
 frozen_json(R/'phase_a/config/formal_pipeline_manifest.json',{'pipeline_sha256':file_sha(__file__),'calibration_gate_sha256':file_sha(R/'phase_a/config/calibration_execution_gate.json'),'formal_replay_eligibility_sha256':file_sha(R/'phase_a/config/formal_replay_eligibility.json'),'planned_candidates':len(jobs('formal')),'physical_gpu':1,'training_allowed':False,'wait_for_existing_generator':wait_for_cached_generation})
 write_json(R/'runtime/formal_pipeline_process.json',{'pid':os.getpid(),'started_at':now(),'script':str(Path(__file__).resolve())})
 children=[]
 def start(name,python,script,args):
  log=(logs/(name+'.log')).open('a');proc=subprocess.Popen([python,str(R/'scripts'/script),*args],env=CPU,stdout=log,stderr=subprocess.STDOUT,start_new_session=True);children.append((proc,log));return proc
 def finish(proc,name):
  code=proc.wait()
  if code:raise RuntimeError(f'{name} exited {code}; inspect {logs/name}.log')
 try:
  status('formal_pipeline_started',planned_candidates=len(jobs('formal')),waiting_for_existing_generator=wait_for_cached_generation)
  if wait_for_cached_generation:
   deadline=time.monotonic()+3600;todo=jobs('formal')
   while True:
    current=read(R/'STATUS.json')
    complete=all(path_for('formal',j).exists() for j in todo)
    if complete and current.get('stage')=='formal_generation_complete' and current.get('model_server_released'):break
    if time.monotonic()>deadline:raise TimeoutError('Existing generator did not finish within one hour; cached actions preserved')
    time.sleep(5)
  gen=start('generation',sys.executable,'a_candidates.py',['--stage','formal','--action','generate']);finish(gen,'generation')
  status('formal_generation_complete_starting_execution_and_diagnostics',generated=len(jobs('formal')))
  execute=start('execution',sys.executable,'a_candidates.py',['--stage','formal','--action','execute'])
  diagnostic=start('distribution',config()['paths']['training_python'],'a_distribution.py',['--stage','formal'])
  finish(execute,'execution')
  judge=start('judging',config()['paths']['training_python'],'a_judge_v2.py',['--stage','formal'])
  finish(judge,'judging');finish(diagnostic,'distribution')
  analyze=start('analysis',config()['paths']['training_python'],'a_analyze.py',['--stage','formal']);finish(analyze,'analysis')
  status('formal_automatic_results_ready_assistant_review_pending',candidate_rows=read(R/'phase_a/analysis/formal/summary.json')['candidate_rows'],training_updates=0)
 except BaseException as e:
  status('formal_pipeline_needs_attention',error=str(e),training_updates=0)
  raise
 finally:
  for proc,log in children:
   if proc.poll() is None:
    os.killpg(proc.pid,signal.SIGTERM)
    try:proc.wait(timeout=30)
    except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
   log.close()
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--wait-for-cached-generation',action='store_true');main(p.parse_args().wait_for_cached_generation)
