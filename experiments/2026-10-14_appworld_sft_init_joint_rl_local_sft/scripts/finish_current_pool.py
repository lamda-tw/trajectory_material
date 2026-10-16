"""Adopt the existing GPU1 trainer, finish its ONE pool, export its LoRA, and exit.
No baseline, second training pass, fallback candidate, evaluation, or later round is launched.
"""
from pathlib import Path
import argparse,fcntl,json,os,re,shutil,signal,subprocess,sys,time,traceback,hashlib
from common import ROOT,WORKSPACE,read,dump,sha,require,now
from owned_process import birth
from round_data import schedule
RUN=ROOT/'runtime/round1_run'
CONTROL=ROOT/'runtime/finish_current_pool.json'
P=WORKSPACE/'plans/2026-10-13_appworld_sft_init_local_sft_online_rl'
LORA_PARAMETERS=21823488

def is_alive(pid,start):
    if birth(pid)!=start:return False
    try:return Path(f'/proc/{pid}/stat').read_text().rsplit(')',1)[1].split()[0]!='Z'
    except FileNotFoundError:return False

def check_owned(pid,start,argv,gpu_uuid):
    require(is_alive(pid,start),'Recorded trainer is no longer alive')
    actual=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    command=[x.decode() for x in actual if x]
    # The GPU launcher has exec'd the inner Python command by the time we adopt it.
    expected=argv[argv.index('--')+1:]
    require(command==expected,'PID no longer runs the recorded trainer command')
    env=dict(x.split(b'=',1) for x in Path(f'/proc/{pid}/environ').read_bytes().split(b'\0') if b'=' in x)
    require(env.get(b'CUDA_VISIBLE_DEVICES')==gpu_uuid.encode(),'Trainer no longer pinned to GPU1 UUID')

def checkpoints(output):
    return sorted(p for p in Path(output).glob('step_*') if re.fullmatch(r'step_\d{5}',p.name) and (p/'manifest.json').exists())

def check_inputs(control):
    require(sha(control['config'])==control['config_sha256'],'Running configuration changed')
    require(sha(control['pool'])==control['pool_sha256'],'Input pool changed')
    for name,expected in control['training_code_sha256'].items():require(sha(ROOT/name)==expected,'Training implementation changed: '+name)
    cfg=read(control['config'])
    require(sha(Path(cfg['model']['initial_adapter'])/'adapter_model.safetensors')==cfg['model']['adapter_weights_sha256'],'Original SFT LoRA changed')
    return cfg

def status(phase,control,**details):
    live=read(ROOT/'STATUS.json');count=len(checkpoints(control['output']))
    live.update(updated_at=now(),phase=phase,pipeline_pid=os.getpid(),physical_gpu_indices=[1],
      training_started=count>0,formal_training_started=False,formal_optimizer_updates=0,
      actual_optimizer_updates=count,current_round=1,current_round_committed_batches=count,current_round_total_batches=15,
      active_training_output=control['output'],active_log=control['training_log'],
      scope='Finish the existing 15-batch single pool, keep its LoRA and stop; user amended scope 2026-10-15',
      stop_after_current_pool=True,repeat_training=False,evaluation_scheduled=False,next_round_scheduled=False,
      next_step='save_current_pool_final_adapter_then_exit',last_heartbeat=now(),**details)
    dump(ROOT/'STATUS.json',live);dump(RUN/'status.json',{'at':now(),'phase':phase,**details})

def document(phase,body):
    text=f'# 第一轮执行记录\n\n更新时间：{now()}（北京时间）。\n\n状态：{phase}\n\n{body}\n\n当前范围：完成正在运行的15批单池训练，保存模型后结束。不再从A0重复训练，不启动DEV57或后续轮次。参数、学习率与数据保持当前运行配置。仅物理GPU1。\n\n当前训练文件仍位于 smoke/full_pool_15，保留历史 smoke 标签以忠实记录来源；其 checkpoint 是真实更新后的 LoRA。\n'
    for base in [ROOT,P]:(base/'ROUND_01_RUN.md').write_text(text)

