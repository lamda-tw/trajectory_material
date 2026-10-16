"""Authorized unattended chain: whole-pool trial -> freeze -> A0 DEV57 -> formal round 1 -> A1 DEV57.
No rounds 2-5 are launched by this entrypoint. Resume repeats only uncommitted work.
"""
from pathlib import Path
import argparse, copy, fcntl, json, os, re, shutil, signal, subprocess, sys, time, traceback
from common import ROOT, WORKSPACE, read, dump, sha, require, now, jsonl
from round_data import schedule
TRAIN=str(WORKSPACE/'.conda-training/bin/python')
POOL=ROOT/'rollout/round_01/pool.json'
REF=ROOT/'cache/round_01_A0_reference'
P=WORKSPACE/'plans/2026-10-13_appworld_sft_init_local_sft_online_rl'
RUN=ROOT/'runtime/round1_run'

def update_status(phase,**details):
    previous=read(ROOT/'STATUS.json')
    n=len(list((ROOT/'training/round_01').glob('step_[0-9][0-9][0-9][0-9][0-9]/manifest.json')))
    previous.update(updated_at=now(),phase=phase,pipeline_pid=os.getpid(),physical_gpu_indices=[1],
                    formal_optimizer_updates=n,training_started=n>0,**details)
    dump(ROOT/'STATUS.json',previous);dump(RUN/'status.json',{'at':now(),'phase':phase,**details})
    print(json.dumps({'at':now(),'phase':phase,**details},ensure_ascii=False),flush=True)

def locked_run():
    RUN.mkdir(parents=True,exist_ok=True);f=open(RUN/'pipeline.lock','a+')
    try:fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:raise RuntimeError('Round-1 supervisor already running')
    return f

def stop_child(p):
    if p.poll() is not None:return
    os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=45)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()

