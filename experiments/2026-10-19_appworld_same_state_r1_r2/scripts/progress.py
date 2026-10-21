from pathlib import Path
from contextlib import contextmanager
import fcntl,json,os,threading
from datetime import datetime
from zoneinfo import ZoneInfo
R=Path(__file__).resolve().parents[1]
LOCK=threading.Lock()
NODES=['授权与GPU1核对','输入token核验','双重重放校准','评分校准与协议冻结','299张正式前缀卡','正式状态重放核验','正式单步生成与执行','行为评分与72条复核','evaluator与报告']
@contextmanager
def locked():
 with LOCK:
  (R/'runtime').mkdir(exist_ok=True)
  with (R/'runtime/progress.lock').open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);yield

def render(d):
 node=d['current_node'];detail=d['current_detail'];state=d['status'];now=d['updated_at']
 lines=['# 全规则1358 / DropR1 / DropR2 同状态动作比较','',f'实验节点更新时间（北京时间）：{now}',f'\n**当前节点：{node}；{state}。** {detail}', '', '9个已有adapter：全规则1358（DropR5）、DropR1、DropR2，各seed 20261015/16/17。299个正式状态：主面板171，E/R/D/S各32。校准8状态不入正式统计。仅物理GPU1；无新训练，不运行旧ZeroFail3或可选续跑。','', '| 节点 | 状态 | 说明 |','| --- | --- | --- |']
 for n in NODES:
  v=d['nodes'].get(n,{});lines.append(f"| {n} | {v.get('status','pending')} | {v.get('detail','未开始')} |")
 health=R/'HEALTH.json'
 if health.exists():
  h=json.loads(health.read_text());counts=h.get('counts',{})
  lines+=['','## 无人值守检查','',f"最近检查（北京时间）：{h['checked_at']}；监控状态：**{h['monitor_status']}**。",f"{h.get('detail','')}",f"动作生成 {counts.get('generated',0)}/2691；配对执行 {counts.get('paired',0)}/2691；有效配对 {counts.get('paired_valid',0)}；不同证据评分 {counts.get('scored',0)}；重复复核 {counts.get('reviewed',0)}/72。",f"预计剩余：{h.get('eta','首次正式批次测速后更新')}。",f"工作盘空闲 {h.get('disk_free_gib','未知')} GiB；pipeline PID：{h.get('pipeline_pid')}；监控 PID：{h.get('monitor_pid')}。",'每5分钟检查进程、产物、磁盘和GPU；网络/进程暂态异常按断点重启，已成功的动作和评分不重采。完成后监控自动退出；未知一致性/协议错误会停止并保留错误记录。', '- [机器可读检查状态](HEALTH.json) / [监控事件](MONITOR_EVENTS.jsonl) / [监控日志](logs/watchdog.log)。']
 incident=R/'INCIDENTS.md'
 if incident.exists():lines+=['','## 异常与修复','',incident.read_text().strip()]
 lines+=['','- [实时状态](STATUS.json) / [全部节点记录](EVENTS.jsonl)。','- [冻结计划](plan_snapshot/SAME_STATE_PLAN.md) / [评价协议](plan_snapshot/STATE_JUDGING.md) / [状态清单](plan_snapshot/states_selected.csv)。','- [本次授权](config/authorization.json) 覆盖快照中启动前“未授权”说明；[运行配置](config/runtime.json)。','- 原始重放/评分/生成文件本地保存在 calibration/raw、inputs、results、judge_runs；含任务数据，默认不进入git。','', '实时终端查看：`cat STATUS.json`、`cat HEALTH.json` 或 `tail -f EVENTS.jsonl`（在本目录执行）。','']
 tmp=R/f'README.md.tmp.{os.getpid()}';tmp.write_text('\n'.join(lines));tmp.replace(R/'README.md')

def refresh():
 with locked():render(json.loads((R/'STATUS.json').read_text()))

def update(node,detail,state='running',**counts):
 with locked():
  now=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat();p=R/'STATUS.json';d=json.loads(p.read_text()) if p.exists() else {'nodes':{}}
  d.update(updated_at=now,current_node=node,current_detail=detail,status=state);d['nodes'][node]={'status':state,'detail':detail,'updated_at':now,**counts}
  tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
  with (R/'EVENTS.jsonl').open('a') as f:f.write(json.dumps({'time':now,'node':node,'state':state,'detail':detail,**counts},ensure_ascii=False)+'\n')
  render(d)
  print(json.dumps({'node':node,'detail':detail,'state':state,**counts},ensure_ascii=False),flush=True)
