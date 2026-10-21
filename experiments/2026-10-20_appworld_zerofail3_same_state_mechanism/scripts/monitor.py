"""Read-only workload monitor; never allocates a GPU or touches another task's processes."""
from experiment import *
from progress import refresh,now
import shutil
from datetime import datetime

def estimate_remaining(status,counts):
 if (R/'config/experiment_completed.json').exists():return '已完成'
 node=status['current_node']
 field,total=('formal_continuations',540) if node=='540个固定策略续跑分支' else ('formal_paired',1161) if node=='1161个首步生成与执行' else ('formal_cards',129) if node=='129张正式前缀卡' else (None,None)
 scoring=node=='行为评分与54条复核'
 reviewing=scoring and '同评委独立上下文复核' in status.get('current_detail','')
 if scoring:
  field='repeat_scored' if reviewing else 'unique_actions_scored'
  total=status['nodes'][node].get('total',54 if reviewing else 671)
 if field and (R/'MONITOR_EVENTS.jsonl').exists():
  history=[json.loads(x) for x in (R/'MONITOR_EVENTS.jsonl').read_text().splitlines()[-25:]]
  current=datetime.fromisoformat(now()).timestamp()
  candidates=[h for h in history if h.get('detail','').startswith('当前'+node+'；') and (not reviewing or h.get('counts',{}).get('repeat_scored',0)>0) and 300<=current-datetime.fromisoformat(h['checked_at']).timestamp()<=3600 and counts[field]>h.get('counts',{}).get(field,0)]
  if candidates:
   h=candidates[0];elapsed=current-datetime.fromisoformat(h['checked_at']).timestamp();done=counts[field]-h['counts'].get(field,0)
   remaining=max(0,total-counts[field]);extra=0
   if scoring and not reviewing:
    common=read(R/'analysis/common_states.json')['state_ids']
    extra=sum(x['state_id'] in common for x in read(R/'plan_snapshot/review_manifest.json')['rows'])-counts['repeat_scored']
   hours=(remaining+max(0,extra))*elapsed/done/3600
   if scoring:
    return f'按近期真实节点速度，评分及预选复核约{hours:.1f}小时；另预计续跑4–7小时、统计与报告0.3–0.5小时，合计约{hours+4.3:.1f}–{hours+7.5:.1f}小时。不含GPU等待；续跑开始后按实测速率替换估计'
   return f'按最近完成速度，当前阶段约还需{hours:.1f}小时；不含后续阶段及GPU等待。全流程原计划7–15小时，不能保证GPU持续空闲'
 return '尚无足够正式吞吐估计；全流程原计划7–15小时（总工期，非滚动剩余时间），另计GPU等待'

def live(pidfile):
 try:
  pid=int(pidfile.read_text());stat=Path(f'/proc/{pid}/stat').read_text().rsplit(') ',1)[1].split();return pid if stat[0]!='Z' else None
 except (OSError,ValueError):return None

def tick():
 status=read(R/'STATUS.json');gpu=gpu_status();c={'calibration_generated':len(list((R/'results/generations').glob('calibration_*/*.json'))),'formal_generated':sum(len(list((R/'results/generations'/model_key(m)).glob('*.json'))) for m in models()),'formal_paired':len(list((R/'results/paired_checks').glob('*/*.json'))),'formal_cards':len(list((R/'judge_runs/cards').glob('*/judgement.json'))),'unique_actions_scored':len(list((R/'judge_runs/actions').glob('*/judgement.json'))),'repeat_scored':len(list((R/'judge_runs/review_repeat').glob('*/*/judgement.json'))),'formal_continuations':len(list((R/'results/continuation_checks/continuation').glob('*/*/*.json'))),'calibration_continuations':len(list((R/'results/continuation_checks/calibration_continuation').glob('*/*/*.json')))}
 complete=(R/'config/experiment_completed.json').exists();mode='complete' if complete else status['status']
 detail='实验与最终报告已完成。' if complete else f"当前{status['current_node']}；校准动作{c['calibration_generated']}/27，正式首步{c['formal_generated']}/1161，正式续跑{c['formal_continuations']}/540。"
 if status['current_node']=='行为评分与54条复核':detail+=f"主评分完成{c['unique_actions_scored']}种不同证据，重复复核{c['repeat_scored']}条；当前GPU空闲属阶段安排。"
 health={'checked_at':now(),'monitor_status':mode,'detail':detail,'gpu1_status':f"显存{gpu['used_mib']} MiB，利用率{gpu['utilization_percent']}%，计算进程{gpu['pids']}",'gpu1':gpu,'counts':c,'disk_free_gib':round(shutil.disk_usage(R).free/2**30,1),'calibration_pid':live(R/'runtime/calibration_gpu.pid'),'pipeline_pid':live(R/'runtime/pipeline.pid'),'monitor_pid':live(R/'runtime/monitor.pid'),'eta':estimate_remaining(status,c),'interval_seconds':300,'no_process_termination':True}
 atomic_json(R/'HEALTH.json',health);refresh()
 with (R/'MONITOR_EVENTS.jsonl').open('a') as f:f.write(json.dumps(health,ensure_ascii=False)+'\n')
 print(json.dumps(health,ensure_ascii=False),flush=True);return complete

def main():
 with (R/'runtime/monitor.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);(R/'runtime/monitor.pid').write_text(str(os.getpid())+'\n')
  while True:
   try:
    if tick():break
   except Exception as e:print(repr(e),flush=True)
   time.sleep(300)
if __name__=='__main__':main()
