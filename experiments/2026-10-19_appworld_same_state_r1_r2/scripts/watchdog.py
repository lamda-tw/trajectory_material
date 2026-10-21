"""Local, bounded, resumable supervisor. Never changes scientific inputs or scores."""
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
import argparse,fcntl,hashlib,json,os,shutil,signal,statistics,subprocess,sys,time
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,file_sha
from progress import refresh,update
TZ=ZoneInfo('Asia/Shanghai');PIPELINE=str(R/'scripts/run_phase1.py');GPU='GPU-35170b76-56ce-240a-19c0-0c092a3e8501'
STATE=R/'runtime/watchdog_state.json';TOTAL=2691

def now():return datetime.now(TZ).isoformat()
def read(p,default=None):
 try:return json.loads(p.read_text())
 except (OSError,ValueError):return default

def event(kind,detail,**extra):
 x={'time':now(),'kind':kind,'detail':detail,**extra}
 with (R/'MONITOR_EVENTS.jsonl').open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
 print(json.dumps(x,ensure_ascii=False),flush=True)

def process_table():
 out={}
 for p in Path('/proc').iterdir():
  if not p.name.isdigit():continue
  try:
   st=(p/'stat').read_text().rsplit(') ',1)[1].split()
   if st[0]=='Z':continue
   out[int(p.name)]={'ppid':int(st[1]),'birth':st[19],'cmd':(p/'cmdline').read_bytes().replace(b'\0',b' ').decode(errors='replace')}
  except (OSError,ValueError,IndexError):pass
 return out

def pipeline_pids(table):return [p for p,v in table.items() if PIPELINE+' --execute' in v['cmd']]

def track_children(state,table,pids):
 owned={int(p):birth for p,birth in state.get('owned_processes',{}).items() if p.isdigit() and int(p) in table and table[int(p)]['birth']==birth}
 family=set(pids)
 while True:
  new={p for p,v in table.items() if v['ppid'] in family}-family
  if not new:break
  family|=new
 for p in family:owned[p]=table[p]['birth']
 state['owned_processes']={str(p):b for p,b in owned.items()}

def stop_owned(state):
 # Only identities previously observed below this experiment's pipeline are owned.
 table=process_table();pids=[int(p) for p,b in state.get('owned_processes',{}).items() if int(p) in table and table[int(p)]['birth']==b]
 for sig in (signal.SIGTERM,signal.SIGKILL):
  for pid in reversed(pids):
   try:
    cur=process_table().get(pid)
    if cur and cur['birth']==state['owned_processes'][str(pid)]:os.kill(pid,sig)
   except ProcessLookupError:pass
  if sig==signal.SIGTERM:time.sleep(10)
 event('owned_cleanup','仅终止本实验已记录且启动时间匹配的进程。',pids=pids)

def counts():
 generated=list((R/'results/generations').glob('*/*.json'));paired=list((R/'results/paired_checks').glob('*/*.json'))
 return {'generated':len(generated),'paired':len(paired),'paired_valid':sum(bool(read(p,{}).get('execution_valid')) for p in paired),'scored':len(list((R/'judge_runs/actions').glob('*/judgement.json'))),'reviewed':len(list((R/'judge_runs/review_repeat').glob('*/*/judgement.json'))),'reference_evaluators':len(list((R/'results/evaluators/reference').glob('*.before.json')))},generated,paired

def estimate(c,generated,paired,status):
 if c['reviewed']>=72 and (R/'REPORT.md').exists():return '已完成或正在写最终报告'
 def remaining(paths,n):
  if len(paths)<20:return None
  elapsed=time.time()-min(p.stat().st_mtime for p in paths)
  return max(0,n-len(paths))*elapsed/max(1,len(paths)-1)/3600
 gen=remaining(generated,TOTAL);exe=remaining(paired,TOTAL)
 if gen is None or exe is None:return '暂估6–10小时；依据校准评分45–71秒/条、8并发，正式吞吐尚在测速'
 if c['generated']==TOTAL:
  common=read(R/'analysis/common_states.json',{});n_unique=status.get('nodes',{}).get('行为评分与72条复核',{}).get('unique_total',TOTAL)
 else:n_unique=TOTAL
 scoreleft=max(0,n_unique-c['scored']);reviewleft=72-c['reviewed']
 # Before full generation completes, unique evidence count is unknown; budget all rows.
 base=max(gen,exe)
 lower=base*.85+(scoreleft*45+reviewleft*45)/8/3600
 upper=base*1.4+(scoreleft*75+reviewleft*75)/8/3600+.25
 finish=datetime.now(TZ)+timedelta(hours=upper)
 return f'约{lower:.1f}–{upper:.1f}小时（按当前吞吐，评分去重前按最多2691条估算；上界对应北京时间{finish:%m-%d %H:%M}；不含后续故障/外部排队）'

def frozen_ok():
 gate=read(R/'config/calibration_accepted.json',{})
 return gate.get('accepted') and gate.get('evaluator_verified') and all(file_sha(R/p)==sha for p,sha in gate['frozen_files'].items())

def fault(status):
 detail=status.get('current_detail','')
 logpath=R/'logs/pipeline.log';tail=logpath.read_text(errors='replace')[-12000:] if logpath.exists() else ''
 # Equality/protocol/data failures cannot be repaired by changing criteria or rerolling.
 bad=['Frozen protocol changed','Model input token mismatch','Judge exhausted bounded retries','Evaluator disk snapshot != actual branch database','Server changed the supplied prompt tokens.','token IDs and logprob tokens disagree']
 combined=detail+'\n'+tail
 # The tail may contain an old, already resolved exception; use current error's worker log.
 if '; see ' in detail:
  raw=detail.split('; see ',1)[1].split("')",1)[0]
  p=Path(raw)
  if p.is_relative_to(R) and p.exists():combined=detail+'\n'+p.read_text(errors='replace')[-6000:]
 if any(t in combined for t in bad):return 'integrity',detail
 if status.get('status')=='error' and any(x in combined for x in ['AssertionError','KeyError','TypeError','ValueError']):return 'integrity',detail
 return 'transient',detail or 'pipeline进程消失'

