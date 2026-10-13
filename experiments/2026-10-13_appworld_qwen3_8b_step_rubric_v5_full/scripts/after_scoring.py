from pathlib import Path
import json,subprocess,sys,time
root=Path(__file__).resolve().parents[1]
while True:
    status=json.loads((root/'STATUS.json').read_text())
    if status.get('phase')=='scoring_complete':
        subprocess.run([sys.executable,str(root/'scripts/analyze_full.py')],cwd=root,check=True)
        break
    if status.get('phase')=='scoring_needs_recovery':
        print('Scoring requires recovery; analysis not started.',flush=True)
        break
    time.sleep(20)
