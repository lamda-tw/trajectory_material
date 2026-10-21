"""Replay cached calibration first responses with passive capture; never resample."""
from experiment import *
def main():
 items=[(r,m) for r in rows('calibration_states.csv') for m in models() if m['training_seed']==20261015]
 def one(item):
  row,m=item;name=model_key(m);gen=R/'results/generations'/('calibration_'+name)/f'{key(row)}.json'
  original=read(R/'results/executions'/('calibration_'+name)/f'{key(row)}.json')
  current=replay(row,'capture_equivalence_'+name,gen)
  assert original['candidate']['observation']==current['candidate']['observation'],'Passive capture changed observation'
  assert original['before']==current['before'] and original['after']==current['after'],'Passive capture changed state'
  assert original['candidate']['actual_requests']==current['candidate']['actual_requests'],'Passive capture changed requests'
  return {'state_id':row['state_id'],'model':name,'observations_and_states_equal':True,'captured_api_calls':len(current['candidate']['local_api_responses'])}
 result=list(ThreadPoolExecutor(max_workers=4).map(one,items))
 atomic_json(R/'calibration/api_capture_equivalence.json',{'accepted':True,'comparisons':result,'no_new_generations':True})
 print(json.dumps({'passed':len(result),'no_new_generations':True}))
if __name__=='__main__':main()
