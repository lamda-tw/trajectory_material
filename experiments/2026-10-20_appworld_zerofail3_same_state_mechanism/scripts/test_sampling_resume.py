"""Failure/restart regression: a saved valid output cannot be rerolled."""
from experiment import *
import tempfile
from sampling import bounded_sample

def main():
 with tempfile.TemporaryDirectory(prefix='same_state_sampling_test_') as directory:
  path=Path(directory)/'step.json';calls=[];metadata={'test_fixture':True};messages=[{'role':'user','content':'synthetic transport test'}]
  def valid(*args,**kw):calls.append(1);return {'text':'```python\nx=1\n```','prompt_ids':[1],'response_ids':[2],'finish_reason':'stop'}
  result=bounded_sample(C,'test',messages,100,path,metadata,expected_prompt_ids=[1],sampler=valid);assert len(calls)==1
  same=bounded_sample(C,'test',messages,100,path,metadata,expected_prompt_ids=[1],sampler=lambda *a,**k:(_ for _ in ()).throw(AssertionError('Must not resample valid output')));assert same==result
  # Simulate three interrupted transport attempts from earlier processes: no fourth call permitted.
  p=Path(directory)/'retry.json';from common import digest
  context=digest({'messages':messages,'seed':100,'metadata':metadata,'sampling':{'temperature':C['evaluation']['temperature'],'max_model_len':C['agent']['max_model_len'],'max_new_tokens':C['agent']['max_new_tokens']}})
  atomic_json(p.parent/'attempts'/p.name,{'context_sha256':context,'attempts':[{'status':'started'}]*3})
  try:bounded_sample(C,'test',messages,100,p,metadata,sampler=valid)
  except RuntimeError as e:assert 'three persisted' in str(e)
  else:raise AssertionError('Fourth transport attempt was allowed')
  assert len(calls)==1
 print({'first_valid_output_preserved':True,'restarts_cannot_reset_retry_budget':True,'real_model_calls':0})
if __name__=='__main__':main()
