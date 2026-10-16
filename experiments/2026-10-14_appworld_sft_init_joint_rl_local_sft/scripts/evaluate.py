"""Fresh DEV57 evaluation of A0 or an audited round-1 adapter; no training."""
from pathlib import Path
import argparse, concurrent.futures, csv, io, json, os, signal, subprocess, time
from common import ROOT, read, dump, sha, require, now
from collection_protocol import collection_fingerprint
from policy_server import owned_server

def validate_freeze():
    freeze=read(ROOT/'FREEZE.json')
    require(sha(ROOT/'config/training_config.json')==freeze['training_config_sha256'],'Frozen config changed')
    for filename,expected in freeze['files'].items():require(sha(ROOT/filename)==expected,'Frozen artifact changed: '+filename)
    return read(ROOT/'config/training_config.json')

def validate_completed_adapter(adapter):
    """Validate the user-retained trial model without fabricating a formal freeze."""
    completion=read(ROOT/'ROUND_01_COMPLETE.json')
    require(completion['passed'] and completion['optimizer_updates']==15,'Completed 15-update pool required')
    require(completion['rl_trajectories']==540 and completion['sft_steps']==2623,'Wrong completed data budget')
    require(adapter.resolve()==Path(completion['final_adapter']).resolve(),'Expected the exported final adapter')
    provenance=read(adapter/'provenance.json')
    for key in ['adapter_sha256','config_sha256','initial_adapter_sha256','checkpoint','optimizer_updates']:
        require(provenance[key]==completion[key],'Model provenance mismatch: '+key)
    require(sha(adapter/'adapter_model.safetensors')==completion['adapter_sha256'],'Final adapter checksum mismatch')
    config_path=adapter/'training_config_used.json'
    require(sha(config_path)==completion['config_sha256'],'Actual training config changed')
    active=read(config_path)
    require(active['model']['adapter_weights_sha256']==completion['initial_adapter_sha256'],'Wrong SFT initialization')
    checkpoint=Path(completion['checkpoint']);manifest=read(checkpoint/'manifest.json')
    require(manifest['adapter_sha256']==completion['adapter_sha256'],'Source checkpoint identity mismatch')
    for name,expected in manifest['files'].items():
        require(sha(checkpoint/name)==expected,'Source checkpoint checksum mismatch: '+name)
    require(sha(adapter/'adapter_config.json')==sha(checkpoint/'adapter_config.json'),'Exported LoRA config changed')
    state=manifest['state']
    require(state['round']==1 and state['batch']==15 and state['global_update']==15,'Wrong final update')
    require(active['resource_constraints']['physical_gpu_uuid']==read(ROOT/'config/resource_policy.json')['physical_gpu_uuid'],'GPU policy mismatch')
    return active,{'training_completion_sha256':sha(ROOT/'ROUND_01_COMPLETE.json'),
                   'training_config_sha256':completion['config_sha256'],
                   'source_checkpoint':str(checkpoint),'source_mode':state['mode'],
                   'training_optimizer_updates':15,'freeze_sha256':None}

def write_readable_results(out,tasks,records,phase,weight_hash):
    """Stable human-readable entrypoint, including pending tasks during execution."""
    rows=[records[t] for t in tasks if t in records];successes=sum(r['success'] for r in rows)
    score=f'{successes}/57 = {successes/57:.2%}' if len(rows)==57 else f'已完成题中成功 {successes}/{len(rows)}；全量成绩待57题完成'
    lines=['# 第一轮最终 LoRA：DEV57 评测', '',f'更新时间：{now()}', '',
           f'状态：{phase}；进度：{len(rows)}/57；{score}。', '',
           '协议：每题1条轨迹，temperature=0，seed=100，最多50步，每动作最多3000 token，上下文32000，thinking=False。仅物理GPU1。', '',
           f'模型 SHA-256：`{weight_hash}`。', '',
           '官方任务失败计入分母；仅基础设施故障重试。此次没有运行初始模型对照，不据此声称相对提升。', '',
           '| 题目 | 官方成功 | 测试通过数 | 步数 | 结束原因 | 生成token |',
           '| --- | --- | --- | ---: | --- | ---: |']
    for task in tasks:
        r=records.get(task)
        if r:lines.append(f"| [{task}](trajectories/{task}.json) | {'PASS' if r['success'] else 'FAIL'} | {r['passes']}/{r['tests']} | {r['steps']} | {r['termination']} | {r['generated_tokens']} |")
        else:lines.append(f'| {task} | 待完成 | — | — | — | — |')
    temp=out/'RESULTS.md.tmp';temp.write_text('\n'.join(lines)+'\n');os.replace(temp,out/'RESULTS.md')
    content=io.StringIO();writer=csv.DictWriter(content,fieldnames=['task_id','success','passes','tests','steps','termination','generated_tokens','source','sha256'])
    writer.writeheader();writer.writerows(rows)
    temp=out/'task_results.csv.tmp';temp.write_text(content.getvalue());os.replace(temp,out/'task_results.csv')

