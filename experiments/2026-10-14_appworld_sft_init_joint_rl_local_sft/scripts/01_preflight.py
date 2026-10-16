"""CPU-only source/model/split integrity and import/resource preflight; no training."""
from common import *
import argparse,csv,shutil,sys,jsonschema
from collections import Counter

def ids(p):return [x.strip() for x in Path(p).read_text().splitlines() if x.strip() and not x.startswith('#')]
def inspect(cfg):
 began=now();j=Path(cfg['selection']['input']).parents[1];m=read(j/'manifest.json');sm=read(j/'score_manifest.json')
 require(sha(j/'manifest.json')==sm['source_manifest_sha256'],'Source manifest hash')
 for f,meta in sm['outputs'].items():require(sha(j/f)==meta['sha256'],f'Output hash {f}')
 for f,h in read(j/'FREEZE.json')['files'].items():require(sha(j/f)==h,f'Frozen file {f}')
 require(read(j/'analysis/validation.json')['passed'],'Scoring structural validation')
 require(sha(j/'judge_config.json')==sm['config_sha256'],'Judge config hash')
 schema=read(j/'assets/output_schema_v6.json');validator=jsonschema.Draft202012Validator(schema)
 rows=list(csv.DictReader((j/'analysis/step_labels.csv').open()));csv_index={}
 for x in rows:
  k=(x['trajectory_id'],int(x['step_id']));require(k not in csv_index,'Duplicate CSV step');csv_index[k]=x
 require(len(rows)==9886 and len(m['samples'])==len(sm['samples'])==540,'Source counts')
 scored={x['id']:x for x in sm['samples']}; inventory=[];expected_keys=set();tasks=Counter();policy_ids=set();prompt=(j/'assets/prompt_v6_en.txt').read_text()
 for sample in m['samples']:
  sid=sample['id'];ref=scored[sid];source=Path(sample['source']);inp=j/sample['input'];judgement=j/ref['judgement'];folder=judgement.parent
  require(sha(source)==sample['source_sha256']==ref['source_sha256'],f'Source hash {sid}')
  require(sha(inp)==sample['input_sha256']==ref['input_sha256'],f'Input hash {sid}')
  require(sha(judgement)==ref['judgement_sha256'],f'Judgement hash {sid}')
  raw=read(source);payload=read(inp);judged=read(judgement);validator.validate(judged)
  step_ids=[s['step'] for s in raw['steps']];payload_ids=[s['id'] for s in payload['steps']]
  require(step_ids==payload_ids==[r[0] for r in judged['steps']]==list(range(1,sample['steps']+1)),f'Step order {sid}')
  require(judged['trajectory_id']==payload['trajectory_id']==sample['trajectory_id']==ref['trajectory_id'],f'Trajectory identity {sid}')
  require(set(payload)=={'trajectory_id','task','agent_instructions','reference_api_docs','steps','termination'},'Payload keys')
  require((folder/'request.txt').read_text()==prompt.replace('{{TRAJECTORY_JSON}}',inp.read_text()),f'Request {sid}')
  meta=read(folder/'metadata.json');require(meta['accepted_attempt']==ref['accepted_attempt'],'Accepted attempt')
  require(read(folder/f"attempt_{ref['accepted_attempt']:03d}"/'response.json')==judged,'Accepted response consistency')
  for step,label,reason in judged['steps']:
   k=(sample['trajectory_id'],step);require(k not in expected_keys,'Duplicate manifest identity');expected_keys.add(k);x=csv_index[k]
   require(x['id']==sid and x['task_id']==sample['task_id'] and x['labels']==label and x['reason']==reason,'CSV/judgement mismatch')
   require(''.join(x[f'R{i}'] for i in range(1,9))==label,'Expanded label columns mismatch')
   require((not reason if set(label)<=set('PN') else bool(reason)) and len(reason)<=60,'Reason constraints')
  tasks[sample['task_id']]+=1;policy_ids.add(sample['policy_id'])
  inventory.append({k:sample[k] for k in ['id','trajectory_id','task_id','source','source_sha256','input_sha256','steps','policy_id']}|{'judgement':str(judgement),'judgement_sha256':ref['judgement_sha256']})
 require(expected_keys==set(csv_index),'CSV coverage');require(len(policy_ids)==1 and next(iter(policy_ids)).startswith('initial-lora:'),'Initial SFT policy')
 require(len(tasks)==90 and set(tasks.values())=={6},'90x6 task groups')
 original=WORKSPACE/'experiments/2026-10-08_static_rubric_grpo_lora_init';oc=read(original/'config.json');data=Path(oc['paths']['appworld_data'])
 train=ids(data/'datasets/train.txt');dev=ids(data/'datasets/dev.txt')
 require(len(train)==len(set(train))==90 and len(dev)==len(set(dev))==57 and not set(train)&set(dev),'Train/DEV identity overlap')
 require(train==ids(original/'assets/splits/train_all.txt') and dev==ids(original/'assets/splits/dev.txt') and set(train)==set(tasks),'Original/official split mismatch')
 require((data/'api_docs').is_dir() and (data/'base_dbs').is_dir(),'AppWorld shared data missing')
 for task in train+dev:
  require((data/'tasks'/task/'specs.json').is_file() and (data/'tasks'/task/'dbs').is_dir() and (data/'tasks'/task/'ground_truth').is_dir(),f'Task assets {task}')
 for name,values in [('train90',train),('dev57',dev)]:(ROOT/'config'/f'{name}.txt').write_text('\n'.join(values)+'\n')
 adapter=Path(cfg['model']['initial_adapter']);ah=sha(adapter/'adapter_model.safetensors');require(ah==cfg['model']['adapter_weights_sha256'],'Adapter hash')
 ac=read(adapter/'adapter_config.json');require(ac['r']==8 and ac['lora_alpha']==16,'Adapter structure')
 base=Path(cfg['model']['base']);require(Path(ac['base_model_name_or_path'])==base,'Adapter base mismatch')
 bi=read(base/'model.safetensors.index.json');shards=[]
 for f in sorted(set(bi['weight_map'].values())):
  x=base/f;require(x.is_file() and x.stat().st_size>0,'Missing base shard');shards.append({'path':str(x),'bytes':x.stat().st_size})
 mf=['config.json','generation_config.json','model.safetensors.index.json','tokenizer.json','tokenizer_config.json','merges.txt','vocab.json']
 model={'adapter_path':str(adapter),'adapter_weights_sha256':ah,'adapter_config':ac,'adapter_config_sha256':sha(adapter/'adapter_config.json'),'base_metadata_hashes':{f:sha(base/f) for f in mf},'base_shards':shards,'base_shard_verification':'existence and size; full weight-shard hash not computed','base_config':read(base/'config.json')}
 dump(ROOT/'references/model_inventory.json',model)
 environments={}
 for name,modules in [('training_python',['torch','transformers','peft','safetensors','jsonschema']),('appworld_python',['appworld','appworld.environment']),('vllm_python',['torch','vllm'])]:
  py=oc['paths'][name];require(Path(py).is_file() and os.access(py,os.X_OK),f'Python unavailable {name}')
  proc=run([py,str(ROOT/'scripts/env_probe.py'),*modules],timeout=240)
  (ROOT/'logs'/f'{name}_probe.log').write_text(proc.stdout+'\nSTDERR\n'+proc.stderr)
  lines=[x for x in proc.stdout.splitlines() if x.startswith('PROBE_JSON=')];require(bool(lines),f'No probe result {name}')
  result=json.loads(lines[-1].split('=',1)[1]);environments[name]=result
  dump(ROOT/'references/environment.json',{'checked_at':now(),'environments':environments})
  require(proc.returncode==0 and result['passed'],f'Import failure {name}: see logs')
 gpu=run(['nvidia-smi','--query-gpu=index,uuid,pci.bus_id,name,memory.total,memory.used,memory.free,utilization.gpu','--format=csv,noheader,nounits'])
 require(gpu.returncode==0,'GPU read-only query failed');gpus=[]
 for vals in csv.reader(gpu.stdout.splitlines(),skipinitialspace=True):gpus.append(dict(zip(['index','uuid','pci_bus_id','name','total_mib','used_mib','free_mib','utilization_percent'],vals)))
 rp=read(ROOT/'config/resource_policy.json');allowed=[g for g in gpus if g['index']=='1'];require(len(allowed)==1 and allowed[0]['uuid']==rp['physical_gpu_uuid'],'Physical GPU1 UUID mismatch')
 apps=run(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader,nounits']);require(apps.returncode==0,'GPU process query failed')
 disk=shutil.disk_usage(ROOT)
 resources={'checked_at':now(),'policy':rp,'gpus_read_only_snapshot':gpus,'compute_processes_read_only_snapshot':apps.stdout.strip(),'disk_bytes':{'total':disk.total,'used':disk.used,'free':disk.free},'resource_scope':'Snapshot only; full-run VRAM/disk feasibility requires step 3 length inventory and step 6 smoke; no GPU allocations made.','gpu0_use_authorized':False,'single_gpu_only':True,'gpu1_available_at_snapshot':int(allowed[0]['used_mib'])==0,'pending':['T_SFT/context capacity','peak training/serving/reference VRAM','full-run storage and throughput budget']}
 dump(ROOT/'references/resources.json',resources)
 dump(ROOT/'references/input_inventory.json',{'checked_at':now(),'score_manifest':str(j/'score_manifest.json'),'score_manifest_sha256':sha(j/'score_manifest.json'),'label_csv_sha256':sha(j/'analysis/step_labels.csv'),'source_manifest_sha256':sha(j/'manifest.json'),'samples':inventory,'source_policy_ids':sorted(policy_ids)})
 for src,name in [(j/'manifest.json','scoring_source_manifest.json'),(j/'score_manifest.json','score_manifest.json'),(j/'analysis/validation.json','scoring_validation.json'),(j/'assets/output_schema_v6.json','scoring_schema.json'),(data/'datasets/train.txt','official_train.txt'),(data/'datasets/dev.txt','official_dev.txt')]:shutil.copy2(src,ROOT/'references'/name)
 report={'passed':True,'started_at':began,'completed_at':now(),'stage':1,'trajectories':540,'steps':9886,'labels':79088,'source_hashes_verified':540,'input_hashes_verified':540,'judgement_hashes_verified':540,'csv_rows_matched_to_judgements':9886,'original_step_order_verified':True,'train_tasks':90,'dev_tasks':57,'split_overlap':0,'adapter_hash_verified':True,'environment_imports_passed':True,'cuda_initialized_by_probes':False,'gpu_allocations':0,'model_loads':0,'new_judge_calls':0,'optimizer_updates':0,'gpu_policy_verified':'physical GPU1 only','training_readiness':'not established; steps 3-7 remain','script_sha256':sha(__file__),'config_sha256':sha(ROOT/'config/draft.json')}
 dump(ROOT/'checks/preflight.json',report);return report
if __name__=='__main__':
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--config',default=str(ROOT/'config/draft.json'));a=ap.parse_args()
 try:print(json.dumps(inspect(read(a.config)),ensure_ascii=False))
 except Exception as e:
  dump(ROOT/'checks/preflight.json',{'passed':False,'at':now(),'error':f'{type(e).__name__}: {e}'});raise
