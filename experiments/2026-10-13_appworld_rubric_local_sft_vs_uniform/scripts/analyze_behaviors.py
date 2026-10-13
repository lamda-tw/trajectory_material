"""Mechanical DEV behavior diagnostics, without a new judge or semantic relabeling."""
from pathlib import Path
from collections import Counter
import json,re
R=Path(__file__).resolve().parents[1]
def main():
 result={'scope':'Mechanical counts only. Repeated code is not automatically wrong; execution success is not task success. No new rubric scoring.','arms':{}}
 for arm in ['base','rubric','uniform']:
  summary=json.loads((R/f'evaluation/{arm}/SUMMARY.json').read_text());stats=Counter();errors=Counter();ends=Counter()
  for item in summary['results']:
   d=json.loads(Path(item['source']).read_text());seen=set();stats['trajectories']+=1
   ends[d['termination']+('::success' if item['success'] else '::failure')]+=1
   for st in d['steps']:
    stats['steps']+=1;code=st['code'].strip();stats['with_code']+=bool(code)
    if st['observation'].startswith('Execution failed.'):
     stats['execution_error_steps']+=1
     types=re.findall(r'\b([A-Za-z_]\w*(?:Error|Exception)|Exception|Error)\b',st['observation'])
     errors[types[-1] if types else 'unclassified']+=1
    blocks=re.findall(r'```(?:python|py)\s*\n(.*?)```',st['text'],re.S|re.I)
    stats['multiple_nonempty_python_blocks']+=sum(bool(x.strip()) for x in blocks)>1
    if code:
     stats['exact_code_seen_previously_same_trajectory']+=code in seen;seen.add(code)
  result['arms'][arm]={'counts':dict(stats),'execution_error_fraction':stats['execution_error_steps']/stats['steps'],'error_types':dict(errors),'termination_outcome':dict(ends)}
 (R/'analysis/mechanical_dev_behaviors.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n');print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
