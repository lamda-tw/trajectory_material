from pathlib import Path
import json,sys
from concurrent.futures import ThreadPoolExecutor,as_completed
from judging import judge,public_prefix
from progress import update
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json
ids=json.loads((R/'plan_snapshot/same_state_audit.json').read_text())['pilot_state_ids']
def one(s):
 key=s.replace(':','__');d=json.loads((R/'inputs'/f'{key}.json').read_text());p=public_prefix(d)
 card=judge('card',p,R/'judge_runs/calibration_cards_v2'/key)
 candidate=json.loads((R/'calibration/raw/original_actions'/f'{key}.json').read_text())
 action=judge('action',dict(p,diagnostic_card=card,candidate=candidate),R/'judge_runs/calibration_actions_v2'/key)
 return {'state_id':s,'card':card,'action':action}
rows=[];update('评分校准与协议冻结','外部目的地已获用户明确授权；启动8状态卡片和动作评分校准。')
with ThreadPoolExecutor(max_workers=8) as pool:
 for f in as_completed([pool.submit(one,s) for s in ids]):
  rows.append(f.result());atomic_json(R/'calibration/judge_calibration_results_v2.json',rows);update('评分校准与协议冻结',f'{len(rows)}/8校准卡片与原动作评分完成，待逐例核查后冻结。',completed=len(rows),total=8)
update('评分校准与协议冻结','8/8格式与引用核验完成；等待证据语义复核，尚未冻结正式协议。','needs_review')
