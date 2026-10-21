"""Wait for GPU1, produce only the prespecified calibration candidates, then technical branches."""
from experiment import *
from policy_server import owned_server,sample_step
from common import parse_code

def main():
 assert read(R/'config/cpu_calibration_accepted.json')['accepted'];pilot=rows('calibration_states.csv');node='27个校准动作与短续跑';done=0
 for m in [x for x in models() if x['training_seed']==20261015]:
  tag='calibration_'+model_key(m);folder=R/'results/generations'/tag;folder.mkdir(parents=True,exist_ok=True);pending=[r for r in pilot if not (folder/f'{key(r)}.json').exists()]
  if pending:
   with gpu_lock(node):
    adapter=W/m['adapter'];assert file_sha(adapter)==m['adapter_sha256']
    with owned_server(C,R/'logs/servers'/tag,adapter.parent) as served:
     def generate(row):
      d=data(row);sample=sample_step(C,served,d['messages'],100+int(row['before_step'])-1,evaluation=True);assert sample and sample['prompt_ids']==d['prompt_ids'],'Calibration input token mismatch'
      code,fixed=parse_code(sample['text']);atomic_json(folder/f'{key(row)}.json',dict(sample,code=code,history_assistant_text=fixed,state_id=row['state_id'],policy_sha256=m['adapter_sha256'],checkpoint_alias=m['alias'],physical_gpu=1))
     parallel(pending,generate,node,detail='当前校准权重生成',max_workers=3)
  def execute(row):
   g=folder/f'{key(row)}.json';assert read(g)['policy_sha256']==m['adapter_sha256'] and read(g)['prompt_ids']==data(row)['prompt_ids'];x=replay(row,tag,g);ref=read(R/'results/executions/calibration_reference_a'/f'{key(row)}.json')
   assert x['all_observations_exact'] and x['environment_supported'] and x['before_sha256']==ref['before_sha256'],'Calibration branch prefix mismatch'
   ev=evaluate(row,tag,'after');return {'state_id':row['state_id'],'model':model_key(m),'prefix_equal':True,'passes':ev['num_passes'],'tests':ev['num_tests'],'execution_error':x['candidate']['execution_error'],'no_code':x['candidate']['no_code']}
  result=parallel(pilot,execute,node,detail='校准动作真实执行与evaluator');atomic_json(R/'calibration'/f'candidate_audit_{model_key(m)}.json',result);done+=len(result);update(node,f'{done}/27个校准动作生成、执行及evaluator完成。',completed=done,total=27)
 from continuations import run
 run(calibration=True)
 atomic_json(R/'config/gpu_calibration_accepted.json',{'accepted':True,'calibration_first_actions':27,'technical_continuation_branches':9,'technical_followup_generation_budget':27,'physical_gpu':1})
 update(node,'27个首步与9个短续跑技术分支完成，未生成正式状态动作。','complete')
if __name__=='__main__':
 try:main()
 except BaseException as e:
  update('27个校准动作与短续跑',repr(e),'error');raise
