from pathlib import Path
import json
from safetensors.torch import load_file
from train_ddp import state_sha,sha,dump
R=Path(__file__).resolve().parents[1];done=json.loads((R/'training/rubric/COMPLETE.json').read_text());assert done['epochs']==5
out={'checkpoints':{},'selection':'User requested epochs 1,3,5 before any DEV result of this run; no best-checkpoint selection.'}
for epoch in [1,3,5]:
 p=R/f'training/rubric/epoch_{epoch:02d}_adapter';ep=json.loads((R/f'training/rubric/epoch_{epoch:02d}.json').read_text());actual=state_sha(load_file(str(p/'adapter_model.safetensors'),device='cpu'));assert actual==ep['adapter_tensor_sha256'],epoch
 out['checkpoints'][str(epoch)]={'epoch':epoch,'path':str(p),'tensor_sha256':actual,'adapter_files':{x.name:sha(x) for x in p.iterdir() if x.is_file()}}
assert out['checkpoints']['5']['tensor_sha256']==done['final_adapter_tensor_sha256']
dump(R/'CHECKPOINTS_135.json',out);print(json.dumps(out,ensure_ascii=False,indent=2))
