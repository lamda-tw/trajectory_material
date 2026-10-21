"""Calibrated formal experiment, resumable. Only starts after researcher acceptance is saved."""
from experiment import *

def main():
 with (R/'runtime/pipeline.lock').open('a+') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB);(R/'runtime/pipeline.pid').write_text(str(os.getpid())+'\n')
  from run_phase1 import verify_gate,main as phase1
  verify_gate()
  if not (R/'config/phase1_completed.json').exists():phase1()
  from analyze import first_actions,continuation_analysis
  if not (R/'analysis/PHASE1_SUMMARY.json').exists():first_actions()
  from continuations import run
  run(calibration=False)
  update('统计核验与详细报告','正式分支已完成，正在计算配对行为、逐检查得失、三seed/三来源/三接手策略结果。')
  continuation_analysis()
  from coverage_ledger import main as ledger
  ledger()
  from write_report import main as report
  report()
  atomic_json(R/'config/computed_report_ready.json',{'ready':True,'report':'REPORT.md','researcher_synthesis_pending':True})
  update('统计核验与详细报告','计算结果与真实案例已写入REPORT.md和analysis/CASES.md，等待研究助手核查并补充结果解释。','needs_review')
if __name__=='__main__':
 try:main()
 except BaseException as e:
  state=read(R/'STATUS.json');update(state.get('current_node','统计核验与详细报告'),repr(e)+'；已有有效输出保留。','error');raise
