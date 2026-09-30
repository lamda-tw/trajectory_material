"""Logging-only Ellipsis serialization fix and exact response replay after logger abort.
No changes to agent actions, environment outputs, evaluator, or generation budgets.
"""
import copy,json,os,runpy,sys
from pathlib import Path
from appworld.requester import RequestTracker
from fastapi.encoders import jsonable_encoder
from appworld.common.io import write_jsonl
from appworld_agents.code.simplified.language_model import LanguageModel
ROOT=Path(os.environ['APPWORLD_ROOT'])
EVENTS=ROOT/'logging_recovery_events.jsonl'
def event(x):
    with EVENTS.open('a') as f:f.write(json.dumps(x,ensure_ascii=False)+'\n')
original_save=RequestTracker.save
def save_with_ellipsis(self,file_path):
    try:return original_save(self,file_path)
    except ValueError:
        encoded=[jsonable_encoder(request,custom_encoder={type(Ellipsis):lambda _: {'__python_type__':'Ellipsis'}}) for request in self.requests]
        write_jsonl(encoded,file_path,silent=True)
        event({'event':'log_only_ellipsis_encoding','path':file_path,'requests':len(self.requests)})
RequestTracker.save=save_with_ellipsis
replay_path=os.environ.get('CFST_REPLAY_LOG')
records=[json.loads(s) for s in Path(replay_path).read_text().splitlines()] if replay_path else []
replay_task=os.environ.get('CFST_REPLAY_TASK')
position=0
original_init=LanguageModel.__init__
def init_with_exact_replay(self,*a,**kw):
    original_init(self,*a,**kw)
    real_call=self.lm_call
    def call(**args):
        global position
        if records and self.log_file_path and Path(self.log_file_path).parent.parent.name==replay_task and position<len(records):
            rec=records[position]
            clean=lambda x:{k:v for k,v in x.items() if k not in ['base_url','api_key']}
            assert clean(args)==clean(rec['input']),f'Exact prefix input mismatch before action {position+1}'
            position+=1
            event({'event':'exact_student_response_replay','task_id':replay_task,'action_number':position,'input_verified':True,'source':replay_path,'teacher_used':False})
            response=copy.deepcopy(rec['output']);response.pop('timestamps',None)
            return response
        return real_call(**args)
    self.lm_call=call
LanguageModel.__init__=init_with_exact_replay
entry=sys.argv.pop(1)
runpy.run_path(entry,run_name='__main__')
assert position==len(records),'Unconsumed recovery prefix'
