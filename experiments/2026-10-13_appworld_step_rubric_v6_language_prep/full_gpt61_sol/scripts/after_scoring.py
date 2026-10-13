"""Wait for frozen full scoring, then run local analysis. No scoring calls."""
from pathlib import Path
import json,subprocess,sys,time,datetime,traceback
R=Path(__file__).resolve().parents[1]
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
while True:
 status=json.loads((R/'STATUS.json').read_text())
 if status.get('phase')=='scoring_complete':break
 if status.get('phase')=='scoring_needs_recovery':
  print('Scoring requires recovery; analysis deferred.',flush=True);raise SystemExit(1)
 time.sleep(20)
try:
 for script in ['analyze_full','analyze_terminal_status','report_metrics','render_report_assets','analyze_rubric_validity','compare_configurations']:
  with (R/'logs'/f'{script}.log').open('w') as out:subprocess.run([sys.executable,str(R/'scripts'/f'{script}.py')],stdout=out,stderr=subprocess.STDOUT,check=True)
  print(script,'completed',flush=True)
 timer=json.loads((R/'EVALUATION_TIMING.json').read_text());timer.update(phase='awaiting_semantic_review',automatic_analysis_finished_at=datetime.datetime.now(datetime.timezone.utc).isoformat());write(R/'EVALUATION_TIMING.json',timer)
 write(R/'ANALYSIS_STATUS.json',{'phase':'automatic_analysis_complete','semantic_review':'pending','report':'pending'})
except Exception:
 write(R/'ANALYSIS_STATUS.json',{'phase':'analysis_failed','error':traceback.format_exc()});raise
