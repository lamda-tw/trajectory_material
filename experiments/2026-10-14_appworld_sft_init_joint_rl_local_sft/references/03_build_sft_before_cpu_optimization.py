"""CPU-only full original completion dataset; no inference, correction or filtering."""
from common import *
os.environ.update(gpu_env())
import argparse,collections,csv,hashlib,numpy as np,torch
from transformers import AutoTokenizer

def digest_ids(x):return hashlib.sha256(np.asarray(x,dtype='<i4').tobytes()).hexdigest()
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--selection',default=str(ROOT/'data/selected_steps.jsonl'));ap.add_argument('--source-manifest',default=str(ROOT/'references/scoring_source_manifest.json'));args=ap.parse_args()
 started=now();cfg=read(ROOT/'config/draft.json');selcheck=read(ROOT/'checks/selection.json');selection=Path(args.selection)
 require(sha(selection)==selcheck['output_hashes']['data/selected_steps.jsonl'],'Selection changed')
 require(read(ROOT/'checks/preflight.json')['passed'],'Preflight required')
 selected=[json.loads(l) for l in selection.read_text().splitlines()];require(len(selected)==2623,'Selected count')
 inventory=read(ROOT/'references/model_inventory.json');base=Path(cfg['model']['base'])
 for name,h in inventory['base_metadata_hashes'].items():require(sha(base/name)==h,f'Tokenizer/model metadata changed: {name}')
 require(sha(Path(cfg['model']['initial_adapter'])/'adapter_model.safetensors')==cfg['model']['adapter_weights_sha256'],'Initial adapter changed')
 tok=AutoTokenizer.from_pretrained(base,local_files_only=True)
 source_manifest=read(args.source_manifest);byid={x['id']:x for x in source_manifest['samples']}
 groups=collections.defaultdict(list)
 for x in selected:groups[x['id']].append(x)
 work=ROOT/'data/step03_build';require(not work.exists(),'Existing step03 build: inspect it before recovery');work.mkdir();(work/'encoded').mkdir()
 manifest=[];preview=[];finish=collections.Counter();eos=collections.Counter();pcounts=[];tcounts=[];totals=[];targets=[];source_checks=[];special_counts=collections.Counter()
 with (work/'sft_samples.jsonl').open('w') as sf:
  for gi,(sid,items) in enumerate(groups.items()):
   src=byid[sid];source=Path(src['source']);require(sha(source)==src['source_sha256']==items[0]['source_sha256'],'Original source changed');raw=read(source)
   wanted={x['step_id']:x for x in items};messages=[dict(x) for x in raw['initial_messages']]
   for step in raw['steps']:
    stepid=step['step']
    if stepid in wanted:
     chosen=wanted[stepid];require(chosen['score']>=4,'Selection includes a nonselected row')
     # Reconstruct exact causal history, independently compare with originally served token IDs.
     prompt=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False)
     require(prompt==step['prompt_ids'],f'Prompt mismatch {sid}:{stepid}')
     response=step['response_ids'];require(bool(response) and all(type(x) is int and 0<=x<len(tok) for x in response),'Invalid response IDs')
     decoded=tok.decode(response,skip_special_tokens=True,clean_up_tokenization_spaces=False)
     require(decoded==step['text'],f'Original target text/token mismatch {sid}:{stepid}')
     n=len(prompt);m=len(response);full=np.asarray(prompt+response,dtype=np.int32);labels=np.full(len(full),-100,dtype=np.int32);labels[n:]=response
     mask=np.zeros(len(full),dtype=np.uint8);mask[n:]=1;attention=np.ones(len(full),dtype=np.uint8)
     require(np.array_equal(labels[n:],full[n:]) and np.all(labels[:n]==-100),'Label mask mismatch')
     require(int(mask.sum())==m and int((labels[1:]!=-100).sum())==m,'Causal shift lost a target token')
     name=f'{sid}__step_{stepid:03d}.npz';path=work/'encoded'/name
     np.savez_compressed(path,input_ids=full,labels=labels,attention_mask=attention,loss_mask=mask)
     sample_id=f'{sid}:{stepid}'
     out={'sample_id':sample_id,'trajectory_id':chosen['trajectory_id'],'task_id':chosen['task_id'],'step_id':stepid,'messages':messages,'target_response':step['text'],'encoded_file':f'data/encoded/{name}','prompt_tokens':n,'target_tokens':m,'total_tokens':n+m,'target_start':n,'target_end_exclusive':n+m,'target_boundary':'original generated token IDs, including only original generated special/end tokens','source':str(source),'source_sha256':src['source_sha256']}
     sf.write(json.dumps(out,ensure_ascii=False)+'\n')
     record={k:v for k,v in out.items() if k not in ['messages','target_response']}
     record.update(encoded_sha256=sha(path),prompt_ids_sha256=digest_ids(prompt),response_ids_sha256=digest_ids(response),target_text_sha256=hashlib.sha256(step['text'].encode()).hexdigest(),finish_reason=step.get('finish_reason'),ends_with_eos=response[-1]==tok.eos_token_id)
     manifest.append(record);pcounts.append(n);tcounts.append(m);totals.append(n+m);finish[step.get('finish_reason')]+=1;eos[record['ends_with_eos']]+=1;special_counts.update(x for x in response if x in tok.all_special_ids)
     targets.append((n+m,sample_id));preview.append({'sample_id':sample_id,'labels':chosen['labels'],'score':chosen['score'],'prompt_tokens':n,'target_tokens':m,'target_excerpt':step['text'][:350],'step_id':stepid,'finish_reason':step.get('finish_reason'),'eos':record['ends_with_eos']})
    # This reproduces the original rollout interaction protocol, including prior parser repairs.
    messages.append({'role':'assistant','content':step['history_assistant_text']+'\n\n'})
    if step['code']:
     messages.append({'role':'user','content':'Output:\n```\n'+step['observation'].rstrip()+'\n```\n\n'})
    if stepid>=max(wanted):break
   source_checks.append({'id':sid,'source_sha256':src['source_sha256'],'selected_steps':len(items)})
   if (gi+1)%25==0:print(json.dumps({'event':'progress','source_trajectories':gi+1,'samples':len(manifest),'target_tokens':sum(tcounts)}),flush=True)
 require([(x['trajectory_id'],x['step_id']) for x in manifest]==[(x['trajectory_id'],x['step_id']) for x in selected],'Output identity/order differs')
 require(not torch.cuda.is_initialized(),'CPU construction initialized CUDA')
 def stats(a):return {'sum':sum(a),'min':min(a),'max':max(a),'mean':float(np.mean(a)),**{f'p{q}':float(np.percentile(a,q)) for q in [50,90,95,99]}}
 summary={'sample_count':len(manifest),'source_trajectories':len(groups),'tasks':len({x['task_id'] for x in selected}),'prompt_tokens':stats(pcounts),'target_tokens':stats(tcounts),'total_tokens':stats(totals),'T_SFT':sum(tcounts),'five_epoch_target_tokens':5*sum(tcounts),'finish_reasons':dict(finish),'eos_terminated':eos[True],'no_eos_appended':True,'non_eos_terminated':eos[False],'special_target_tokens':{str(k):v for k,v in special_counts.items()},'over_32000':sum(v>32000 for v in totals),'longest_samples':sorted(targets,reverse=True)[:10]}
 dump(work/'length_statistics.json',summary)
 data_manifest={'created_at':now(),'started_at':started,'status':'constructed_pending_independent_validation','sample_count':len(manifest),'T_SFT':sum(tcounts),'selection_sha256':sha(selection),'selection_policy_sha256':sha(ROOT/'config/selection_policy.json'),'tokenizer':str(base),'tokenizer_metadata_hashes':inventory['base_metadata_hashes'],'chat_template_kwargs':{'add_generation_prompt':True,'enable_thinking':False},'encoding':'exact prompt reconstruction checked against logged prompt_ids; original response_ids checked by decoded text; no response re-tokenization, appended EOS or padding','history_protocol':'original initial_messages + previous history_assistant_text with two newlines + user Output observation wrapper; current and future feedback excluded','loss':'unshifted labels: -100 on entire prompt; original response token IDs on target. Standard causal shift in model/loss, not in stored labels.','row_fields_npz':{'input_ids':'int32 -> torch.long','labels':'int32 -> torch.long','attention_mask':'uint8 -> torch.long','loss_mask':'uint8 -> torch.bool'},'training_samples_file':'data/sft_samples.jsonl','training_samples_sha256':sha(work/'sft_samples.jsonl'),'script_sha256':sha(__file__),'common_script_sha256':sha(ROOT/'scripts/common.py'),'cuda_initialized':False,'model_loaded':False,'training_started':False,'samples':manifest}
 dump(work/'data_manifest.json',data_manifest);dump(work/'source_checks.json',source_checks);dump(work/'review_candidates.json',preview)
 for name in ['encoded','sft_samples.jsonl','data_manifest.json','length_statistics.json','source_checks.json','review_candidates.json']:
  dest=ROOT/'data'/name;require(not dest.exists(),f'Destination already exists {dest}');os.replace(work/name,dest)
 work.rmdir()
 print(json.dumps({'event':'constructed','samples':len(manifest),'T_SFT':sum(tcounts),'max_total_tokens':max(totals),'cuda_initialized':False}),flush=True)
if __name__=='__main__':
 try:main()
 except Exception as e:dump(ROOT/'checks/step03_build_failure.json',{'at':now(),'error':f'{type(e).__name__}: {e}'});raise
