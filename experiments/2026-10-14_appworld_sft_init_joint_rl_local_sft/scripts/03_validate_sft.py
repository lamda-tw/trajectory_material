"""Independent persisted dataset/causal history/mask validation. CPU only."""
from common import *
os.environ.update(gpu_env())
import numpy as np,torch
from transformers import AutoTokenizer
from sft_dataset import LocalSFTDataset,CompletionCollator

def main():
 start=now();m=read(ROOT/'data/data_manifest.json');selection=[json.loads(l) for l in (ROOT/'data/selected_steps.jsonl').read_text().splitlines()];tokenizer=AutoTokenizer.from_pretrained(m['tokenizer'],local_files_only=True)
 require(sha(ROOT/'data/sft_samples.jsonl')==m['training_samples_sha256'],'Sample JSONL hash')
 source=None;original=None;count=0;tokens=0;keys=set();sensitive_input_keys={'labels','score','judge_reason','official_evaluation','current_observation'}
 ds=LocalSFTDataset(ROOT/'data/data_manifest.json');require(len(ds)==2623==len(m['samples'])==len(selection),'Sample coverage')
 with (ROOT/'data/sft_samples.jsonl').open() as f:
  for record,chosen,line in zip(m['samples'],selection,f,strict=True):
   sample=json.loads(line)
   require((sample['trajectory_id'],sample['step_id'])==(chosen['trajectory_id'],chosen['step_id']),'Original selected identity')
   key=(sample['trajectory_id'],sample['step_id']);require(key not in keys,'Duplicate sample identity');keys.add(key)
   if sample['source']!=source:
    source=sample['source'];require(sha(source)==sample['source_sha256'],'Original source hash');original=read(source)
   st=original['steps'][sample['step_id']-1];require(st['step']==sample['step_id'],'Source step identity')
   history=[dict(v) for v in original['initial_messages']]
   for prev in original['steps'][:sample['step_id']-1]:
    history.extend([{'role':'assistant','content':prev['history_assistant_text']+'\n\n'},{'role':'user','content':'Output:\n```\n'+prev['observation'].rstrip()+'\n```\n\n'}])
   require(history==sample['messages'],'Reconstructed strictly prior history mismatch')
   require(all(set(msg)=={'role','content'} for msg in history),'Unexpected message fields')
   require(not set(sample)&sensitive_input_keys,'Judgement/outcome fields added to sample')
   prompt=tokenizer.apply_chat_template(history,tokenize=True,add_generation_prompt=True,enable_thinking=False)
   require(prompt==st['prompt_ids'],'Independent prompt token check')
   require(sample['target_response']==st['text'],'Target response rewritten')
   require(tokenizer.decode(st['response_ids'],skip_special_tokens=True,clean_up_tokenization_spaces=False)==sample['target_response'],'Target decoded text check')
   path=ROOT/record['encoded_file'];require(sha(path)==record['encoded_sha256'],'Encoded hash')
   with np.load(path,allow_pickle=False) as a:
    n=len(st['prompt_ids']);t=len(st['response_ids']);full=st['prompt_ids']+st['response_ids']
    require(set(a.files)=={'input_ids','labels','attention_mask','loss_mask'},'NPZ fields')
    require(a['input_ids'].tolist()==full,'Stored input token mismatch')
    require(a['labels'].tolist()==[-100]*n+st['response_ids'],'Stored labels mismatch')
    require(a['loss_mask'].tolist()==[0]*n+[1]*t,'Stored mask mismatch')
    require(a['attention_mask'].tolist()==[1]*len(full),'Stored attention mismatch')
    require(sample['target_start']==n and sample['target_end_exclusive']==len(full),'Boundaries')
    require(sum(a['labels'][1:]!=-100)==t,'Shifted target count')
   loaded=ds[count];require(loaded['labels'].dtype==torch.long and loaded['labels'].tolist()==[-100]*n+st['response_ids'],'Training loader mismatch')
   count+=1;tokens+=t
   if count%400==0:print(json.dumps({'event':'validated','samples':count,'target_tokens':tokens}),flush=True)
 require(tokens==m['T_SFT'],'Target token sum')
 # Real variable-length samples verify right-padding cannot introduce targets.
 lengths=[r['total_tokens'] for r in m['samples']];idx=[int(np.argmin(lengths)),int(np.argmax(lengths))];examples=[ds[i] for i in idx]
 batch=CompletionCollator(tokenizer.pad_token_id)(examples)
 for i,x in enumerate(examples):
  n=len(x['input_ids']);require(torch.equal(batch['labels'][i,:n],x['labels']),'Collator altered labels')
  require(torch.all(batch['labels'][i,n:]==-100).item() and torch.all(batch['attention_mask'][i,n:]==0).item(),'Padding is supervised')
 # Small deterministic CE check: first response predicted at last prompt position; no prompt/pad loss.
 logits=torch.randn(2,7,19,generator=torch.Generator().manual_seed(20261014),requires_grad=True)
 labels=torch.tensor([[-100,-100,-100,4,5,6,-100],[-100,-100,7,8,-100,-100,-100]])
 loss=torch.nn.functional.cross_entropy(logits[:,:-1].reshape(-1,19),labels[:,1:].reshape(-1),ignore_index=-100,reduction='sum')
 expected=-sum(torch.log_softmax(logits[b,k-1],dim=-1)[labels[b,k]] for b in range(2) for k in range(1,7) if labels[b,k]!=-100)
 require(torch.allclose(loss,expected,rtol=1e-6,atol=1e-6),'Causal CE mismatch');loss.backward()
 for b in range(2):
  for pos in range(7):
   if pos==6 or labels[b,pos+1]==-100:require(torch.all(logits.grad[b,pos]==0).item(),'Gradient on nonsupervised prediction')
 require(not torch.cuda.is_initialized(),'Validation initialized CUDA')
 report={'passed':True,'started_at':start,'completed_at':now(),'samples':count,'T_SFT':tokens,'five_epoch_target_tokens':5*tokens,'full_selected_identity_coverage':True,'source_hashes_verified':len({x['source'] for x in m['samples']}),'full_original_prompt_ids_matched':count,'full_original_response_ids_matched':count,'target_text_matched':count,'strictly_prior_history_verified':count,'labels_and_masks_verified':count,'causal_shift_verified':True,'loader_all_rows_verified':True,'variable_length_padding_verified':True,'synthetic_CE_sum':float(loss.detach()),'synthetic_CE_reference':float(expected.detach()),'prompt_padding_prediction_gradients_zero':True,'no_target_truncation':True,'no_content_deduplication':True,'extra_quality_filters':[],'no_EOS_synthesis':True,'cuda_initialized':False,'model_loaded':False,'training_started':False,'script_sha256':sha(__file__),'manifest_sha256_before_review':sha(ROOT/'data/data_manifest.json')}
 dump(ROOT/'checks/token_mask.json',report);print(json.dumps(report),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:dump(ROOT/'checks/token_mask.json',{'passed':False,'at':now(),'error':f'{type(e).__name__}: {e}'});raise