def launch(state):
 assert frozen_ok(),'Frozen protocol changed'
 with (R/'logs/pipeline.log').open('a') as log:
  p=subprocess.Popen([sys.executable,PIPELINE,'--execute'],cwd=R,env=dict(os.environ,PYTHONUNBUFFERED='1',PYTHONHASHSEED='0'),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
 (R/'runtime/pipeline.pid').write_text(str(p.pid)+'\n');state['last_launch']=time.time();state['last_progress_time']=time.time()
 event('pipeline_started','从已保存产物断点继续；成功生成/评分不重采。',pid=p.pid)
 return p.pid

def tick(state,manage=True):
 status=read(R/'STATUS.json',{});table=process_table();pids=pipeline_pids(table);track_children(state,table,pids)
 c,generated,paired=counts();signature=json.dumps(c,sort_keys=True)
 if signature!=state.get('last_counts'):
  state['last_counts']=signature;state['last_progress_time']=time.time();state['same_failure_restarts']=0
 free=round(shutil.disk_usage(R).free/2**30,1);detail='运行正常；按断点推进。';mode='running';complete=status.get('current_node')=='evaluator与报告' and status.get('status')=='complete' and (R/'REPORT.md').exists()
 gpu=subprocess.run(['nvidia-smi','--query-gpu=index,uuid,memory.used,memory.free,utilization.gpu','--format=csv,noheader'],capture_output=True,text=True,timeout=15)
 if complete:mode='complete';detail='实验、评分和最终报告已完成；守护进程自动退出。'
 elif state.get('blocked'):
  mode='needs_attention';detail=state['blocked']
 elif not frozen_ok():
  state['blocked']='冻结文件哈希异常；停止自动恢复，保留产物。';mode='needs_attention';detail=state['blocked']
  if manage:stop_owned(state)
 elif free<10:
  mode='waiting_disk';detail='工作盘空闲不足10GiB；只暂停本实验并保留全部结果，每5分钟复查。'
  if manage and pids:stop_owned(state);state['disk_paused']=True;pids=[]
 elif len(pids)>1:
  state['blocked']='检测到多个pipeline进程；停止自动启动，避免重复采样。';mode='needs_attention';detail=state['blocked']
 elif pids:
  node=status.get('nodes',{}).get(status.get('current_node'),{})
  waiting_gpu=node.get('status_detail')=='waiting_gpu1'
  if waiting_gpu:mode='waiting_gpu1';detail='GPU1暂被占用，原流程等待；不使用GPU0，不终止其他任务。'
  elif time.time()-state.get('last_progress_time',time.time())>7200:
   if manage:stop_owned(state);state['last_progress_time']=time.time();event('stalled','120分钟没有新产物；结束本实验进程，下一次检查断点重启。')
   mode='recovering';detail='120分钟无新产物，处理本实验卡住的进程。'
 elif manage:
  category,reason=fault(status)
  if state.pop('disk_paused',False):category='transient';reason='磁盘空间已恢复'
  if category=='integrity':
   state['blocked']='一致性/协议或有界评分重试异常，需要检查，未改评分或舍弃状态：'+reason;mode='needs_attention';detail=state['blocked'];stop_owned(state);event('needs_attention',detail)
  else:
   digest=hashlib.sha256(reason.encode()).hexdigest()
   if digest!=state.get('last_failure'):state['same_failure_restarts']=0;state['last_failure']=digest
   n=state.get('same_failure_restarts',0);total=state.get('total_restarts',0)
   if n>=3 or total>=8:
    state['blocked']='同一故障3次或累计8次断点恢复后仍失败；停止重复重启并保留错误。'+reason;mode='needs_attention';detail=state['blocked'];stop_owned(state);event('needs_attention',detail)
   else:
    stop_owned(state);pids=[launch(state)];state['same_failure_restarts']=n+1;state['total_restarts']=total+1;mode='recovering';detail=f'暂态故障后第{n+1}次断点恢复；总恢复{total+1}次。'
 health={'checked_at':now(),'monitor_status':mode,'detail':detail,'counts':c,'eta':estimate(c,generated,paired,status),'disk_free_gib':free,'pipeline_pid':pids[0] if pids else None,'monitor_pid':os.getpid(),'gpu_status':gpu.stdout.strip(),'total_restarts':state.get('total_restarts',0),'interval_seconds':300}
 atomic_json(R/'HEALTH.json',health);atomic_json(STATE,state);refresh()
 event('health_check',detail,counts=c,eta=health['eta'],free_gib=free)
 return complete

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--once',action='store_true');a=ap.parse_args()
 if a.once:tick(read(STATE,{}),manage=False);return
 lock=(R/'runtime/watchdog.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
 (R/'runtime/watchdog.pid').write_text(str(os.getpid())+'\n');state=read(STATE,{})
 event('monitor_started','每5分钟检查并更新README；每30秒记录本实验子进程归属，仅GPU1。')
 while True:
  try:
   if tick(state):return
  except Exception as e:
   event('monitor_error',repr(e));atomic_json(STATE,state)
  for _ in range(10):
   time.sleep(30);table=process_table();track_children(state,table,pipeline_pids(table));atomic_json(STATE,state)
if __name__=='__main__':main()
