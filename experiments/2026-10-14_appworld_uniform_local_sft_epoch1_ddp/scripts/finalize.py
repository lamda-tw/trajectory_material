from pathlib import Path
from datetime import datetime
import hashlib,json
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def dump(p,x):(R/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
s=read('analysis/summary.json');state=read('STATUS.json');assert s['all_checks_passed'] and state['phase'] in ['runs_complete_awaiting_analysis','complete']
for rel,h in read('EXECUTION_MANIFEST.json')['files'].items():assert sha(R/rel)==h
stages=[]
for p in sorted((R/'logs').glob('*_attempt_*.json')):
 d=json.loads(p.read_text());proc=Path(f"/proc/{d['pid']}/cmdline")
 if proc.exists():assert str(R).encode() not in proc.read_bytes()
 stages.append(d)
for kind in ['train','evaluate']:assert any(d['kind']==kind and d['status']=='complete' and d['exit_code']==0 for d in stages)
now=datetime.now().astimezone().isoformat();dump('TIMING.json',{'started_at':state['started_at'],'training_and_dev_finished_at':state['finished_at'],'analysis_verified_at':now,'training_seconds':s['training']['training_wall_seconds'],'evaluation_seconds':s['results']['random_epoch1']['elapsed_current_invocation_seconds'],'total_training_and_dev_wall_seconds':(datetime.fromisoformat(state['finished_at'])-datetime.fromisoformat(state['started_at'])).total_seconds(),'stages':stages,'preparation_probe_and_analysis_excluded_from_training':True})
x=s['results']['random_epoch1'];(R/'README.md').write_text(f"# Random步骤一轮双卡SFT\n\n已完成：Random **{x['successes']}/57（{100*x['TGC']:.2f}%）**，Rubric参考组 **13/57（22.81%）**。两组匹配2,440步、1,220次更新和每次更新的任务配对，从相同LoRA初始化开始。监督token与部分响应mask不完全相同。\n\n[报告]({R/'REPORT.md'}) · [模型]({R/'training/uniform/epoch_01_adapter'}) · [loss图]({R/'analysis/loss_epoch1.png'}) · [逐题比较]({R/'analysis/task_comparison.csv'}) · [用时]({R/'TIMING.json'})\n")
state.update(phase='complete',analysis_finished_at=now,report=str(R/'REPORT.md'));dump('STATUS.json',state)
files=[p for p in R.rglob('*') if p.is_file() and p.parent in [R,R/'analysis',R/'scripts'] and p.name!='COMPLETION_CHECK.json'];dump('COMPLETION_CHECK.json',{'phase':'complete','checked_at':now,'steps':2440,'updates':1220,'epochs':1,'dev_tasks':57,'initialization_matches_rubric':True,'step_counts_and_task_pairs_match':True,'owned_stage_processes_exited':True,'artifact_sha256':{str(p.relative_to(R)):sha(p) for p in files}});print(json.dumps({'random_successes':x['successes'],'rubric_successes':13},ensure_ascii=False))
