"""One server, one immutable adapter, one complete pool. Never trains or calls a judge."""
from pathlib import Path
import argparse,concurrent.futures,json,os,subprocess,hashlib
from common import ROOT,read,dump,sha,require,now
from collection_protocol import collection_fingerprint
from policy_server import owned_server
from round_data import build_pool

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--adapter',type=Path,required=True)
    ap.add_argument('--round',type=int,required=True);ap.add_argument('--output',type=Path,required=True)
    ap.add_argument('--mode',choices=['smoke','formal'],default='smoke');ap.add_argument('--smoke-tasks',type=int,default=1)
    ap.add_argument('--smoke-group-size',type=int,default=2);ap.add_argument('--smoke-max-steps',type=int,default=2)
    ap.add_argument('--execute',action='store_true');a=ap.parse_args();require(a.execute,'Explicit --execute required')
    a.output=a.output.resolve();require(a.output.is_relative_to(ROOT),'Isolated output required')
    if a.mode=='smoke':require(a.output.is_relative_to(ROOT/'smoke'),'Smoke output must be separate')
    else:
        frozen_manifest=read(ROOT/'FREEZE.json')
        require(sha(ROOT/'config/training_config.json')==frozen_manifest['training_config_sha256'],'Frozen config changed')
        require(frozen_manifest.get('files'),'Frozen hashes required')
        for filename,expected in frozen_manifest['files'].items():require(sha(ROOT/filename)==expected,'Frozen artifact changed: '+filename)
    policy=read(ROOT/'config/resource_policy.json');require(os.environ.get('CUDA_VISIBLE_DEVICES')==policy['physical_gpu_uuid'],'Use gpu1_run')
    require(a.round>=1,'Invalid round');adapter=a.adapter.resolve();weight_hash=sha(adapter/'adapter_model.safetensors')
    active=read(ROOT/('config/training_config.json' if a.mode=='formal' else 'config/pool_training_draft.json'))
    task_ids=(ROOT/'config/train90.txt').read_text().split();size=active['schedule_candidate']['rollouts_per_task'];max_steps=active['online_sampling_candidate']['max_steps']
    if a.mode=='smoke':task_ids=task_ids[:a.smoke_tasks];size=a.smoke_group_size;max_steps=a.smoke_max_steps
    else:
        require(a.round>=2,'Formal round 1 imports existing pool')
        manifest=read(adapter/'manifest.json');state=manifest['state']
        require(state['mode']=='formal' and state['round']==a.round-1,'Collect only from previous formal round-final checkpoint')
        frozen=read(ROOT/'config/training_config.json')
        require(state['batch']==frozen['schedule_candidate']['batches_per_round'],'Previous round not complete')
        require(manifest['adapter_sha256']==weight_hash,'Parent adapter changed')
    cfg={'paths':{'base_model':'/root/autodl-tmp/models/Qwen3-8B','vllm_python':'/root/autodl-tmp/envs/qwen3-vllm-py312/bin/python'},
         'server':{'host':'127.0.0.1','port':8147,'gpu':policy['physical_gpu_uuid'],'model_name':'joint-qwen3-8b',
                   'adapter_name':'joint-round-policy','gpu_memory_utilization':0.80,'max_num_seqs':6,'minimum_free_gpu_gib':70,
                   'startup_timeout_seconds':900,'request_timeout_seconds':600},
         'agent':{'prompt':'assets/agent_prompt.txt','max_steps':max_steps,'max_model_len':active['online_sampling_candidate']['max_model_len'],'max_new_tokens':active['online_sampling_candidate']['max_new_tokens_per_action']},
         'sampling':{'temperature':active['online_sampling_candidate']['temperature'],'group_size':size},'evaluation':{'temperature':0.0,'tasks':'config/dev57.txt'},
         'training':{'lora':{'r':8}},'adapter_sha256':weight_hash,'round':a.round,'mode':a.mode}
    a.output.mkdir(parents=True,exist_ok=True);config_path=a.output/'collection_config.json'
    if config_path.exists():require(read(config_path)==cfg,'Resume collection config changed')
    else:dump(config_path,cfg)
    fingerprint=collection_fingerprint(cfg);policy_id='adapter:'+weight_hash
    jobs=[];paths=[]
    for task in task_ids:
        for sample in range(size):
            output=a.output/'trajectories'/f'{task}__{sample:02d}.json';paths.append(output)
            seed=int(hashlib.sha256(f'20261014:{a.round}:{task}:{sample}'.encode()).hexdigest()[:8],16)%(2**31-1)
            job={'mode':'train','task_id':task,'sample':sample,'seed':seed,'update':0,'episode_id':f'joint_{fingerprint[:10]}_{task}_{sample}',
                 'runtime_name':'appworld','model':'joint-round-policy','output':str(output),'fingerprint':fingerprint,'policy_id':policy_id}
            jobpath=a.output/'jobs'/f'{task}__{sample:02d}.json'
            if output.exists():require(read(output)['job']==job,'Existing rollout belongs to another request')
            else:dump(jobpath,job);jobs.append(jobpath)
    env={**os.environ,'JOINT_COLLECTION_CONFIG':str(config_path)}
    def worker(jobpath):
        logpath=a.output/'worker_logs'/f'{jobpath.stem}.log';logpath.parent.mkdir(exist_ok=True)
        # Retrying an infrastructure failure never examines success/reward.
        for attempt in range(1,4):
            with logpath.open('a') as log:
                proc=subprocess.run(['/root/autodl-tmp/envs/appworld-0.2.0-py312/bin/python',str(ROOT/'scripts/rollout_worker.py'),
                                     '--job',str(jobpath),'--execute'],env=env,cwd=ROOT,stdout=log,stderr=log)
            dump(a.output/'attempts'/f'{jobpath.stem}_{attempt}.json',{'at':now(),'returncode':proc.returncode,'job':str(jobpath)})
            if proc.returncode==0:return
        raise RuntimeError('Infrastructure failure after 3 attempts: '+str(logpath))
    if jobs:
        with owned_server(cfg,a.output/'server',adapter):
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
                for completed,_ in enumerate(executor.map(worker,jobs),1):
                    dump(a.output/'progress.json',{'at':now(),'new_jobs_completed':completed,'new_jobs':len(jobs),'behavior_adapter_sha256':weight_hash})
    require(sha(adapter/'adapter_model.safetensors')==weight_hash,'Behavior weights mutated during collection')
    pool=build_pool(paths,a.output/'pool.json',a.round,weight_hash,task_ids,size,sha(config_path))
    print(json.dumps({'pool':str(a.output/'pool.json'),'count':pool['count'],'mode':a.mode,'parameter_updates':0}))
if __name__=='__main__':main()
