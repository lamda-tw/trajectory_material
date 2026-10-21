"""GPU-free replay/evaluator calibration. No judge calls."""
from experiment import *

def main():
 assert read(R/'config/input_audit.json')['all_prompt_tokens_exact']
 pilot=rows('calibration_states.csv');node='双重重放及evaluator校准'
 def one(item):
  row,rep=item;x=replay(row,'calibration_reference_'+rep)
  if x['all_observations_exact'] and x['environment_supported']:evaluate(row,'calibration_reference_'+rep,'before')
  return x
 parallel([(r,rep) for r in pilot for rep in ['a','b']],one,node,detail='双重前缀重放及隔离before-evaluator')
 audit=[]
 for row in pilot:
  a=read(R/'results/executions/calibration_reference_a'/f'{key(row)}.json');b=read(R/'results/executions/calibration_reference_b'/f'{key(row)}.json')
  audit.append({'state_id':row['state_id'],'both_observations_exact':a['all_observations_exact'] and b['all_observations_exact'],'fingerprints_equal':a['before_sha256']==b['before_sha256'],'unsupported_a':a['before']['unsupported_variables'],'unsupported_b':b['before']['unsupported_variables'],'seconds':[a['elapsed_seconds'],b['elapsed_seconds']]})
 atomic_json(R/'calibration/replay_audit.json',audit)
 assert all(x['both_observations_exact'] and x['fingerprints_equal'] and not x['unsupported_a'] and not x['unsupported_b'] for x in audit),'Calibration prefix replay mismatch; no formal generation permitted'
 fixture=min(pilot,key=lambda r:(int(r['before_step']),r['prefix_sha256']));probes=[]
 for kind in ['read_only','write','partial_write_error']:
  tag='calibration_transport_'+kind;x=replay(fixture,tag,transport_probe=kind)
  assert x['all_observations_exact'] and x['environment_supported']
  changed=x['before']['db_tables']!=x['after']['db_tables'];error=x['transport_probe']['observation'].startswith('Execution failed.')
  assert changed==(kind!='read_only') and error==(kind=='partial_write_error'),(kind,changed,error)
  before=evaluate(fixture,tag,'before');after=evaluate(fixture,tag,'after')
  assert before['checks'].keys()==after['checks'].keys() and before['loaded_db_matches_live_branch'] and after['loaded_db_matches_live_branch']
  probes.append({'kind':kind,'state_id':fixture['state_id'],'db_changed':changed,'execution_error':error,'before_passes':before['num_passes'],'after_passes':after['num_passes'],'evaluator_loaded_actual_branch':True,'source_unmodified':before['source_unmodified'] and after['source_unmodified'],'technical_only_not_policy_behavior':True})
 atomic_json(R/'calibration/evaluator_transport_audit.json',probes)
 atomic_json(R/'config/cpu_calibration_accepted.json',{'accepted':True,'replay_states':9,'independent_replays':18,'transport_probes':3,'probe_note':'Controlled local table mutation via injected helper, not a model action; validates SQLite snapshot and exception-side-effect transport, not policy quality.'})
 update(node,'9状态18次重放完全一致；3种快照/异常副作用技术探针通过；GPU未使用。','complete')
if __name__=='__main__':main()
