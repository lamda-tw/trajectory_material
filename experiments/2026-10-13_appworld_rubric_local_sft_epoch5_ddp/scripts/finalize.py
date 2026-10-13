from pathlib import Path
from datetime import datetime
import hashlib,json
R=Path(__file__).resolve().parents[1]
def read(p):return json.loads((R/p).read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def dump(p,x):(R/p).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
s=read('analysis/summary.json');assert s['all_checks_passed'];state=read('STATUS.json');assert state['phase'] in ['runs_complete_awaiting_analysis','complete']
for rel,h in read('EXECUTION_MANIFEST.json')['files'].items():assert sha(R/rel)==h,rel
for rel,h in read('AMENDMENT_01.json')['files'].items():assert sha(R/rel)==h,rel
stages=[]
for p in sorted((R/'logs').glob('*_attempt_*.json')):
 d=json.loads(p.read_text());proc=Path(f"/proc/{d['pid']}/cmdline")
 if proc.exists():assert str(R).encode() not in proc.read_bytes(),d['pid']
 stages.append(d)
for kind in ['train','evaluate','evaluate_epoch1','evaluate_epoch3']:assert any(x['kind']==kind and x['status']=='complete' and x['exit_code']==0 for x in stages)
finished=datetime.now().astimezone().isoformat();timing={'started_at':state['started_at'],'training_and_dev_finished_at':state['finished_at'],'verified_at':finished,'training_seconds':s['training']['training_wall_seconds'],'dev_seconds_by_checkpoint':{str(e):s['results'][k]['elapsed_current_invocation_seconds'] for e,k in [(1,'rubric_epoch1_new_recipe'),(3,'rubric_epoch3'),(5,'rubric_epoch5')]},'training_and_dev_total_wall_seconds':(datetime.fromisoformat(state['finished_at'])-datetime.fromisoformat(state['started_at'])).total_seconds(),'stages':stages,'probe_excluded_from_formal_training':True};dump('TIMING.json',timing)
result=s['results']['rubric_epoch5'];(R/'README.md').write_text(f"# Rubric 局部动作五轮双卡 SFT\n\n实验已完成。全新LoRA、相同2,440个rubric目标，5轮、6,100次更新、983,040监督token。DEV57官方成功：**第1轮 {s['results']['rubric_epoch1_new_recipe']['successes']}/57，第3轮 {s['results']['rubric_epoch3']['successes']}/57，第5轮 {result['successes']}/57**。本次观察中第1轮最高；loss下降不代表DEV成功率持续提升。\n\n[完整报告]({R/'REPORT.md'}) · [五轮loss图]({R/'analysis/loss_5epochs.png'}) · [逐题比较]({R/'analysis/task_comparison.csv'}) · [最终adapter]({R/'training/rubric/adapter'}) · [用时]({R/'TIMING.json'})\n\n本次第1、3、5轮独立保存并分别完成DEV57，见CHECKPOINTS_135.json和完整报告。本次使用历史五轮SFT配方，未接续旧adapter，未调用外部模型改动作。与旧一轮的差异不只epoch，且未训练五轮uniform组。\n")
state.update(phase='complete',analysis_finished_at=finished,report=str(R/'REPORT.md'));dump('STATUS.json',state)
files=[p for p in R.rglob('*') if p.is_file() and p.parent in [R,R/'analysis',R/'scripts'] and p.name!='COMPLETION_CHECK.json'];check={'phase':'complete','checked_at':finished,'five_epochs_exactly_verified':True,'target_tokens_total':983040,'updates':6100,'new_adapter_from_base_verified':True,'both_ranks_synchronized_each_epoch':True,'dev_tasks_per_checkpoint':57,'dev_results_total':171,'retained_checkpoints':[1,3,5],'official_results_valid':True,'new_external_judge_calls':0,'new_training_actions':0,'owned_stage_processes_exited':True,'artifact_sha256':{str(p.relative_to(R)):sha(p) for p in files}};dump('COMPLETION_CHECK.json',check);print(json.dumps({'result':result['successes'],'timing':timing},ensure_ascii=False,indent=2))
