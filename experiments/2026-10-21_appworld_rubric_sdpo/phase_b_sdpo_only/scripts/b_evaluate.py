"""Epoch-end dev57 evaluation; student only, no diagnostic feedback."""
from b_common import *
from a_policy_server import owned_server
from concurrent.futures import ThreadPoolExecutor,as_completed
import argparse,subprocess


def main(arm,number=None):
    authorize('evaluation_allowed');cfg=config();number=number or cfg['training']['update_opportunities']
    gate=read(B/'config/execution_gate.json')
    assert arm in gate['allowed_arms'] and number in gate['evaluation_batches']
    assert number in (18,36)
    checkpoint=batch_dir(arm,number)/'checkpoint';done=read(checkpoint/'COMPLETE.json')
    for name,h in done['files'].items():assert file_sha(checkpoint/name)==h
    folder=run_dir(arm)/f'epoch_{number//18:02d}_dev57';folder.mkdir(parents=True,exist_ok=True)
    identity=policy_identity(checkpoint)
    frozen_json(folder/'identity.json',{'policy_identity':identity,'checkpoint_batch':number,'epoch':number//18,
        'config_sha256':file_sha(B/'config/run.json'),'no_feedback':True})
    if (folder/'summary.json').exists():
        summary=read(folder/'summary.json')
        assert len(summary['results'])==57 and {x['task_id'] for x in summary['results']}==set((B/'config/dev57.txt').read_text().split())
        for item in summary['results']:assert file_sha(folder/'trajectories'/(item['task_id']+'.json'))==item['trajectory_sha256']
        return summary
    def worker(path):
        job=read(path);target=Path(job['output']);target.parent.mkdir(parents=True,exist_ok=True)
        for attempt in range(2):
            if target.exists():break
            try:
                with target.with_suffix('.log').open('a') as log:
                    p=subprocess.run([cfg['paths']['appworld_python'],str(S/'b_rollout_worker.py'),'--job',str(path)],
                        env=CPU,stdout=log,stderr=subprocess.STDOUT,timeout=cfg['collection']['trajectory_timeout_seconds'])
                if p.returncode==0:break
            except subprocess.TimeoutExpired:
                pass
        if not target.exists():raise RuntimeError(f'Dev infrastructure failure after two identical-seed attempts: {path}')
        value=read(target);assert value['job']==job
        return {'task_id':job['task_id'],**value['official_evaluation'],'steps':len(value['steps']),
                'termination':value['termination'],'trajectory_sha256':file_sha(target)}
    results=[]
    with gpu_lock('evaluation_allowed'):
        with owned_server(cfg,folder/'server_logs',checkpoint/done['student_adapter']) as model:
            jobs=[]
            for task in (B/'config/dev57.txt').read_text().split():
                job={'mode':'dev','task_id':task,'seed':cfg['evaluation']['seed'],'model':model,'policy_identity':identity,
                     'config_sha256':file_sha(B/'config/run.json'),'episode_id':'dev_'+task,'runtime':str(folder/'runtime'/task),
                     'output':str(folder/'trajectories'/(task+'.json'))}
                path=folder/'jobs'/(task+'.json');frozen_json(path,job);jobs.append(path)
            with ThreadPoolExecutor(max_workers=cfg['collection']['workers']) as pool:
                for f in as_completed([pool.submit(worker,p) for p in jobs]):
                    results.append(f.result());write_json(folder/'partial.json',{'completed':len(results),'total':57,'results':results})
    assert len(results)==57
    summary={'completed_at':now(),'epoch':number//18,'checkpoint_batch':number,'policy_identity':identity,'tasks':57,
        'successes':sum(x['success'] for x in results),'task_goal_completion':sum(x['success'] for x in results)/57,
        'macro_test_pass_fraction':sum(x['num_passes']/x['num_tests'] for x in results)/57,
        'student_without_feedback':True,'temperature':cfg['evaluation']['temperature'],'seed':cfg['evaluation']['seed'],
        'results':sorted(results,key=lambda x:x['task_id'])}
    write_json(folder/'summary.json',summary)
    return summary


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--arm',choices=['mixed','sft','sdpo'],default='sdpo')
    parser.add_argument('--batch',type=int,choices=[18,36],default=36)
    args=parser.parse_args();main(args.arm,args.batch)