def evaluation_config(active,weight_hash,label):
    return {'paths':{'base_model':active['model']['base'],'vllm_python':'/root/autodl-tmp/envs/qwen3-vllm-py312/bin/python'},
      'server':{'host':'127.0.0.1','port':8147,'gpu':active['resource_constraints']['physical_gpu_uuid'],
        'model_name':'joint-qwen3-8b','adapter_name':'joint-eval-policy','gpu_memory_utilization':.80,
        'max_num_seqs':6,'minimum_free_gpu_gib':70,'startup_timeout_seconds':900,'request_timeout_seconds':600},
      'agent':{'prompt':'assets/agent_prompt.txt','max_steps':active['evaluation_candidate']['max_steps'],
        'max_model_len':active['evaluation_candidate']['max_model_len'],'max_new_tokens':active['evaluation_candidate']['max_new_tokens_per_action']},
      'sampling':{'temperature':1.0,'group_size':1},'evaluation':{'temperature':active['evaluation_candidate']['temperature'],'tasks':'config/dev57.txt'},
      'training':{'lora':{'r':8}},'adapter_sha256':weight_hash,'label':label,
      'mode':'completed_pool_evaluation' if label=='round_01_final' else 'formal_evaluation'}

def compact(job,d):
    require(d['job']==job,'Evaluation job mismatch')
    e=d['official_evaluation'];require(type(e['success']) is bool and e['num_tests']>0,'Invalid official evaluation')
    return {'task_id':job['task_id'],'success':e['success'],'passes':e['num_passes'],'tests':e['num_tests'],
      'steps':len(d['steps']),'termination':d['termination'],'generated_tokens':sum(len(s['response_ids']) for s in d['steps']),
      'source':job['output'],'sha256':sha(job['output'])}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--label',choices=['initial','round_01','round_01_final'],required=True)
    ap.add_argument('--adapter',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    require(a.execute,'Explicit --execute required');adapter=a.adapter.resolve()
    if a.label=='round_01_final':active,source=validate_completed_adapter(adapter)
    else:active=validate_freeze();source={'freeze_sha256':sha(ROOT/'FREEZE.json')}
    require(os.environ.get('CUDA_VISIBLE_DEVICES')==active['resource_constraints']['physical_gpu_uuid'],'Use GPU1 launcher')
    weight_hash=sha(adapter/'adapter_model.safetensors')
    if a.label=='initial':require(weight_hash==active['model']['adapter_weights_sha256'],'Baseline must be A0')
    elif a.label=='round_01':
        from joint_core import verify_checkpoint
        m=verify_checkpoint(adapter);s=m['state']
        require(s['mode']=='formal' and s['round']==1 and s['batch']==active['schedule_candidate']['batches_per_round'],'Round 1 is incomplete')
    out=ROOT/'evaluation'/a.label;out.mkdir(parents=True,exist_ok=True)
    cfg=evaluation_config(active,weight_hash,a.label)
    config_path=out/'evaluation_config.json'
    if config_path.exists():require(read(config_path)==cfg,'Evaluation protocol changed on resume')
    else:dump(config_path,cfg)
    fingerprint=collection_fingerprint(cfg);tasks=(ROOT/'config/dev57.txt').read_text().split()
    require(len(tasks)==57 and len(set(tasks))==57,'Expected exact DEV57')
    require(not set(tasks)&set((ROOT/'config/train90.txt').read_text().split()),'Evaluation/training overlap')
    identity={**source,'adapter_sha256':weight_hash,'config_sha256':sha(config_path),
              'tasks_sha256':sha(ROOT/'config/dev57.txt'),'prompt_sha256':sha(ROOT/cfg['agent']['prompt']),
              'code_sha256':{p:sha(ROOT/p) for p in ['scripts/evaluate.py','scripts/rollout_worker.py','scripts/collection_protocol.py',
                           'scripts/policy_server.py','scripts/appworld_log_compat.py','scripts/gpu1_run.py']}}
    if (out/'INPUT_MANIFEST.json').exists():require(read(out/'INPUT_MANIFEST.json')==identity,'Evaluation inputs changed on resume')
    else:dump(out/'INPUT_MANIFEST.json',identity)
    records={};jobs=[];start=time.monotonic()
    for task in tasks:
        job={'mode':'dev','task_id':task,'sample':0,'seed':active['evaluation_candidate']['seed'],'update':0,
          'episode_id':f'joint_{a.label}_{fingerprint[:12]}_{task}','runtime_name':'appworld',
          'model':'joint-eval-policy','output':str(out/'trajectories'/f'{task}.json'),'fingerprint':fingerprint,'policy_id':'adapter:'+weight_hash}
        if Path(job['output']).exists():records[task]=compact(job,read(job['output']))
        else:jobs.append(job)
    def status(phase):
        dump(out/'STATUS.json',{'at':now(),'phase':phase,'tasks_done':len(records),'total':57,
          'successes':sum(x['success'] for x in records.values()),'elapsed_invocation_seconds':time.monotonic()-start,
          'pid':os.getpid(),'physical_gpu_indices':[1],'adapter':str(adapter)})
        write_readable_results(out,tasks,records,phase,weight_hash)
    env={**os.environ,'JOINT_COLLECTION_CONFIG':str(config_path),'OMP_NUM_THREADS':'1','MKL_NUM_THREADS':'1','PYTHONUNBUFFERED':'1'}
    def worker(job):
        path=out/'jobs'/f"{job['task_id']}.json";dump(path,job);logpath=path.with_suffix('.log')
        for attempt in range(1,4):
            with logpath.open('a') as log:
                p=subprocess.Popen(['/root/autodl-tmp/envs/appworld-0.2.0-py312/bin/python','-u',str(ROOT/'scripts/rollout_worker.py'),
                  '--job',str(path),'--execute'],env=env,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                from owned_process import record
                record(path.with_suffix('.process.json'),p.pid,p.args)
                try:code=p.wait(timeout=33000)
                except subprocess.TimeoutExpired:
                    os.killpg(p.pid,signal.SIGTERM)
                    try:p.wait(timeout=10)
                    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
                    code=124
            dump(out/'attempts'/f"{job['task_id']}_{time.time_ns()}.json",{'at':now(),'returncode':code,'attempt':attempt})
            if code==0:return compact(job,read(job['output']))
        raise RuntimeError('Infrastructure failure after 3 attempts: '+str(logpath))
    status('starting_server')
    try:
        if jobs:
            with owned_server(cfg,out/'server',adapter):
                status('running')
                with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
                    futures=[ex.submit(worker,j) for j in jobs]
                    for f in concurrent.futures.as_completed(futures):
                        row=f.result();records[row['task_id']]=row;status('running')
                        dump(out/'task_results.json',[records[t] for t in tasks if t in records])
                        print(json.dumps({'at':now(),'label':a.label,'completed':len(records),'task':row['task_id'],'success':row['success']}),flush=True)
        require(len(records)==57,'Incomplete DEV57');require(sha(adapter/'adapter_model.safetensors')==weight_hash,'Evaluation adapter mutated')
        rows=[records[t] for t in tasks];successes=sum(x['success'] for x in rows)
        report={'at':now(),'passed':True,'label':a.label,'tasks':57,'successes':successes,'TGC':successes/57,
          'adapter_sha256':weight_hash,'config_sha256':sha(config_path),**source,'results':rows,
          'physical_gpu_indices':[1],'split':'DEV57','trajectories_per_task':1,'temperature':cfg['evaluation']['temperature']}
        dump(out/'SUMMARY.json',report)
        dump(out/('baseline_complete.json' if a.label=='initial' else 'evaluation_complete.json'),
          {k:v for k,v in report.items() if k!='results'}|{'summary_sha256':sha(out/'SUMMARY.json')})
        status('complete')
        if a.label=='round_01_final':
            dump(ROOT/'DEV57_COMPLETE.json',{k:v for k,v in report.items() if k!='results'}|
                 {'summary':str(out/'SUMMARY.json'),'readable_results':str(out/'RESULTS.md'),
                  'summary_sha256':sha(out/'SUMMARY.json')})
            print(json.dumps({'at':now(),'phase':'complete','successes':successes,'tasks':57,'TGC':successes/57}),flush=True)
    except BaseException as error:
        status('error');dump(out/'ERROR.json',{'at':now(),'error':repr(error)});raise
if __name__=='__main__':main()
