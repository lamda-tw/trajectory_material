"""Wait for the owned inference run, then perform read-only probability diagnostics."""
from pathlib import Path
import json,subprocess,time,sys
D=Path(__file__).resolve().parents[1];deadline=time.monotonic()+3600
while time.monotonic()<deadline:
 status=json.loads((D/'STATUS.json').read_text())
 if status['stage']=='generation_and_execution_complete':break
 time.sleep(10)
else:raise TimeoutError('Generation did not complete; not starting probability work')
time.sleep(2)
with (D/'distribution.log').open('a') as log:
 subprocess.run([sys.executable,'-u',str(D/'scripts/distribution.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
with (D/'analysis/current_summary.txt').open('w') as log:
 subprocess.run([sys.executable,str(D/'scripts/analyze_results.py')],stdout=log,stderr=subprocess.STDOUT,check=True)
print('Generation, execution, and read-only probability diagnostics completed; report review remains.',flush=True)
