"""Read-only experiment observer; writes only README and its own progress journal."""
from pathlib import Path
from datetime import datetime,timezone,timedelta
import argparse,fcntl,json,os,time
R=Path(__file__).resolve().parents[1]
START='<!-- AUTO_PROGRESS_START -->';END='<!-- AUTO_PROGRESS_END -->'
NAMES={'random':'Random','net3':'Net3','pass4':'Pass4','zerofail3':'ZeroFail3','highfail3':'HighFail3'}
def now():return datetime.now(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')
def read(p):
 try:return json.loads(p.read_text())
 except (FileNotFoundError,json.JSONDecodeError):return {}
def atomic(p,text):
 tmp=p.with_name(p.name+f'.tmp.{os.getpid()}');tmp.write_text(text);tmp.replace(p)
def refresh():
 state=read(R/'STATUS.json');cfg=read(R/'config/training.json');events_path=R/'runtime/progress_nodes.jsonl'
 events=[json.loads(s) for s in events_path.read_text().splitlines()] if events_path.exists() else [];known={e['key'] for e in events};new=[]
 def event(key,text,evidence):
  if key not in known:
   new.append({'key':key,'observed_at_beijing':now(),'event':text,'evidence':evidence});known.add(key)
 for rel,label in [('checks/data_validation.json','数据验收通过，11,254 步均保留'),('checks/loss_math.json','Loss 与梯度等价测试通过'),('probe/random/seed_20261015/COMPLETE.json','最长样本试跑完成')]:
  d=read(R/rel)
  if d.get('passed') or d.get('phase')=='complete':event(rel,label,rel)
 base=read(R/'evaluation/base/SUMMARY.json');base_status=read(R/'evaluation/base/STATUS.json')
 if base:event('base_complete',f"原始模型基线完成：{base['successes']}/{base['tasks']}",'evaluation/base/SUMMARY.json')
 rows=[];train_done=eval_done=0;current='等待状态';active_key=(state.get('arm'),state.get('seed'));stage=state.get('stage','unknown')
 for seed in cfg.get('seeds',[]):
  for arm in cfg.get('arms',[]):
   tr=f'training/{arm}/seed_{seed}';ev=f'evaluation/{arm}/seed_{seed}/epoch_01';p=read(R/tr/'PROGRESS.json');td=read(R/tr/'epoch_01.json');es=read(R/ev/'STATUS.json');ed=read(R/ev/'SUMMARY.json');name=f'{NAMES[arm]} / {seed}'
   update=p.get('update',p.get('updates',0));training='待开始';evaluation='待开始';result='—'
   if p:
    training=f"{update}/855（{update/855:.1%}）";event(tr+'/started',f'{name} 开始训练',tr+'/INITIALIZATION.json')
    for n in range(100,min(update,855)+1,100):event(tr+f'/update_{n}',f'{name} 训练已达到 {n}/855 次更新',tr+'/PROGRESS.json')
   if td:
    training='完成 855/855';train_done+=1;event(tr+'/complete',f'{name} 第 1 轮训练完成',tr+'/epoch_01.json')
   if es:
    evaluation=f"{es.get('completed',0)}/57";event(ev+'/started',f'{name} 开始 DEV57',ev+'/STATUS.json')
    for n in range(10,es.get('completed',0)+1,10):event(ev+f'/task_{n}',f'{name} 评测已达到 {n}/57 题',ev+'/STATUS.json')
   if ed:
    evaluation='完成 57/57';eval_done+=1;result=f"{ed['successes']}/57（{ed['TGC']:.2%}）";event(ev+'/complete',f'{name} DEV57 完成：{result}',ev+'/SUMMARY.json')
   rows.append(f'| {NAMES[arm]} | {seed} | {training} | {evaluation} | {result} |')
   if active_key==(arm,seed):
    if stage.startswith('train_'):current=f'**{name}，第 1 轮训练，{training}**'
    elif stage.startswith('eval_'):current=f'**{name}，DEV57 评测，{evaluation}**'
 if stage.startswith('eval_base'):current=f"**原始 Qwen3-8B 基线评测，{base_status.get('completed',0)}/57 题**"
 elif stage=='probe':current='**最长样本试跑**'
 elif stage=='summarize':current='**整理已完成评测结果**'
 if state.get('phase')=='complete':current='**全部实验已完成**';event('all_complete','全部五组、三个 seed 的单轮训练和评测完成','COMPLETE.json')
 if state.get('phase')=='error':current=f"**实验已停止，需处理错误**：{state.get('error','详见 STATUS.json')}";event('error/'+str(state.get('finished_at')),state.get('error','实验停止'),'STATUS.json')
 warning=''
 if state.get('phase')=='running':
  pid=state.get('pid');cmd=Path(f'/proc/{pid}/cmdline')
  alive=cmd.exists() and b'run_pipeline.py' in cmd.read_bytes()
  if not alive:warning='\n调度器进程已不存在；以上为最后记录，请检查 STATUS.json 和日志。\n'
  elif state.get('heartbeat_at'):
   age=(datetime.now(timezone.utc)-datetime.fromisoformat(state['heartbeat_at'])).total_seconds()
   if age>120:warning=f'\n调度器心跳已超过 {int(age)} 秒未更新，请检查进程。\n'
 events+=new
 if new:
  with events_path.open('a') as f:
   for e in new:f.write(json.dumps(e,ensure_ascii=False)+'\n')
 block=f'''{START}
## 当前进度

更新时间：**{now()}（北京时间）**。每 30 秒读取一次状态；不占用 GPU、不修改训练。

当前：{current}。

总体：训练 **{train_done}/15** 完成，微调模型评测 **{eval_done}/15** 完成；每次训练仅 1 轮、1,710 步、855 次更新。
'''
 if base:block+=f"\n原始模型基线：**{base['successes']}/57（{base['TGC']:.2%}）**，已完成。\n"
 block+=warning+'\n| 组别 | Seed | 训练更新 | DEV57 评测 | 最终成功率 |\n| --- | ---: | --- | --- | --- |\n'+'\n'.join(rows)+'\n\n### 最近节点\n\n'
 block+='节点时间为记录程序观察到该节点的北京时间；首次启用会补录已完成节点，不代表它们刚刚发生。\n\n'
 for e in events[-20:]:block+=f"- {e['observed_at_beijing']}：{e['event']}。\n"
 block+='\n记录训练开始、每 100 次更新、训练完成，以及评测开始、每 10 题、评测完成；具体更新数见上表。完整节点历史见 [progress_nodes.jsonl](runtime/progress_nodes.jsonl)。\n'
 block+=f"\n当前调度阶段：`{stage}`。调度器心跳：`{state.get('heartbeat_at','—')}`。\n"
 if state.get('active_log'):block+=f"\n[当前日志]({Path(state['active_log']).relative_to(R)}) · [原始状态](STATUS.json)\n"
 block+=f'\n{END}'
 p=R/'README.md';text=p.read_text()
 if START in text:
  before,rest=text.split(START,1);_,after=rest.split(END,1);text=before+block+after
 else:
  heading,rest=text.split('\n',1);text=heading+'\n\n'+block+'\n'+rest
 atomic(p,text)
 atomic(R/'runtime/readme_observer.json',json.dumps({'pid':os.getpid(),'updated_at_beijing':now(),'pipeline_phase':state.get('phase'),'node_count':len(events)},indent=2)+'\n')
 return state.get('phase') in ('complete','error')
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--watch',action='store_true');args=ap.parse_args()
 lock=(R/'runtime/readme_observer.lock').open('a+');fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
 while True:
  terminal=refresh()
  if not args.watch or terminal:break
  time.sleep(30)
if __name__=='__main__':main()
