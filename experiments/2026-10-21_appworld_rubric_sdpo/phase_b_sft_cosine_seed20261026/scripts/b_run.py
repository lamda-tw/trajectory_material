"""Explicitly gated synchronous Phase B runner. No execution in preparation mode."""
from b_common import *
from a_policy_server import owned_server
from b_judge import judge_batch
from b_dataset import compile_batch
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,json,subprocess,time


def collect(arm,number):
    authorize('rollout_allowed');cfg=config();folder=batch_dir(arm,number);folder.mkdir(parents=True,exist_ok=True)
    parent=previous_checkpoint(arm,number);identity=policy_identity(parent)
    schedule=read(B/'config/schedule.json')['batches'][number-1]
    if (folder/'collection.json').exists():
        cached=read(folder/'collection.json');assert cached['policy_identity']==identity
        for item in cached['trajectories']:assert file_sha(folder/item['path'])==item['sha256']
        return
    adapter=parent/read(parent/'COMPLETE.json')['student_adapter'] if parent else None
    def worker(job_path):
        job=read(job_path);path=Path(job['output']);log=path.with_suffix('.log')
        if path.exists():
            cached=read(path);assert cached['job']==job
            return path
        # Infrastructure retry only; reuse the same policy/task/seed. Completed model failures are retained.
        for attempt in range(2):
            with log.open('a') as output:
                process=subprocess.run([cfg['paths']['appworld_python'],str(S/'b_rollout_worker.py'),'--job',str(job_path)],
                    env=CPU,stdout=output,stderr=subprocess.STDOUT,timeout=cfg['collection']['trajectory_timeout_seconds'])
            if process.returncode==0:
                assert read(path)['job']==job
                return path
        raise RuntimeError(f'Rollout infrastructure failed; no task replacement: {job_path}')
    with gpu_lock('rollout_allowed'):
        with owned_server(cfg,folder/'server_logs',adapter) as model:
            jobs=[]
            for item in schedule['tasks']:
                episode=f'b{number:03d}_{item["task_id"]}'
                job={'episode_id':episode,'task_id':item['task_id'],'seed':item['seed'],'model':model,
                     'policy_identity':identity,'config_sha256':file_sha(B/'config/run.json'),
                     'runtime':str(folder/'runtime'/episode),'output':str(folder/'trajectories'/(episode+'.json'))}
                path=folder/'jobs'/(episode+'.json');frozen_json(path,job);Path(job['output']).parent.mkdir(parents=True,exist_ok=True);jobs.append(path)
            with ThreadPoolExecutor(max_workers=cfg['collection']['workers']) as pool:
                paths=[f.result() for f in as_completed([pool.submit(worker,p) for p in jobs])]
    records=[{'id':p.stem,'path':str(p.relative_to(folder)),'sha256':file_sha(p),'steps':len(read(p)['steps'])} for p in sorted(paths)]
    frozen_json(folder/'collection.json',{'arm':arm,'batch':number,'policy_identity':identity,'schedule':schedule,'trajectories':records})


def main(arm,until_batch,execute):
    if not execute:
        raise PermissionError('Preparation only. A future explicit start instruction and execution gate are required.')
    authorize('training_allowed');authorize('rollout_allowed');authorize('external_judging')
    assert arm in read(B/'config/execution_gate.json').get('allowed_arms',[]), 'This arm is not authorized'
    cfg=config();assert 1<=until_batch<=len(read(B/'config/schedule.json')['batches'])
    lock=run_dir(arm)/'runner.lock';lock.parent.mkdir(parents=True,exist_ok=True)
    with lock.open('a+') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        for number in range(1,until_batch+1):
            folder=batch_dir(arm,number)
            if (folder/'checkpoint/COMPLETE.json').exists():
                saved=read(folder/'checkpoint/COMPLETE.json')
                from b_retention import validate_committed
                validate_committed(folder/'checkpoint', allow_pruned=True)
                continue
            status('collecting',arm=arm,batch=number,training_started=number>1)
            collect(arm,number)
            status('whole_trajectory_judging',arm=arm,batch=number)
            judge_batch(folder)
            data=compile_batch(folder,arm)
            status('batch_prepared_for_update',arm=arm,batch=number,counts=data['counts'])
            log=folder/'training.log'
            with log.open('a') as out:
                result=subprocess.run([cfg['paths']['training_python'],str(S/'b_train_batch.py'),
                    '--arm',arm,'--batch',str(number)],env=dict(CPU,USE_TORCH='1',USE_TF='0'),stdout=out,stderr=subprocess.STDOUT)
            if result.returncode:raise RuntimeError(f'Training failed before checkpoint commit: {log}')
            completed=read(folder/'checkpoint/COMPLETE.json')
            status('batch_complete',arm=arm,batch=number,optimizer_updates=completed['optimizer_updates'],training_started=True)
        status('requested_batches_complete',arm=arm,batches=until_batch,
               optimizer_updates=read(batch_dir(arm,until_batch)/'checkpoint/COMPLETE.json')['optimizer_updates'])


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--arm',choices=['mixed','sft','sdpo'],default='sft')
    parser.add_argument('--until-batch',type=int,default=54);parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    try:main(args.arm,args.until_batch,args.execute)
    except Exception as error:
        status('not_started_or_needs_attention',error=str(error));raise
