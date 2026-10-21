"""Thread/process safe experiment progress. No GPU or remote calls."""
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime
from zoneinfo import ZoneInfo
import fcntl,json,os,threading
R=Path(__file__).resolve().parents[1];LOCK=threading.Lock()
NODES=['启动授权与GPU1排队','输入与权重核验','双重重放及evaluator校准','27个校准动作与短续跑','评分校准与协议冻结','129张正式前缀卡','正式前缀重放','1161个首步生成与执行','行为评分与54条复核','540个固定策略续跑分支','统计核验与详细报告']
def now():return datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
@contextmanager
def locked():
 with LOCK:
  (R/'runtime').mkdir(exist_ok=True)
  with (R/'runtime/progress.lock').open('a+') as f:
   fcntl.flock(f,fcntl.LOCK_EX);yield

def render(d):
 lines=['# ZeroFail3 / Random / Net3同状态机制实验','',f"更新时间（北京时间）：{d['updated_at']}",'',f"**当前节点：{d['current_node']}；{d['status']}。** {d['current_detail']}",'','三策略×三个已有1710步/1轮权重；129正式状态+9独立校准状态。正式首步1161个；20状态×9首步×3固定接手策略=540续跑分支，每分支最多12个额外模型步。仅物理GPU1；GPU1被占用就等待。','', '| 节点 | 状态 | 当前说明 |','| --- | --- | --- |']
 for node in NODES:
  v=d['nodes'].get(node,{});detail=v.get('detail','尚未开始').replace('|','/').replace('\n',' ');lines.append(f"| {node} | {v.get('status','pending')} | {detail} |")
 hpath=R/'HEALTH.json'
 if hpath.exists():
  h=json.loads(hpath.read_text());lines+=['','## 实时检查','',f"最近检查：{h.get('checked_at')}；{h.get('detail','')}",f"GPU1状态：{h.get('gpu1_status','待检查')}",f"预计剩余：{h.get('eta','校准后重估；原计划7–15小时，不含等待GPU时间')}。",f"[检查状态](HEALTH.json)；[检查日志](MONITOR_EVENTS.jsonl)。"]
 lines+=['','## 查看入口','','- [当前机器可读状态](STATUS.json) / [每个节点记录](EVENTS.jsonl)。','- [总流水线日志](logs/pipeline.log) / [校准日志](logs/calibration.log)。','- [冻结计划](plan_snapshot/PLAN.md) / [状态清单](plan_snapshot/states_selected.csv) / [评价方法](plan_snapshot/ACTION_EVALUATION.md) / [续跑与预算](plan_snapshot/CONTINUATION_AND_BUDGET.md)。','- [详细报告](REPORT.md)：未完成时明确标记，完成后含三seed行为、evaluator细项、后续效果、案例及限制。','- [启动授权](config/authorization.json)覆盖计划快照中的“仅计划”状态。','', '终端持续查看：','', '```bash','cd /root/autodl-tmp/workspace-tw/experiments/2026-10-20_appworld_zerofail3_same_state_mechanism','watch -n 30 cat README.md','# 或只看新增节点','tail -f EVENTS.jsonl','```','', '原始输入、真实执行快照和模型输出含实验数据，保存在本地忽略目录；公开盲评仅允许脱敏公开前缀和候选，禁止隐藏测试、未来轨迹、模型组名/seed。','']
 incident=R/'INCIDENTS.md'
 if incident.exists():lines+=['## 异常及处理','',incident.read_text()]
 tmp=R/f'README.md.tmp.{os.getpid()}';tmp.write_text('\n'.join(lines));tmp.replace(R/'README.md')

def refresh():
 with locked():render(json.loads((R/'STATUS.json').read_text()))

def update(node,detail,state='running',**counts):
 with locked():
  p=R/'STATUS.json';d=json.loads(p.read_text()) if p.exists() else {'nodes':{}};ts=now()
  d.update(updated_at=ts,current_node=node,current_detail=detail,status=state);d['nodes'][node]={'status':state,'detail':detail,'updated_at':ts,**counts}
  tmp=R/f'STATUS.json.tmp.{os.getpid()}';tmp.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n');tmp.replace(p)
  with (R/'EVENTS.jsonl').open('a') as f:f.write(json.dumps({'time':ts,'node':node,'state':state,'detail':detail,**counts},ensure_ascii=False)+'\n')
  render(d);print(json.dumps({'node':node,'state':state,'detail':detail,**counts},ensure_ascii=False),flush=True)
if __name__=='__main__':update('启动授权与GPU1排队','GPU1正被其他teacher-history-bias任务占用；用户要求等待空闲，尚未启动本实验GPU工作。','waiting_gpu1')
