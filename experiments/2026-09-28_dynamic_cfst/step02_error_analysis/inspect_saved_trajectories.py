#!/usr/bin/env python3
"""Read existing evidence only; never execute saved model code."""
import json,re,sys
from pathlib import Path
STAGE=Path(__file__).resolve().parent
ROOT=STAGE.parent/'step01_train90_student_rollouts/experiments/outputs/simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/train'

def load_task(task):
    path=ROOT/'tasks'/task/'logs/environment_io.md'
    text=path.read_text()
    matches=list(re.finditer(r'^### Environment Interaction (\d+)\s*$',text,re.M))
    calls=[json.loads(x) for x in (path.parent/'lm_calls.jsonl').read_text().splitlines()]
    steps=[]
    for i,match in enumerate(matches):
        end=matches[i+1].start() if i+1<len(matches) else len(text)
        segment=text[match.end():end]
        parsed=re.search(r'```python\n(.*?)\n```\s*\n\s*```\n(.*?)\n```',segment,re.S)
        assert parsed,(task,i)
        steps.append({'step':int(match.group(1)),'line':text[:match.start()].count('\n')+1,'code':parsed.group(1),'observation':parsed.group(2)})
    return path,calls,steps

def main():
    official=json.loads((ROOT/'evaluations/train.json').read_text())['individual']
    for task in sys.argv[1:]:
        path,calls,steps=load_task(task)
        msg=calls[0]['input']['messages'][-1]['content']
        print('\nTASK',task,'GOAL',msg.split('Task:',1)[-1].strip())
        print('OFFICIAL_FAILURES',[v['requirement'] for v in official[task]['failures']])
        seen={}
        for s in steps:
            code=s['code'];obs=s['observation']
            key=(code,obs)
            if key in seen:
                print(f"STEP {s['step']} line {s['line']}: identical code and observation to step {seen[key]}")
                continue
            seen[key]=s['step']
            print(f"STEP {s['step']} line {s['line']} CODE:\n{code}")
            if 'apis.api_docs.' in code and not any(x in code for x in ['apis.spotify.','apis.phone.','apis.venmo.','apis.simple_note.','apis.file_system.']):
                print('OBS: API documentation; length',len(obs))
            elif len(obs)>1100:
                print('OBS:',obs[:750]+'\n...[middle omitted for inspection]...\n'+obs[-300:])
            else:print('OBS:',obs)
        print('CALLS',len(calls),'ACTIONS',len(steps))
if __name__=='__main__':main()
