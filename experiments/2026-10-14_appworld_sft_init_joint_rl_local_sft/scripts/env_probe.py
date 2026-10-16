"""Import-only environment probe. No model loading or CUDA initialization."""
import importlib,importlib.metadata,json,os,platform,sys
modules=sys.argv[1:]; result={'python':sys.executable,'version':platform.python_version(),'CUDA_VISIBLE_DEVICES':os.environ.get('CUDA_VISIBLE_DEVICES'),'modules':{}}
for name in modules:
 try:
  m=importlib.import_module(name)
  try:v=importlib.metadata.version(name.split('.')[0])
  except importlib.metadata.PackageNotFoundError:v=getattr(m,'__version__','unknown')
  result['modules'][name]={'imported':True,'version':v}
 except Exception as e:result['modules'][name]={'imported':False,'error':f'{type(e).__name__}: {e}'}
if 'torch' in sys.modules:result['cuda_initialized']=sys.modules['torch'].cuda.is_initialized()
else:result['cuda_initialized']=False
result['passed']=all(x['imported'] for x in result['modules'].values()) and not result['cuda_initialized']
print('PROBE_JSON='+json.dumps(result))
sys.exit(0 if result['passed'] else 1)
