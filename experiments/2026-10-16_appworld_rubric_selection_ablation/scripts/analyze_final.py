from pathlib import Path
import json,statistics as st,collections as co,re,hashlib
R=Path(__file__).resolve().parents[1];O=R/'analysis';cfg=json.loads((R/'config/training.json').read_text());arms=cfg['arms'];seeds=cfg['seeds']
def read(p):return json.loads(Path(p).read_text())
def dump(n,x):(O/n).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
source_cache={};selection={};behaviors={};paired=[];task_rows=[]
def features(steps):
 codes=[x['code'].strip() for x in steps];cnt=co.Counter(c for c in codes if c);n=len(steps)
 return {'steps':n,'generated_tokens':sum(len(x['response_ids']) for x in steps),'doc_steps':sum('apis.api_docs.' in c for c in codes),'completion_steps':sum('apis.supervisor.complete_task(' in c for c in codes),'execution_error_steps':sum(x['observation'].startswith('Execution failed.') for x in steps),'repeated_code_steps':sum(v-1 for v in cnt.values()),'no_code_steps':sum(not c for c in codes)}
for arm in arms:
 selection[arm]=[];behaviors[arm]=[]
 for seed in seeds:
  rows=[json.loads(s) for s in (R/f'data/{arm}/seed_{seed}/selection.jsonl').read_text().splitlines()];steps=[];positions=[]
  for r in rows:
   path=r['source']
   if path not in source_cache:source_cache[path]=read(path)
   traj=source_cache[path];step=traj['steps'][r['step']-1];assert step['step']==r['step'];steps.append(step);positions.append(r['step']/len(traj['steps']))
  labels=co.Counter(r['labels'] for r in rows);f=features(steps);f.pop('repeated_code_steps')
  codecounts=co.Counter(s['code'].strip() for s in steps if s['code'].strip())
  selection[arm].append({'seed':seed,'samples':len(rows),'tasks':len({r['task_id'] for r in rows}),'trajectories':len({r['trajectory_id'] for r in rows}),'P_mean':st.mean(r['P'] for r in rows),'with_F':sum(r['F']>0 for r in rows),'with_U':sum(r['U']>0 for r in rows),'prompt_tokens_mean':st.mean(r['prompt_tokens'] for r in rows),'target_tokens_mean':st.mean(r['response_tokens'] for r in rows),'relative_position_mean':st.mean(positions),'source_success_steps':sum(source_cache[r['source']]['official_evaluation']['success'] for r in rows),'top_patterns':labels.most_common(6),'R_P':{f'R{i}':sum(r['labels'][i-1]=='P' for r in rows) for i in range(1,9)},'R_F':{f'R{i}':sum(r['labels'][i-1]=='F' for r in rows) for i in range(1,9)},'duplicate_code_across_samples':sum(v-1 for v in codecounts.values()),**f})
  folder=R/f'evaluation/{arm}/seed_{seed}/epoch_01';summary=read(folder/'SUMMARY.json');assert summary['tasks']==57 and len(summary['results'])==57
  epoch=read(R/f'training/{arm}/seed_{seed}/epoch_01.json');assert epoch['updates']==855 and epoch['samples']==1710
  totals=co.Counter();term=co.Counter();successes=[]
  for row in summary['results']:
   path=folder/'trajectories'/f"{row['task_id']}.json";assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'];d=read(path);f=features(d['steps']);totals.update(f);term[d['termination']]+=1
   success=d['official_evaluation']['success']
   if success:successes.append(row['task_id'])
   task_rows.append({'arm':arm,'seed':seed,'task_id':row['task_id'],'success':success,'termination':d['termination'],'file':str(path),**f})
  behaviors[arm].append({'seed':seed,'successes':len(successes),'successful_tasks':successes,'successful_families':len({t.rsplit('_',1)[0] for t in successes}),'termination':dict(term),'completion_failed':sum(t['arm']==arm and t['seed']==seed and t['termination']=='completion_api' and not t['success'] for t in task_rows),'mean_training_loss':epoch['mean_step_loss'],**dict(totals)})
base=read(R/'evaluation/base/SUMMARY.json');bt=co.Counter();bf=co.Counter()
for r in base['results']:
 d=read(r['source']);bt[d['termination']]+=1;bf.update(features(d['steps']))
dump('final_selection.json',selection);dump('final_behavior.json',behaviors);dump('final_task_metrics.json',task_rows);dump('final_base_behavior.json',{'successes':base['successes'],'termination':dict(bt),**dict(bf)})
for seed in seeds:
 a={t['task_id']:t for t in task_rows if t['arm']=='zerofail3' and t['seed']==seed};b={t['task_id']:t for t in task_rows if t['arm']=='random' and t['seed']==seed}
 paired.append({'seed':seed,'gains':[t for t in a if a[t]['success'] and not b[t]['success']],'losses':[t for t in a if b[t]['success'] and not a[t]['success']]})
dump('zerofail_random_pairs.json',paired)
for arm in arms:
 s=selection[arm];b=behaviors[arm]
 print(arm,'success',[x['successes'] for x in b], 'selection', {k:round(st.mean(x[k] for x in s),2) for k in ['with_F','prompt_tokens_mean','target_tokens_mean','doc_steps','execution_error_steps','completion_steps','relative_position_mean']},'RP',{k:round(st.mean(x['R_P'][k] for x in s),1) for k in ['R4','R5','R6','R7']})
 print('behavior', {k:round(st.mean(x[k] for x in b),2) for k in ['steps','generated_tokens','doc_steps','execution_error_steps','repeated_code_steps','completion_failed','successful_families','mean_training_loss']},'termination',{k:round(st.mean(x['termination'].get(k,0) for x in b),2) for k in set().union(*(x['termination'] for x in b))})
print('base',{'successes':base['successes'],'termination':dict(bt),**dict(bf)})
print('pairs',paired)
