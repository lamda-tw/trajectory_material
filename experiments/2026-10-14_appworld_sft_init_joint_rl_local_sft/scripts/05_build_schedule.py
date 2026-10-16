"""Generate a reviewable candidate schedule. Does not freeze batch count or train."""
from common import ROOT,read,dump,jsonl,sha,require,now
from round_data import schedule

def main():
    cfg=read(ROOT/'config/pool_training_draft.json');data=read(ROOT/'data/data_manifest.json');tasks=(ROOT/'config/train90.txt').read_text().split();rows=[]
    for r in range(1,cfg['schedule_candidate']['online_rounds']+1):
        for row in schedule(cfg,tasks,len(data['samples']),r):
            row['sample_ids']=[data['samples'][i]['sample_id'] for i in row['sft_indices']]
            row['sft_target_tokens']=sum(data['samples'][i]['target_tokens'] for i in row['sft_indices'])
            row['behavior_policy_update']=(r-1)*cfg['schedule_candidate']['batches_per_round']
            row['rl_trajectories']=len(row['tasks'])*cfg['schedule_candidate']['rollouts_per_task']
            rows.append(row)
    require(sum(x['sft_target_tokens'] for x in rows)==data['T_SFT']*5,'Token budget mismatch')
    jsonl(ROOT/'data/sft_schedule_candidate.jsonl',rows)
    dump(ROOT/'checks/schedule_candidate.json',{'at':now(),'status':'candidate validated, not frozen','updates':len(rows),
         'per_round':15,'rl_total_consumptions':sum(x['rl_trajectories'] for x in rows),'reused_initial':540,'new_formal':2160,
         'sft_consumptions':sum(len(x['sft_indices']) for x in rows),'sft_tokens':sum(x['sft_target_tokens'] for x in rows),
         'schedule_sha256':sha(ROOT/'data/sft_schedule_candidate.jsonl'),'config_sha256':sha(ROOT/'config/pool_training_draft.json')})
if __name__=='__main__':main()
