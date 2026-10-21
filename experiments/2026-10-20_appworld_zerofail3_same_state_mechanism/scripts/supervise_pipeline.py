"""Bounded process-level recovery of this experiment only; no reroll or integrity-rule changes."""
from experiment import *
from progress import now
import shutil

def event(kind,detail,**values):
 with (R/'SUPERVISION_EVENTS.jsonl').open('a') as f:f.write(json.dumps({'time':now(),'kind':kind,'detail':detail,**values},ensure_ascii=False)+'\n')
 print(json.dumps({'kind':kind,'detail':detail,**values},ensure_ascii=False),flush=True)

def processes():
 result={}
 for path in Path('/proc').iterdir():
  if not path.name.isdigit():continue
  try:
   value=(path/'stat').read_text().rsplit(') ',1)[1].split()
   if value[0]!='Z':result[int(path.name)]={'ppid':int(value[1]),'birth':value[19]}
  except (OSError,ValueError,IndexError):pass
 return result

def track_owned(root,owned):
 table=processes();family={root} if root in table else set()
 while True:
  new={p for p,v in table.items() if v['ppid'] in family}-family
  if not new:break
  family|=new
 for p in family:owned[str(p)]=table[p]['birth']
 return owned

def stop_owned(owned):
 table=processes();targets=[int(p) for p,b in owned.items() if int(p) in table and table[int(p)]['birth']==b]
 for sig in [signal.SIGTERM,signal.SIGKILL]:
  for pid in reversed(targets):
   current=processes().get(pid)
   if current and current['birth']==owned[str(pid)]:
    try:os.kill(pid,sig)
    except ProcessLookupError:pass
  if sig==signal.SIGTERM:time.sleep(10)
 event('owned_cleanup','仅清理本实验已追踪且启动时间匹配的进程。',pids=targets)

def check_frozen():
 from run_phase1 import verify_gate
 verify_gate()

def main():
 with (R/'runtime/supervisor.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);(R/'runtime/supervisor.pid').write_text(str(os.getpid())+'\n')
  statepath=R/'runtime/supervision.json';state=read(statepath) if statepath.exists() else {'launches':0,'same_failure_restarts':0}
  while True:
   if (R/'config/computed_report_ready.json').exists():event('ready_for_review','计算报告已完成，监督器退出；不自动声称研究解释已核查。');return
   check_frozen()
   if shutil.disk_usage(R).free/2**30<10:
    update('统计核验与详细报告','工作盘不足10GiB，等待空间恢复；不删除历史数据。','waiting_disk');time.sleep(30);continue
   # The pipeline's OS lock prevents duplicate computation even if a prior run exists.
   with (R/'runtime/pipeline.lock').open('a+') as pf:
    try:fcntl.flock(pf,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:time.sleep(30);continue
    fcntl.flock(pf,fcntl.LOCK_UN)
   state['launches']+=1;atomic_json(statepath,state)
   logpath=R/'logs/pipeline.log'
   with logpath.open('a') as log:
    marker=f'PIPELINE_START {state["launches"]} {now()}';log.write('\n'+marker+'\n');log.flush()
    p=subprocess.Popen([sys.executable,'-u',str(R/'scripts/pipeline.py')],cwd=R,env=dict(os.environ,PYTHONHASHSEED='0',PYTHONUNBUFFERED='1',CUDA_VISIBLE_DEVICES=''),stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    event('pipeline_started','启动/断点恢复本实验；已保存有效生成与评分不重采。',pid=p.pid,launch=state['launches'])
    owned={};last_progress=time.time();last_stamp=0
    while p.poll() is None:
     track_owned(p.pid,owned);atomic_json(R/'runtime/owned_pipeline_processes.json',owned)
     status=read(R/'STATUS.json');stamp=(R/'STATUS.json').stat().st_mtime
     if stamp!=last_stamp:last_stamp=stamp;last_progress=time.time()
     low_disk=shutil.disk_usage(R).free/2**30<10
     stalled=time.time()-last_progress>7200 and status.get('status')!='waiting_gpu1'
     if low_disk or stalled:
      event('pause_owned','磁盘低于10GiB或120分钟无节点进展，保留输出并清理本实验进程。',low_disk=low_disk,stalled=stalled);stop_owned(owned);break
     time.sleep(30)
    code=p.wait()
    if code:stop_owned(owned)
   if code==0:continue
   text=logpath.read_text(errors='replace').split(marker)[-1];reason=read(R/'STATUS.json').get('current_detail','')
   bad=['AssertionError','KeyError','TypeError','ValueError','mismatch','changed','exhausted','unsupported','integrity']
   if any(s.lower() in (reason+'\n'+text).lower() for s in bad):
    event('needs_attention','一致性/协议或请求重试耗尽，停止自动重启，保留证据。',reason=reason);atomic_json(R/'config/requires_attention.json',{'reason':reason,'time':now(),'pipeline_exit_code':code});return
   signature=digest(reason)
   state['same_failure_restarts']=state['same_failure_restarts']+1 if state.get('last_failure')==signature else 1;state['last_failure']=signature;atomic_json(statepath,state)
   if state['same_failure_restarts']>=3 or state['launches']>=6:
    event('needs_attention','已到有界进程恢复次数，停止自动重启。',reason=reason);atomic_json(R/'config/requires_attention.json',{'reason':reason,'time':now(),'bounded_restarts_exhausted':True});return
   event('transient_retry','基础设施进程暂态错误，30秒后恢复。',reason=reason);time.sleep(30)
if __name__=='__main__':main()
