"""Persist the first valid output; at most three transport attempts across process restarts."""
from pathlib import Path
import json,time
from common import atomic_json,digest,parse_code
from policy_server import sample_step

def bounded_sample(config,served,messages,seed,destination,metadata,expected_prompt_ids=None,sampler=sample_step):
 destination=Path(destination);context=digest({'messages':messages,'seed':seed,'metadata':metadata,'sampling':{'temperature':config['evaluation']['temperature'],'max_model_len':config['agent']['max_model_len'],'max_new_tokens':config['agent']['max_new_tokens']}})
 attempt_path=destination.parent/'attempts'/destination.name
 if destination.exists():
  sample=json.loads(destination.read_text());assert sample['sampling_context_sha256']==context,'Cached generation context changed'
  if expected_prompt_ids is not None:assert sample['prompt_ids']==expected_prompt_ids,'Cached generation tokens changed'
  return sample
 state=json.loads(attempt_path.read_text()) if attempt_path.exists() else {'context_sha256':context,'attempts':[]}
 assert state['context_sha256']==context,'Generation retry context changed'
 if state.get('terminal')=='context_limit':return None
 if state.get('terminal')=='integrity_error':raise RuntimeError('Prior generation integrity error: '+str(attempt_path))
 for n in range(len(state['attempts'])+1,4):
  record={'attempt':n,'started_unix':time.time(),'status':'started'};state['attempts'].append(record);atomic_json(attempt_path,state)
  try:
   sample=sampler(config,served,messages,seed,evaluation=True)
   if sample is None:
    state['terminal']='context_limit';record.update(status='context_limit',seconds=time.time()-record['started_unix']);atomic_json(attempt_path,state);return None
   if expected_prompt_ids is not None:assert sample['prompt_ids']==expected_prompt_ids,'Model input token mismatch'
   code,fixed=parse_code(sample['text']);sample.update(metadata,code=code,history_assistant_text=fixed,sampling_context_sha256=context,physical_gpu=1)
   atomic_json(destination,sample);record.update(status='valid',seconds=time.time()-record['started_unix']);state['terminal']='valid';atomic_json(attempt_path,state);return sample
  except (OSError,TimeoutError) as e:
   record.update(status='transport_error',error=repr(e),seconds=time.time()-record['started_unix']);atomic_json(attempt_path,state)
   if n<3:time.sleep(5*n)
  except BaseException as e:
   record.update(status='integrity_error',error=repr(e),seconds=time.time()-record['started_unix']);state['terminal']='integrity_error';atomic_json(attempt_path,state);raise
 raise RuntimeError('Generation exhausted three persisted transport attempts: '+str(attempt_path))