def audit_and_export(control):
    cfg=check_inputs(control);out=Path(control['output']);pool=read(control['pool']);data=read(ROOT/'data/data_manifest.json')
    rows=schedule(cfg,pool['tasks'],len(data['samples']),1);n=len(rows)
    require(n==15,'The requested current run must remain 15 batches')
    found=checkpoints(out);require([p.name for p in found]==[f"step_{r['global_update']:05d}" for r in rows],'Incomplete round: do not export a partial model as final')
    expected_identity=hashlib.sha256(json.dumps({'config':control['config_sha256'],'data':sha(ROOT/'data/data_manifest.json'),'mode':'smoke'},sort_keys=True,separators=(',',':')).encode()).hexdigest()
    sft=[];rl=[];sft_tokens=0;rl_tokens=0;metrics=[]
    for row,checkpoint in zip(rows,found):
        m=read(checkpoint/'manifest.json')
        for name,expected in m['files'].items():require(sha(checkpoint/name)==expected,'Checkpoint file corrupted: '+str(checkpoint/name))
        require(sha(checkpoint/'adapter_model.safetensors')==m['adapter_sha256'],'Adapter checksum mismatch')
        s=m['state'];require(s['identity']==expected_identity and s['mode']=='smoke' and s['round']==1,'Unexpected checkpoint provenance')
        require(s['batch']==row['batch'] and s['global_update']==row['global_update'],'Update sequence changed')
        require(s['sft_indices']==row['sft_indices'] and s['task_ids']==row['tasks'],'Data schedule changed')
        require(s['pool_sha256']==control['pool_sha256'],'Checkpoint refers to another pool')
        require(s['metrics']['optimizer_steps_this_batch']==1,'More than one update in a batch')
        sft+=s['sft_indices'];rl+=s['trajectory_ids'];sft_tokens+=s['metrics']['sft_tokens'];rl_tokens+=s['metrics']['rl_tokens'];metrics.append(s['metrics'])
    require(sorted(sft)==list(range(2623)) and sft_tokens==205238,'SFT single-pass budget mismatch')
    require(len(rl)==540 and set(rl)=={f"{e['task_id']}__{e['sample']:02d}" for e in pool['episodes']},'RL single-pass budget mismatch')
    require(rl_tokens==sum(e['tokens'] for e in pool['episodes']),'RL token budget mismatch')
    # Verify source integrity without allocating a GPU.
    for e in pool['episodes']:require(sha(e['trajectory'])==e['sha256'],'Original rollout changed')
    for row in data['samples']:require(sha(ROOT/row['encoded_file'])==row['encoded_sha256'],'Encoded SFT sample changed')
    from safetensors.torch import load_file
    import torch
    final=found[-1];weights=load_file(str(final/'adapter_model.safetensors'),device='cpu')
    original=load_file(str(Path(cfg['model']['initial_adapter'])/'adapter_model.safetensors'),device='cpu')
    require(set(weights)==set(original),'Final adapter parameter keys changed')
    require(sum(v.numel() for v in weights.values())==LORA_PARAMETERS,'Final LoRA size changed')
    require(all(bool(torch.isfinite(v).all()) for v in weights.values()),'Nonfinite final adapter')
    difference=max(float((weights[k].float()-original[k].float()).abs().max()) for k in weights)
    require(difference>0,'Final adapter has not changed from A0')
    alignment=read(out/'alignment.json');require(alignment['passed'],'Initial backend alignment failed')
    probe=read(out/'final_policy_probe.json') if (out/'final_policy_probe.json').exists() else None
    # A final probe does not mutate the already committed model. Report a failure honestly,
    # but do not discard a valid completed checkpoint or start another run to find a better one.
    report={'at':now(),'passed':True,'scope':'budget/integrity/finite-weights checks; no DEV57 quality claim',
      'origin_mode':'smoke','user_requested_artifact':'one complete pool trained from the existing 90-trajectory SFT LoRA',
      'optimizer_updates':15,'rl_trajectories':540,'rl_generated_tokens':rl_tokens,'sft_steps':2623,'sft_tokens':sft_tokens,
      'base_model':cfg['model']['base'],'initial_adapter_sha256':cfg['model']['adapter_weights_sha256'],
      'checkpoint':str(final),'adapter_sha256':sha(final/'adapter_model.safetensors'),'lora_parameters':LORA_PARAMETERS,
      'maximum_parameter_change_from_A0':difference,'final_policy_probe_passed':probe['passed'] if probe else None,
      'DEV57_performed':False,'repeated_training':False,'next_round_launched':False,'physical_gpu_indices':[1],
      'learning_rate_schedule':'Original 75-update schedule preserved; this artifact stops after update 15. No retrospective rescheduling.',
      'config_sha256':control['config_sha256'],'metrics':metrics}
    dump(out/'single_pool_audit.json',report)
    destination=Path(control['final_adapter'])
    if destination.exists():
        require(read(destination/'provenance.json')['adapter_sha256']==report['adapter_sha256'],'Existing exported model has different provenance')
        require(sha(destination/'adapter_model.safetensors')==report['adapter_sha256'],'Existing exported adapter changed')
        require(sha(destination/'adapter_config.json')==sha(final/'adapter_config.json'),'Existing exported adapter config changed')
    else:
        temp=destination.with_name(destination.name+'.incomplete');temp.mkdir(parents=True,exist_ok=True)
        for name in ['adapter_model.safetensors','adapter_config.json']:shutil.copyfile(final/name,temp/name)
        shutil.copyfile(control['config'],temp/'training_config_used.json')
        dump(temp/'provenance.json',report)
        (temp/'README.md').write_text(f'# 第一轮最终 LoRA\n\n基座：{cfg["model"]["base"]}\n\n加载本目录的 adapter_model.safetensors 和 adapter_config.json 即可在原基座上使用。仅 LoRA，无全量基座合并。\n\n来源：{final}\n\n已完成15次联合更新、540条RL轨迹与2623个SFT步骤各一遍。未执行DEV57，不声称评测效果。完整optimizer/RNG保留在来源checkpoint的resume.pt。\n')
        require(sha(temp/'adapter_model.safetensors')==report['adapter_sha256'],'Export checksum mismatch')
        for f in temp.iterdir():
            if f.is_file():
                with f.open('rb') as handle:os.fsync(handle.fileno())
        os.rename(temp,destination)
        fd=os.open(str(destination.parent),os.O_RDONLY);os.fsync(fd);os.close(fd)
    final_report={k:v for k,v in report.items() if k!='metrics'}|{'final_adapter':str(destination)}
    dump(ROOT/'ROUND_01_COMPLETE.json',final_report);dump(P/'ROUND_01_COMPLETE.json',final_report)
    return final_report

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');a=ap.parse_args();require(a.execute,'Explicit --execute required')
    control=read(CONTROL);cfg=check_inputs(control);RUN.mkdir(parents=True,exist_ok=True)
    lock=open(RUN/'pipeline.lock','a+')
    try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Another supervisor is still active')
    dump(RUN/'supervisor.json',{'at':now(),'pid':os.getpid(),'scope':'Finish current 15-batch pool, export adapter, then exit','trainer_adopted':control['trainer_pid']})
    pid=control['trainer_pid'];start=control['trainer_start_ticks'];out=Path(control['output']);child=None;restarts=0;launch_time=time.time()
    def terminate(signum,frame):raise KeyboardInterrupt('Finish-current-pool supervisor stopped')
    signal.signal(signal.SIGTERM,terminate)
    try:
        if is_alive(pid,start):check_owned(pid,start,control['launcher_argv'],cfg['resource_constraints']['physical_gpu_uuid'])
        document('完成当前单轮后保存模型并结束',f'已接管原训练进程 PID {pid}，无参数重置。模型将导出到 {control["final_adapter"]}。')
        while True:
            if not is_alive(pid,start):
                if child is not None:child.wait();child=None
                if len(checkpoints(out))==15:
                    status('round01_model_export',control);report=audit_and_export(control)
                    document('第一轮模型已保存，运行结束',f'已完成15批，模型：{report["final_adapter"]}。SHA-256：{report["adapter_sha256"]}。预算与权重检查通过，未进行DEV57。')
                    status('round01_model_complete',control,final_adapter=report['final_adapter'],next_step_override='none',run_finished=True)
                    live=read(ROOT/'STATUS.json');live['next_step']='none';dump(ROOT/'STATUS.json',live)
                    dump(RUN/'heartbeat.json',{'at':now(),'stage':'round01_model_complete','child_pid':None,'run_finished':True})
                    return
                if (out/'drift_rejected.json').exists():raise RuntimeError('Numerical drift gate stopped the run; retain last valid checkpoint and do not start fallback/retraining')
                if (out/'alignment.json').exists():require(read(out/'alignment.json')['passed'],'Backend alignment failure')
                log=Path(control['training_log']).read_text(errors='replace')[-16000:]
                require(not any(x in log for x in ['Nonfinite','checksum mismatch','Initial adapter changed','OutOfMemoryError']),'Non-transient trainer failure; preserve evidence')
                require(restarts<3,'Infrastructure resume attempts exhausted')
                check_inputs(control);require(shutil.disk_usage(ROOT).free>4*2**30,'Insufficient disk space to resume')
                with Path(control['training_log']).open('a') as stream:
                    stream.write('\n'+json.dumps({'at':now(),'resume_attempt':restarts+1,'scope':'continue same checkpoint/config; not retrain from A0'})+'\n');stream.flush()
                    child=subprocess.Popen(control['launcher_argv'],cwd=ROOT,stdin=subprocess.DEVNULL,stdout=stream,stderr=subprocess.STDOUT,start_new_session=True,
                        env={**os.environ,'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','TOKENIZERS_PARALLELISM':'false'})
                pid=child.pid;start=birth(pid);restarts+=1;launch_time=time.time()
                dump(RUN/'child.json',{'at':now(),'pid':pid,'start_ticks':start,'stage':'finish_current_pool','argv':control['launcher_argv']})
                control.update(trainer_pid=pid,trainer_start_ticks=start);dump(CONTROL,control)
            status('finish_current_pool',control,resume_attempts=restarts)
            stamps=[p.stat().st_mtime for p in [out/'progress.json',ROOT/'cache/round_01_A0_reference/progress.json'] if p.exists()]
            stamps.extend(p.stat().st_mtime for p in (out/'diagnostics').glob('*.json'))
            age=time.time()-max([launch_time]+stamps)
            dump(RUN/'heartbeat.json',{'at':now(),'stage':'finish_current_pool','child_pid':pid,'last_progress_age_seconds':age,'resume_attempts':restarts})
            if age>2400 or shutil.disk_usage(ROOT).free<2*2**30:
                check_owned(pid,start,control['launcher_argv'],cfg['resource_constraints']['physical_gpu_uuid'])
                os.kill(pid,signal.SIGTERM)
                time.sleep(10)
                if is_alive(pid,start):os.kill(pid,signal.SIGKILL)
                require(shutil.disk_usage(ROOT).free>=2*2**30,'Low disk; stopped own trainer safely')
            time.sleep(20)
    except BaseException as error:
        dump(RUN/'ERROR.json',{'at':now(),'error':repr(error),'traceback':traceback.format_exc(),'scope':'current pool only'})
        status('current_pool_error',control,error=repr(error))
        document('当前单轮运行异常',f'{error!r}。已提交checkpoint保留；不会启动第二遍训练。')
        raise
if __name__=='__main__':main()
