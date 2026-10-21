"""Plan-specified tool-disabled judge, calibration only; formal outputs are gated."""
from experiment import *
from judging import judge,public_prefix
from public_payload import sanitize
import argparse

def run(cards_only=False,version='v1'):
 assert version in ('v1','v2')
 pilot=rows('calibration_states.csv');node='评分校准与协议冻结'
 base=R/f'judge_runs/calibration_{version}'
 def card(row):
  v=judge('card',public_prefix(data(row)),base/'cards'/key(row));return {'state_id':row['state_id'],'card':v}
 cards=parallel(pilot,card,node,detail=f'{version}校准前缀卡',max_workers=8);atomic_json(R/f'calibration/cards_{version}.json',cards)
 if cards_only:
  update(node,'9张校准前缀卡已返回，等待GPU校准动作；正式候选门禁保持关闭。','waiting_calibration_actions');return
 assert read(R/'config/gpu_calibration_accepted.json')['accepted']
 items=[(r,m) for r in pilot for m in models() if m['training_seed']==20261015]
 def action(item):
  row,m=item;d=data(row);card=read(base/'cards'/key(row)/'judgement.json');execution=read(R/'results/executions'/('calibration_'+model_key(m))/f'{key(row)}.json')
  payload=dict(public_prefix(d),diagnostic_card=card,candidate={k:execution['candidate'][k] for k in ['text','code','observation']});clean,redaction=sanitize(payload)
  alias='calibration_action_'+digest(['20261020:calibration_blind',m['alias'],row['state_id']])[:16]
  dest=base/'actions'/alias;v=judge('action',payload,dest)
  atomic_json(R/f'calibration/blind_review_{version}'/f'{alias}.json',{'blind_id':alias,'public_evidence':clean,'judgement':v})
  return {'state_id':row['state_id'],'model':model_key(m),'blind_id':alias,'judgement':str(dest/'judgement.json')}
 result=parallel(sorted(items,key=lambda x:digest(['calibration_order',x[0]['state_id'],x[1]['alias']])),action,node,detail=f'{version}校准候选动作评分',max_workers=8)
 atomic_json(R/f'calibration/action_index_{version}.json',result)
 update(node,'9张卡片和27个动作评分完成，等待逐例语义审阅与技术核验后冻结；正式候选尚未生成。','needs_review')
if __name__=='__main__':
 ap=argparse.ArgumentParser();ap.add_argument('--cards-only',action='store_true');ap.add_argument('--version',choices=['v1','v2'],default='v2');args=ap.parse_args();run(args.cards_only,args.version)
