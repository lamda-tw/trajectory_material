"""Immutable round pools and deterministic one-pass schedules. CPU only."""
from pathlib import Path
import argparse, collections, json, math, random
from common import ROOT, WORKSPACE, read, dump, sha, require, now

def validate_trajectory(d):
    require(d['steps'], 'No generated actions; investigate instead of deleting episode')
    require(type(d['official_evaluation']['success']) is bool and d['official_evaluation']['num_tests']>0,'Missing official reward')
    for s in d['steps']:
        prompt,target,old=s['prompt_ids'],s['response_ids'],s['old_logprobs']
        require(prompt and target and len(target)==len(old),'Misaligned action probabilities')
        require(all(type(x) is int and x>=0 for x in prompt+target),'Invalid token IDs')
        require(all(isinstance(x,(int,float)) and math.isfinite(x) and x<=1e-5 for x in old),'Invalid behavior probabilities')

def build_pool(paths, output, round_id, adapter_sha, expected_tasks, group_size=6, protocol_sha=None):
    entries=[];groups=collections.defaultdict(list);policies=set();slots=set()
    for path in sorted(map(Path,paths)):
        d=read(path);validate_trajectory(d);j=d['job'];slot=(j['task_id'],j['sample'])
        require(slot not in slots,'Duplicate task/sample slot');slots.add(slot);policies.add(j['policy_id'])
        groups[j['task_id']].append(j['sample'])
        entries.append({'trajectory':str(path.resolve()),'sha256':sha(path),'task_id':j['task_id'],'sample':j['sample'],
                        'reward':int(d['official_evaluation']['success']), 'tokens':sum(len(s['response_ids']) for s in d['steps'])})
    require(set(groups)==set(expected_tasks),'Round task coverage mismatch')
    require(all(sorted(v)==list(range(group_size)) for v in groups.values()),'Incomplete GRPO group')
    require(len(policies)==1,'Mixed behavior policies within a round')
    pool={'created_at':now(),'round':round_id,'behavior_adapter_sha256':adapter_sha,'behavior_policy_id':next(iter(policies)),
          'protocol_sha256':protocol_sha,'group_size':group_size,'tasks':list(expected_tasks),'episodes':entries,
          'count':len(entries),'immutable_old_logprobs':True,'passes':1}
    output=Path(output)
    if output.exists():
        existing=read(output); pool['created_at']=existing['created_at'];require(existing==pool,'Refusing to overwrite a different committed pool')
    else: dump(output,pool)
    return pool

def load_pool(path):
    pool=read(path);grouped=collections.defaultdict(list)
    for row in pool['episodes']:
        require(sha(row['trajectory'])==row['sha256'],'Trajectory changed')
        d=read(row['trajectory']);validate_trajectory(d)
        require(d['job']['policy_id']==pool['behavior_policy_id'],'Mixed behavior policy')
        require(d['job']['task_id']==row['task_id'] and d['job']['sample']==row['sample'],'Episode identity mismatch')
        require(int(d['official_evaluation']['success'])==row['reward'],'Reward changed')
        require(sum(len(s['response_ids']) for s in d['steps'])==row['tokens'],'Token count changed')
        grouped[row['task_id']].append({**row,'steps':d['steps']})
    require(len(pool['episodes'])==pool['count'] and set(grouped)==set(pool['tasks']),'Pool coverage mismatch')
    for group in grouped.values():require(sorted(x['sample'] for x in group)==list(range(pool['group_size'])),'Group slots mismatch')
    return pool,grouped

def schedule(cfg, task_ids, sample_count, round_id):
    c=cfg['schedule_candidate'];b=c['tasks_per_batch'];require(len(task_ids)%b==0,'Task batch must divide round pool')
    rng=random.Random(c['seed']+round_id*1009);tasks=list(task_ids);rng.shuffle(tasks)
    samples=list(range(sample_count));random.Random(c['seed']+round_id*1013).shuffle(samples)
    n=len(tasks)//b; q,r=divmod(sample_count,n);sizes=[q+(i<r) for i in range(n)]
    shift=(round_id-1)%n;sizes=sizes[shift:]+sizes[:shift];rows=[];cursor=0
    for j,size in enumerate(sizes):
        rows.append({'round':round_id,'batch':j+1,'global_update':(round_id-1)*n+j+1,
                     'tasks':tasks[j*b:(j+1)*b],'sft_indices':samples[cursor:cursor+size]});cursor+=size
    require(sorted(i for row in rows for i in row['sft_indices'])==list(range(sample_count)),'SFT coverage changed')
    return rows

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--import-initial',action='store_true');args=ap.parse_args()
    require(args.import_initial,'Choose --import-initial')
    source=WORKSPACE/'experiments/2026-10-08_static_rubric_grpo_lora_init/runs/step01_train90_rollouts'
    original=read(source/'collection_manifest.json'); cfg=read(ROOT/'config/pool_training_draft.json')
    require(original['initial_adapter']['files']['adapter_model.safetensors']==cfg['model']['adapter_weights_sha256'],'Wrong initial policy')
    tasks=(ROOT/'config/train90.txt').read_text().split()
    pool=build_pool((source/'trajectories').glob('*.json'),ROOT/'rollout/round_01/pool.json',1,
                    cfg['model']['adapter_weights_sha256'],tasks,protocol_sha=sha(source/'collection_manifest.json'))
    print(json.dumps({'round':1,'episodes':pool['count'],'source':'existing 540; no new sampling'}))
if __name__=='__main__':main()
