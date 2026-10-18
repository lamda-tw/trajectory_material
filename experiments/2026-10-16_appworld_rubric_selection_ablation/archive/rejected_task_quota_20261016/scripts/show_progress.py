from pathlib import Path
import json
R=Path(__file__).resolve().parents[1]
for p in [R/'STATUS.json']:
 if p.exists(): print(p.name,json.dumps(json.loads(p.read_text()),ensure_ascii=False,indent=2))
state=json.loads((R/'STATUS.json').read_text()) if (R/'STATUS.json').exists() else {}
if all(k in state for k in ['arm','seed']):
 p=R/f"training/{state['arm']}/seed_{state['seed']}/PROGRESS.json"
 if p.exists():print(json.dumps(json.loads(p.read_text()),ensure_ascii=False,indent=2))
for p in sorted((R/'evaluation').rglob('STATUS.json')):
 d=json.loads(p.read_text())
 if d['phase']!='complete': print(str(p.relative_to(R)),json.dumps(d,ensure_ascii=False))
