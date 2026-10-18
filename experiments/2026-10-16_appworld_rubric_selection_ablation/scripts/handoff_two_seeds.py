"""Keep the current trainer running, then continue the two-seed scheduler."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import json,os,time,fcntl,sys
R=Path(__file__).resolve().parents[1];W=R.parents[1]
def write(state):
 p=R/'STATUS.json';q=p.with_suffix('.handoff.tmp');q.write_text(json.dumps(state,indent=2)+'\n');q.replace(p)
def now():return datetime.now(timezone(timedelta(hours=8))).isoformat()
scope=json.loads((R/'runtime/execution_scope.json').read_text());child=scope['preserved_training_pid'];state=scope['preserved_stage'];state.update(pid=os.getpid(),runs=10,active_seeds=scope['active_seeds'],handoff='Existing training continues unchanged; next scheduler excludes third seed')
lock=(W/'experiments/2026-10-14_appworld_sft_init_joint_rl_local_sft/runtime/gpu1.lock').open('a+');fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
own=(R/'runtime/pipeline.lock').open('a+');fcntl.flock(own.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
try:
 while True:
  p=Path(f'/proc/{child}/stat')
  if not p.exists() or p.read_text().split()[2]=='Z':break
  assert b'train.py' in Path(f'/proc/{child}/cmdline').read_bytes(),'PID identity changed'
  state['heartbeat_at']=now();write(state);time.sleep(15)
 done=R/f"training/{state['arm']}/seed_{state['seed']}/epoch_01.json"
 assert done.exists(),'Trainer exited without complete epoch; inspect existing log and resume checkpoint'
 d=json.loads(done.read_text());assert d['phase']=='complete' and d['samples']==1710 and d['cumulative_updates']==855
 state.update(stage='handoff_to_two_seed_scheduler',heartbeat_at=now());write(state)
 own.close();lock.close()
 os.execv(sys.executable,[sys.executable,'-u',str(R/'scripts/run_pipeline.py'),'--execute'])
except BaseException as e:
 state.update(phase='error',error=repr(e),heartbeat_at=now());write(state);raise
