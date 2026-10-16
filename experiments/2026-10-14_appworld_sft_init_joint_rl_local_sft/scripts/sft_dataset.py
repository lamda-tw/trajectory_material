"""Completion-only CPU dataset; no truncation, filtering, packing or model load."""
from pathlib import Path
import json,numpy as np,torch
from torch.utils.data import Dataset
class LocalSFTDataset(Dataset):
 def __init__(self,manifest_path):
  path=Path(manifest_path);self.root=path.parent.parent
  self.manifest=json.loads(path.read_text());self.rows=self.manifest['samples']
 def __len__(self):return len(self.rows)
 def __getitem__(self,index):
  row=self.rows[index]
  with np.load(self.root/row['encoded_file'],allow_pickle=False) as a:
   return {key:torch.from_numpy(a[key].astype(np.int64)) for key in ('input_ids','labels','attention_mask')}
class CompletionCollator:
 def __init__(self,pad_token_id):self.pad_token_id=int(pad_token_id)
 def __call__(self,examples):
  if not examples:raise ValueError('Empty batch')
  longest=max(len(x['input_ids']) for x in examples);b=len(examples)
  out={'input_ids':torch.full((b,longest),self.pad_token_id,dtype=torch.long),'labels':torch.full((b,longest),-100,dtype=torch.long),'attention_mask':torch.zeros((b,longest),dtype=torch.long)}
  for i,ex in enumerate(examples):
   n=len(ex['input_ids'])
   for key in out:out[key][i,:n]=ex[key]
  return out