def run_stage(name,argv,progress_paths,output=None,attempts=3):
    """Owned GPU process group, bounded infrastructure retries, durable last-checkpoint resume."""
    logpath=ROOT/'logs'/f'{name}.log';logpath.parent.mkdir(exist_ok=True)
    for attempt in range(1,attempts+1):
        # 12 GiB reserve covers a complete 15-update round plus its trial and evaluations.
        require(shutil.disk_usage(ROOT).free>=12*2**30,'Insufficient disk reserve before GPU stage')
        update_status(name,stage_attempt=attempt,active_log=str(logpath),active_progress=[str(x) for x in progress_paths])
        cmd=[sys.executable,str(ROOT/'scripts/gpu1_run.py'),'--',*map(str,argv)]
        with (ROOT/'commands.jsonl').open('a') as f:f.write(json.dumps({'at':now(),'stage':name,'argv':cmd})+'\n')
        env={**os.environ,'PYTHONUNBUFFERED':'1','OMP_NUM_THREADS':'4','MKL_NUM_THREADS':'4','TOKENIZERS_PARALLELISM':'false'}
        with logpath.open('a') as log:
            log.write('\n'+json.dumps({'at':now(),'attempt':attempt,'argv':cmd})+'\n');log.flush()
            process=subprocess.Popen(cmd,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
            dump(RUN/'child.json',{'at':now(),'pid':process.pid,'stage':name,'argv':cmd})
            start=time.time();failure=None
            try:
                while process.poll() is None:
                    dynamic=list(progress_paths)
                    for x in progress_paths:
                        dynamic.extend(x.parent.glob('trajectories/*.partial.json'))
                        dynamic.extend(x.parent.glob('diagnostics/*.json'))
                    stamps=[x.stat().st_mtime for x in dynamic if x.exists()]
                    recent=max([start]+stamps)
                    # 40 min idle bound: each individual action should complete well within this.
                    if time.time()-recent>2400:failure='no progress for 40 minutes';break
                    if shutil.disk_usage(ROOT).free<4*2**30:failure='disk reserve below 4 GiB';break
                    dump(RUN/'heartbeat.json',{'at':now(),'stage':name,'child_pid':process.pid,
                      'last_progress_age_seconds':time.time()-recent,'elapsed_seconds':time.time()-start})
                    # The root status reflects committed updates while a trainer is still running.
                    live=read(ROOT/'STATUS.json');count=len(list((ROOT/'training/round_01').glob('step_[0-9][0-9][0-9][0-9][0-9]/manifest.json')))
                    live.update(formal_optimizer_updates=count,training_started=count>0,last_heartbeat=now());dump(ROOT/'STATUS.json',live)
                    time.sleep(20)
            finally:
                stop_child(process)
                from owned_process import cleanup
                for x in progress_paths:
                    for owned in list(x.parent.glob('server/owned_process.json'))+list(x.parent.glob('jobs/*.process.json')):
                        cleanup(owned)
        code=process.returncode
        dump(RUN/'attempts'/f'{name}_{time.time_ns()}.json',{'at':now(),'returncode':code,'failure':failure,'attempt':attempt})
        if code==0 and failure is None:return
        if output and (output/'drift_rejected.json').exists():raise DriftRejected(str(output/'drift_rejected.json'))
        if output and (output/'final_policy_probe.json').exists() and not read(output/'final_policy_probe.json')['passed']:
            raise DriftRejected(str(output/'final_policy_probe.json'))
        if output and (output/'alignment.json').exists() and not read(output/'alignment.json')['passed']:
            raise RuntimeError('Backend mismatch: '+str(output/'alignment.json'))
        tail=logpath.read_text(errors='replace')[-20000:]
        if any(t in tail for t in ['Nonfinite','OutOfMemoryError','checksum mismatch','Frozen artifact changed','Traceback']) and not any(t in tail for t in ['ConnectionResetError','ConnectionRefusedError','TimeoutError','timed out','already owns GPU1']):
            raise RuntimeError('Non-transient failure; preserve all evidence: '+str(logpath))
        if attempt<attempts:time.sleep(60)
    raise RuntimeError('Infrastructure retries exhausted: '+str(logpath))

class DriftRejected(RuntimeError):pass

def audit_round(output,cfg,mode):
    from joint_core import verify_checkpoint
    rows=schedule(cfg,read(POOL)['tasks'],2623,1);expected={f"step_{r['global_update']:05d}" for r in rows}
    found={p.name for p in output.glob('step_*') if re.fullmatch(r'step_\d{5}',p.name) and (p/'manifest.json').exists()}
    require(found==expected,'Round checkpoint coverage mismatch')
    sft=[];trajectories=[];tokens=0;metrics=[]
    for row in rows:
        m=verify_checkpoint(output/f"step_{row['global_update']:05d}");s=m['state']
        require(s['mode']==mode and s['round']==1 and s['batch']==row['batch'],'Wrong committed state')
        require(s['sft_indices']==row['sft_indices'] and s['task_ids']==row['tasks'],'Committed schedule mismatch')
        require(s['pool_sha256']==sha(POOL),'Committed pool changed')
        sft.extend(s['sft_indices']);trajectories.extend(s['trajectory_ids']);tokens+=s['metrics']['sft_tokens'];metrics.append(s['metrics'])
    require(sorted(sft)==list(range(2623)),'SFT omission or repeat')
    expected_ids={f"{x['task_id']}__{x['sample']:02d}" for x in read(POOL)['episodes']}
    require(len(trajectories)==540 and set(trajectories)==expected_ids,'RL omission or repeat')
    require(tokens==205238,'SFT target-token budget mismatch')
    require(read(output/'alignment.json')['passed'] and read(output/'final_policy_probe.json')['passed'],'Policy gates incomplete')
    report={'at':now(),'passed':True,'mode':mode,'batches':len(rows),'rl_trajectories':540,'sft_steps':2623,'sft_tokens':tokens,
      'last_checkpoint':str(output/f"step_{rows[-1]['global_update']:05d}"),'peak_allocated_gib':max(x['peak_allocated_gib'] for x in metrics),
      'total_batch_seconds':sum(x['elapsed_seconds'] for x in metrics),'metrics':metrics}
    dump(output/'round_audit.json',report);return report

def freeze(chosen,trial):
    require(trial['passed'],'Cannot freeze an unvalidated trial')
    if (ROOT/'FREEZE.json').exists():
        from evaluate import validate_freeze
        return validate_freeze()
    cfg=copy.deepcopy(read(chosen));s=cfg['schedule_candidate'];n=s['batches_per_round']
    cfg['status']='frozen after full-pool GPU1 trial';cfg['scope']='Five-round design; this launch executes round 1 and its evaluation only.'
    s['batch_count_status']=f'frozen at {n} after complete 540-trajectory single-pass trial'
    cfg['optimizer_candidate']['rationale']='Engineering choice accepted by predeclared full-pool drift limits; no DEV tuning.'
    cfg['loss_candidate']['rationale']='Weights preserved through full-pool engineering validation; no DEV tuning.'
    cfg['preparation_actual']['training_started']=False
    cfg['must_measure_before_freeze']=[]
    cfg['freeze_evidence']={'trial_config':str(chosen),'trial_config_sha256':sha(chosen),'trial_audit':str(Path(trial['last_checkpoint']).parent/'round_audit.json'),
      'initial_weights_preserved':True,'formal_optimizer_reset':True,'selected_batch_count':n,'source_lora_continued':True}
    dump(ROOT/'config/training_config.json',cfg)
    data=read(ROOT/'data/data_manifest.json');rows=[]
    for r in range(1,6):
        for row in schedule(cfg,read(POOL)['tasks'],2623,r):
            row['sft_target_tokens']=sum(data['samples'][i]['target_tokens'] for i in row['sft_indices']);rows.append(row)
    require(sum(x['sft_target_tokens'] for x in rows)==1026190,'Frozen schedule budget mismatch')
    jsonl(ROOT/'data/sft_schedule_frozen.jsonl',rows)
    dump(ROOT/'config/config_decisions.json',{'at':now(),'batches_per_round':n,'learning_rate':cfg['optimizer_candidate']['learning_rate'],
      'sft_lambda':cfg['loss_candidate']['sft_lambda'],'kl_beta':cfg['loss_candidate']['kl_beta'],'selection_rule_unchanged':'P-F>=4',
      'selection_extra_filters':[],'DEV_used_for_selection':False,'trial_evidence':cfg['freeze_evidence']})
    paths=list((ROOT/'scripts').rglob('*.py'))+list((ROOT/'assets').glob('*'))
    paths += [ROOT/x for x in ['config/training_config.json','config/config_decisions.json','config/resource_policy.json','config/train90.txt','config/dev57.txt',
      'config/selection_policy.json','data/data_manifest.json','data/sft_samples.jsonl','data/selected_steps.jsonl','data/sft_schedule_frozen.jsonl','rollout/round_01/pool.json',
      'checks/joint_math.json','checks/pipeline_tests.json','checks/token_mask.json']]
    paths += [ROOT/r['encoded_file'] for r in data['samples']]
    files={str(p.relative_to(ROOT)):sha(p) for p in paths if p.is_file()}
    manifest={'at':now(),'training_config_sha256':sha(ROOT/'config/training_config.json'),'files':files,'trial':trial['last_checkpoint'],
      'initial_adapter_sha256':cfg['model']['adapter_weights_sha256'],'source':'continued same 90-trajectory SFT LoRA; no random adapter'}
    dump(ROOT/'FREEZE.json',manifest)
    update_status('formal_configuration_frozen',batch_count_frozen=True,batches_per_round=n,whole_pool_drift_test_complete=True)
    dump(P/'TRAINING_CONFIG_FROZEN.json',cfg)
    return cfg

def document(stage,body):
    text=f'# 第一轮执行记录\n\n更新时间：{now()}（北京时间）。\n\n状态：{stage}\n\n{body}\n\n仅物理 GPU1；延续原 90 条轨迹 SFT 的同一套 LoRA 参数，基座冻结，原始 adapter 不覆盖。\n\n实时进度：实验 STATUS.json、runtime/round1_run/heartbeat.json；各阶段日志位于 logs/。\n'
    (ROOT/'ROUND_01_RUN.md').write_text(text);(P/'ROUND_01_RUN.md').write_text(text)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--execute',action='store_true');a=ap.parse_args();require(a.execute,'Explicit --execute required')
    if (ROOT/'runtime/finish_current_pool.json').exists():
        os.execv(sys.executable,[sys.executable,'-u',str(ROOT/'scripts/finish_current_pool.py'),'--execute'])
    lock=locked_run();dump(RUN/'supervisor.json',{'at':now(),'pid':os.getpid(),'scope':'through round 1 evaluation; not rounds 2-5'})
    def stop(signum,frame):raise KeyboardInterrupt('Supervisor stopped')
    signal.signal(signal.SIGTERM,stop)
    try:
        if (ROOT/'FREEZE.json').exists():
            from evaluate import validate_freeze
            cfg=validate_freeze()
        else:
            accepted=None
            for tag in ['15','05']:
                chosen=ROOT/f'config/round1_trial_{tag}.json';cfg=read(chosen);out=ROOT/f'smoke/full_pool_{tag}'
                if (out/'drift_rejected.json').exists() or ((out/'final_policy_probe.json').exists() and not read(out/'final_policy_probe.json')['passed']):continue
                document(f'整池 {int(tag)} 批工程试跑', '自动链已启动：完整池试跑通过后冻结配置，再做初始 DEV57、正式第一轮和第一轮 DEV57。正式阶段从原始 A0 重置；试跑不计正式预算。')
                try:
                    run_stage(f'full_pool_trial_{tag}',[TRAIN,'-u',ROOT/'scripts/joint_trainer.py','--config',chosen,'--pool',POOL,
                      '--output',out,'--reference-dir',REF,'--mode','smoke','--execute'],
                      [REF/'progress.json',out/'progress.json',out/'final_policy_probe.json',*list((out/'diagnostics').glob('*.json'))],out)
                except DriftRejected:continue
                trial=audit_round(out,cfg,'smoke');accepted=(chosen,trial);break
            require(accepted is not None,'Both predeclared batch/LR candidates exceeded policy drift limits; formal training not started')
            cfg=freeze(*accepted)
        n=cfg['schedule_candidate']['batches_per_round'];baseline=ROOT/'evaluation/initial'
        document('初始 DEV57 基线',f'完整池检查通过，每轮冻结为 {n} 批。正式第一轮尚未进行；正在评测原始 A0，成绩不用于修改超参数。')
        run_stage('baseline_dev57',[TRAIN,'-u',ROOT/'scripts/evaluate.py','--label','initial','--adapter',cfg['model']['initial_adapter'],'--execute'],
          [baseline/'STATUS.json',*list((baseline/'trajectories').glob('*.partial.json'))])
        out=ROOT/'training/round_01'
        document('正式第一轮',f'初始 DEV57 已完成。每轮 {n} 批，每批联合更新一次；已有 540 条 RL 轨迹和 2,623 个 SFT 步骤各用一遍。')
        run_stage('formal_round_01',[TRAIN,'-u',ROOT/'scripts/joint_trainer.py','--config',ROOT/'config/training_config.json','--pool',POOL,
          '--output',out,'--reference-dir',REF,'--mode','formal','--execute'],[REF/'progress.json',out/'progress.json',out/'final_policy_probe.json'],out)
        trial=audit_round(out,cfg,'formal');adapter=Path(trial['last_checkpoint']);ev=ROOT/'evaluation/round_01'
        document('第一轮 DEV57',f'正式第一轮 {n} 次联合更新已完成，预算验收通过。正在以轮末 adapter 进行同协议 DEV57。')
        run_stage('round01_dev57',[TRAIN,'-u',ROOT/'scripts/evaluate.py','--label','round_01','--adapter',adapter,'--execute'],
          [ev/'STATUS.json',*list((ev/'trajectories').glob('*.partial.json'))])
        before=read(baseline/'SUMMARY.json');after=read(ev/'SUMMARY.json')
        report={'at':now(),'passed':True,'round':1,'optimizer_updates':n,'rl_trajectories':540,'sft_steps':2623,'sft_tokens':205238,
          'adapter':str(adapter),'adapter_sha256':sha(adapter/'adapter_model.safetensors'),'initial_DEV57_successes':before['successes'],
          'round01_DEV57_successes':after['successes'],'next_round_launched':False}
        dump(ROOT/'ROUND_01_COMPLETE.json',report)
        document('第一轮完成',f"共 {n} 次正式联合更新。DEV57：初始 {before['successes']}/57，第一轮 {after['successes']}/57。第 2—5 轮尚未启动。模型：{adapter}")
        update_status('round01_complete',next_step='round02_pool_collection',batch_count_frozen=True,batches_per_round=n)
    except BaseException as error:
        dump(RUN/'ERROR.json',{'at':now(),'error':repr(error),'traceback':traceback.format_exc()})
        update_status('round01_pipeline_error',error=repr(error),next_step='diagnose_preserved_artifacts_then_resume')
        document('执行暂停，保留现场',f'错误：{error!r}。已提交 checkpoint 保留，未跳过任何样本。诊断见 runtime/round1_run/ERROR.json。')
        raise
if __name__=='__main__':main()
