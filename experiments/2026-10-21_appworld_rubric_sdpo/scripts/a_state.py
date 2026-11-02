"""One process/world. Replay every actual prefix action; never load DB-only snapshots as sessions."""
from pathlib import Path
import argparse,datetime,hashlib,json,os,random,re,shutil,sys,time,types,traceback
R=Path(__file__).resolve().parents[1];sys.path.insert(0,str(R/'runtime_code'))
from a_common import atomic_json,digest,file_sha
from api_capture import attach_capture

def encode(x,seen=None):
 seen=set() if seen is None else seen
 if x is None or type(x) in (str,int,bool):return x
 if isinstance(x,float):return {'float':repr(x)}
 if isinstance(x,bytes):return {'bytes':x.hex()}
 if isinstance(x,(datetime.datetime,datetime.date,datetime.time)):return {'type':type(x).__module__+'.'+type(x).__name__,'iso':x.isoformat()}
 if isinstance(x,datetime.timedelta):return {'timedelta':[x.days,x.seconds,x.microseconds]}
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
