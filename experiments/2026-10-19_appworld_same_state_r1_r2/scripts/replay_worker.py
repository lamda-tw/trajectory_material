"""One process/world. Replay every actual prefix action; never load DB-only snapshots as sessions."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,random,re,shutil,sys,time,types,traceback
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from common import atomic_json,digest,file_sha

def encode(x,seen=None):
 seen=set() if seen is None else seen
 if x is None or type(x) in (str,int,bool):return x
 if isinstance(x,float):return {'float':repr(x)}
 if isinstance(x,bytes):return {'bytes':x.hex()}
 if isinstance(x,(datetime.datetime,datetime.date,datetime.time)):return {'type':type(x).__module__+'.'+type(x).__name__,'iso':x.isoformat()}
 if isinstance(x,types.ModuleType):return {'module':x.__name__}
 if isinstance(x,type):return {'class':x.__module__+'.'+x.__qualname__}
 if isinstance(x,(types.BuiltinFunctionType,types.BuiltinMethodType)):return {'builtin':getattr(x,'__module__','')+'.'+x.__name__}
 if id(x) in seen:return {'reference_cycle_type':type(x).__qualname__}
 seen=seen|{id(x)}
 if isinstance(x,dict):return {'dict':[[encode(k,seen),encode(v,seen)] for k,v in x.items()]}
 if isinstance(x,(list,tuple,set,frozenset)):
  vals=[encode(v,seen) for v in x]
  if isinstance(x,(set,frozenset)):vals=sorted(vals,key=lambda v:json.dumps(v,sort_keys=True))
  return {type(x).__name__:vals}
 if isinstance(x,types.FunctionType):
  c=x.__code__
  return {'function':x.__name__,'bytecode':c.co_code.hex(),'consts':encode(c.co_consts,seen),'names':c.co_names,'defaults':encode(x.__defaults__,seen),'closure':[encode(v.cell_contents,seen) for v in x.__closure__ or []]}
 if isinstance(x,types.CodeType):return {'code':x.co_code.hex(),'consts':encode(x.co_consts,seen),'names':x.co_names}
 if isinstance(x,random.Random):return {'random':encode(x.getstate(),seen)}
 return {'UNSUPPORTED':type(x).__module__+'.'+type(x).__qualname__}

def db_state(world):
 out={}
 for app,models in world.models.items():
  conn=models.SQLModel.db.connection
  tables=conn.execute("SELECT name,sql FROM sqlite_master WHERE type='table' ORDER BY name").fetchall();out[app]={}
  for name,sql in tables:
   q='"'+name.replace('"','""')+'"'
   rows=conn.execute('SELECT * FROM '+q).fetchall()
   out[app][name]={'schema':sql,'rows':len(rows),'contents_sha256':digest(encode(rows))}
 return out

def save_exact_snapshot(world, destination):
 # SQLite backup preserves FTS shadow tables; SQL change-log replay can repack them.
 # Deduplicate immutable, byte-identical files without sharing mutable live worlds.
 world.models.save(db_home_path=str(destination),format='full',app_names=list(world.models.keys()),delete_if_exists=True,save_model_hashes=True,vaccum=False)
 blobs=R/'runtime/snapshot_blobs';blobs.mkdir(parents=True,exist_ok=True)
 for p in destination.iterdir():
  if not p.is_file():continue
  blob=blobs/(file_sha(p)+p.suffix)
  try:os.link(p,blob)
  except FileExistsError:pass
  p.unlink();os.link(blob,p)

def fingerprint(world,baseline):
 ns=world.shell.user_ns
 variables={k:encode(v) for k,v in ns.items() if not re.fullmatch(r'_i[0-9]*',k) and k not in ('_','__','___','_ii','_iii','_ih','_oh','_dh','In','Out','get_ipython','exit','quit','open') and (k not in baseline or v is not baseline[k])}
 unsupported=[k for k,v in variables.items() if '"UNSUPPORTED"' in json.dumps(v)]
 state={'num_interactions':world.num_interactions,'variables':variables,'unsupported_variables':unsupported,'db_tables':db_state(world),'completed':world.task_completed(),'clock':datetime.datetime.now().isoformat(),'random':encode(random.getstate()),'misc_files':{}}
 aliases={}
 for name,value in ns.items():
  if name in variables and isinstance(value,(dict,list,set)):
   aliases.setdefault(id(value),[]).append(name)
 state['variable_alias_groups']=sorted(sorted(names) for names in aliases.values() if len(names)>1)
 tracker=world.requester.request_tracker
 state['request_tracker']={'requests_sha256':digest(encode(tracker.requests)),'count':len(tracker.requests),'reset_on':tracker.num_requests_reset_on}
 np=sys.modules.get('numpy')
 if np is not None:
  st=np.random.get_state();state['numpy_random']=[st[0],st[1].tolist(),int(st[2]),int(st[3]),float(st[4])]
 misc=Path(world.output_misc_directory)
 if misc.exists():state['misc_files']={str(p.relative_to(misc)):file_sha(p) for p in sorted(misc.rglob('*')) if p.is_file()}
 return state

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--job',type=Path,required=True);a=ap.parse_args();job=json.loads(a.job.read_text());cfg=json.loads((R/'config/runtime.json').read_text());d=json.loads(Path(job['input']).read_text());out=Path(job['output']);runtime=Path(job['runtime']);runtime.mkdir(parents=True,exist_ok=True)
 if not (runtime/'data').exists():(runtime/'data').symlink_to(cfg['paths']['appworld_data'],target_is_directory=True)
 cache=runtime/'cache';cache.mkdir(exist_ok=True)
 if not (cache/'tests').exists():(cache/'tests').symlink_to(cfg['paths']['appworld_test_cache'],target_is_directory=True)
 os.environ['APPWORLD_ROOT']=str(runtime);os.environ['APPWORLD_CACHE']=str(cache);os.chdir(runtime)
 from appworld import AppWorld,update_root
 update_root(str(runtime));started=time.monotonic();result={'state_id':d['state']['state_id'],'job':job,'observations':[]}
 with AppWorld(task_id=d['state']['task_id'],experiment_name='branch',max_interactions=50,load_ground_truth=True,ground_truth_mode='minimal',random_seed=100,raise_on_failure=True) as world:
  baseline=dict(world.shell.user_ns)
  for s in d['history']:
   obs=world.execute(s['code']) if s['code'] else ''
   result['observations'].append({'step':s['step'],'original_sha256':digest(s['observation']),'replay_sha256':digest(obs),'exact_match':obs==s['observation'],'replayed':obs})
  before=fingerprint(world,baseline);result['before']=before;result['before_sha256']=digest(before)
  result['all_observations_exact']=all(x['exact_match'] for x in result['observations'])
  result['environment_supported']=not before['unsupported_variables']
  world.save_state();save_exact_snapshot(world,runtime/'snapshots/before')
  result['snapshot_format']='sqlite_full_backup_v1'
  if job.get('candidate'):
   candidate=json.loads(Path(job['candidate']).read_text());code=candidate['code'];request_start=len(world.requester.request_tracker.requests);obs=world.execute(code) if code else ''
   result['candidate']={'text':candidate['text'],'code':code,'observation':obs,'execution_error':obs.startswith('Execution failed.'),'no_code':not bool(code),'actual_requests':encode(world.requester.request_tracker.requests[request_start:]),'actual_request_methods_urls':[{'method':x['method'],'url':x['url']} for x in world.requester.request_tracker.requests[request_start:]],'code_repeated':bool(code.strip()) and code.strip() in [x['code'].strip() for x in d['history']]}
   result['after']=fingerprint(world,baseline);world.save_state();save_exact_snapshot(world,runtime/'snapshots/after')
 result['elapsed_seconds']=time.monotonic()-started
 atomic_json(out,result)
 print(json.dumps({'state':result['state_id'],'observations_exact':result['all_observations_exact'],'environment_supported':result['environment_supported'],'seconds':result['elapsed_seconds']}),flush=True)
if __name__=='__main__':
 try:main()
 except BaseException:
  traceback.print_exc();raise
