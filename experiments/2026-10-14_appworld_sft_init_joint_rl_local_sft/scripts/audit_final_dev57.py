"""CPU-only independent artifact checks after the final model's DEV57 run."""
import argparse
import collections
import csv
import math
from pathlib import Path
from common import ROOT, read, dump, require, sha, now
from collection_protocol import collection_fingerprint
from owned_process import birth


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args();require(args.execute,'Pass --execute to write the audit')
    out=ROOT/'evaluation/round_01_final'
    summary=read(out/'SUMMARY.json');complete=read(ROOT/'DEV57_COMPLETE.json')
    training=read(ROOT/'ROUND_01_COMPLETE.json');config=read(out/'evaluation_config.json')
    inputs=read(out/'INPUT_MANIFEST.json');tasks=(ROOT/'config/dev57.txt').read_text().split()
    require(len(tasks)==57 and len(set(tasks))==57,'Wrong DEV57 coverage')
    require(not set(tasks)&set((ROOT/'config/train90.txt').read_text().split()),'Train/dev overlap')
    require(read(out/'STATUS.json')['phase']=='complete','Evaluation has not finished')
    require(complete['summary_sha256']==sha(out/'SUMMARY.json'),'Summary checksum changed')
    require(inputs['training_completion_sha256']==sha(ROOT/'ROUND_01_COMPLETE.json'),'Training completion changed')
    require(inputs['config_sha256']==sha(out/'evaluation_config.json'),'Evaluation config changed')
    require(inputs['tasks_sha256']==sha(ROOT/'config/dev57.txt'),'Task list changed')
    require(inputs['prompt_sha256']==sha(ROOT/config['agent']['prompt']),'Agent prompt changed')
    for path,expected in inputs['code_sha256'].items():require(sha(ROOT/path)==expected,'Evaluation code changed: '+path)
    weight_hash=sha(Path(training['final_adapter'])/'adapter_model.safetensors')
    require(weight_hash==training['adapter_sha256']==inputs['adapter_sha256']==summary['adapter_sha256'],'Model identity changed')
    require(config['evaluation']['temperature']==0 and config['agent']=={
        'prompt':'assets/agent_prompt.txt','max_steps':50,'max_model_len':32000,'max_new_tokens':3000},'Evaluation protocol mismatch')
    require(config['server']['gpu']==read(ROOT/'config/resource_policy.json')['physical_gpu_uuid'],'Wrong GPU policy')
    rows=summary['results'];require([row['task_id'] for row in rows]==tasks,'Missing, repeated or reordered tasks')
    require(read(out/'task_results.json')==rows,'Incremental and final results differ')
    with (out/'task_results.csv').open(newline='') as handle:csv_rows=list(csv.DictReader(handle))
    require([row['task_id'] for row in csv_rows]==tasks,'CSV coverage mismatch')
    counts=collections.Counter();tokens=steps=successes=0
    for row,csv_row in zip(rows,csv_rows):
        path=out/'trajectories'/f"{row['task_id']}.json"
        require(Path(row['source']).resolve()==path.resolve() and path.resolve().is_relative_to(ROOT),'Trajectory outside experiment')
        require(sha(path)==row['sha256'],'Trajectory checksum mismatch')
        d=read(path);job=d['job'];evaluation=d['official_evaluation']
        require(job['task_id']==row['task_id'] and job['mode']=='dev' and job['sample']==0 and job['seed']==100,'Wrong job identity')
        require(job['policy_id']=='adapter:'+weight_hash and job['model']=='joint-eval-policy','Wrong sampled policy')
        require(job['fingerprint']==collection_fingerprint(config),'Wrong generation configuration')
        require(evaluation['num_tests']>0 and evaluation['num_passes']+evaluation['num_failures']==evaluation['num_tests'],'Invalid official test counts')
        require(type(evaluation['success']) is bool and evaluation['success']==row['success'],'Official success mismatch')
        require(row['passes']==evaluation['num_passes'] and row['tests']==evaluation['num_tests'],'Summary test counts mismatch')
        require(len(d['steps'])==row['steps']<=50 and d['termination']==row['termination'],'Step/termination mismatch')
        count=0
        for step in d['steps']:
            p,r,lp=step['prompt_ids'],step['response_ids'],step['old_logprobs']
            require(p and r and len(r)==len(lp) and all(math.isfinite(v) for v in lp),'Invalid token/probability record')
            require(len(p)+len(r)<=32000 and len(r)<=3000,'Generation budget exceeded')
            count+=len(r)
        require(count==row['generated_tokens'],'Generated token count mismatch')
        require(csv_row['success']==str(row['success']) and int(csv_row['steps'])==row['steps'],'CSV result mismatch')
        successes+=row['success'];tokens+=count;steps+=len(d['steps']);counts[d['termination']]+=1
    require(successes==summary['successes']==complete['successes'],'Success total mismatch')
    require(summary['tasks']==57 and summary['TGC']==successes/57,'Wrong final denominator')
    require(not list((out/'trajectories').glob('*.partial.json')),'Unfinished trajectory remains')
    attempts=[read(p) for p in (out/'attempts').glob('*.json')]
    processes={}
    for name,path in [('evaluation',ROOT/'runtime/dev57_round_01_final_launch.json'),('server',out/'server/owned_process.json')]:
        process=read(path);processes[name]=birth(process['pid'])==process['start_ticks']
    report={'at':now(),'passed':True,'tasks':57,'successes':successes,'failures':57-successes,'TGC':successes/57,
            'generated_tokens':tokens,'total_steps':steps,'termination_counts':dict(counts),
            'worker_attempts':len(attempts),'infrastructure_failed_attempts':sum(a['returncode']!=0 for a in attempts),
            'adapter_sha256':weight_hash,'model_unchanged':True,'input_code_hashes_verified':True,
            'all_results_within_existing_experiment':True,'physical_gpu_indices':[1],
            'owned_processes_still_present':processes,'cuda_allocations_by_audit':0,
            'summary_sha256':sha(out/'SUMMARY.json')}
    dump(ROOT/'checks/dev57_final_audit.json',report)
    print(__import__('json').dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
