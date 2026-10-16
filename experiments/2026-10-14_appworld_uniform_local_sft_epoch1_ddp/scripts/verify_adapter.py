from pathlib import Path
import json,hashlib
from safetensors.torch import load_file
from train_ddp import state_sha
R=Path(__file__).resolve().parents[1]
done=json.loads((R/'training/uniform/COMPLETE.json').read_text());assert done['epochs']==1 and done['updates']==1220 and not done['probe']
a=R/'training/uniform/adapter';b=R/'training/uniform/epoch_01_adapter'
for n,h in done['adapter_files'].items():assert hashlib.sha256((a/n).read_bytes()).hexdigest()==h
for path in [a,b]:assert state_sha(load_file(str(path/'adapter_model.safetensors'),device='cpu'))==done['final_adapter_tensor_sha256']
r={'phase':'passed','final_and_epoch1_tensors_match':True,'final_adapter':str(a),'epoch1_adapter':str(b),'tensor_sha256':done['final_adapter_tensor_sha256']}
(R/'MODEL_VERIFICATION.json').write_text(json.dumps(r,indent=2)+'\n');print(json.dumps(r))
