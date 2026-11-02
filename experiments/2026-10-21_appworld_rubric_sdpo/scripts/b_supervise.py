"""Owned mixed-only supervisor: inspect batch 1 before allowing batches 2..36."""
from b_common import *
import argparse
import json
import math
import shutil
import subprocess
import time
import traceback


def validate_checkpoint(number):
    folder=batch_dir('mixed',number)/'checkpoint'
    complete=read(folder/'COMPLETE.json')
    for name,expected in complete['files'].items():
        assert file_sha(folder/name)==expected, name
    m=read(folder/'metrics.json')
    assert m['physical_gpu_uuid']==GPU and not m['teacher_received_gradient']
    for name in ['sft_loss','sdpo_loss','total_loss','sft_grad_norm','weighted_sdpo_grad_norm',
                 'grad_norm_before_clip','grad_norm_after_clip','student_parameter_delta_norm',
                 'peak_allocated_gib','peak_reserved_gib']:
        assert math.isfinite(m[name]), (name,m[name])
    assert m['sdpo_loss']>=-1e-4 and m['sft_loss']>=0
    assert m['grad_norm_after_clip']<=config()['training']['grad_clip_norm']*1.001
    counts=m['counts']
    if number==1:
        assert counts.get('sft',0)>0 and counts.get('sdpo',0)>0, 'First batch must exercise both branches'
        assert m['sft_grad_norm']>0 and m['weighted_sdpo_grad_norm']>0
    if m['optimizer_step_performed']:
        assert m['student_parameter_delta_norm']>0 and m['grad_norm_before_clip']>0
    report={'checked_at':now(),'batch':number,'passed':True,'metrics':m,
            'checkpoint_sha256':file_sha(folder/'COMPLETE.json'),
            'scope':'Technical validity only; this does not establish task quality gains.'}
    write_json(batch_dir('mixed',number)/'acceptance.json',report)
    if number==1:write_json(B/'analysis/first_batch_acceptance.json',report)
    return m


def heartbeat(number,child=None):
    root=run_dir('mixed');folder=batch_dir('mixed',number)
    gpu=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,memory.total,utilization.gpu',
        '--format=csv,noheader,nounits'],text=True,timeout=15)
    row=next(line for line in gpu.splitlines() if GPU in line)
    value={'at':now(),'batch':number,'supervisor_pid':os.getpid(),'child_pid':child.pid if child else None,
           'gpu1':row,'disk_free_gib':shutil.disk_usage(B).free/2**30,
           'stage':read(B/'STATUS.json') if (B/'STATUS.json').exists() else None}
    if (folder/'training_progress.json').exists():value['training']=read(folder/'training_progress.json')
    with (root/'resources.jsonl').open('a') as out:out.write(json.dumps(value,ensure_ascii=False)+'\n')
    write_json(root/'heartbeat.json',value)


def wait_for_resources(number):
    while True:
        authorize('training_allowed')
        assert read(B/'config/execution_gate.json')['automatic_resume']
        assert shutil.disk_usage(B).free>=8*2**30, 'Less than 8 GiB disk free; preserve all checkpoints and stop'
        try:
            require_free_gpu(GPU,config()['server']['minimum_free_gpu_gib'])
            return
        except AssertionError as error:
            status('waiting_for_gpu1',batch=number,reason=str(error))
            heartbeat(number);time.sleep(30)


def wait_for_existing_runner():
    # A supervisor handoff must not interrupt the already authorized current batch.
    with (run_dir('mixed')/'runner.lock').open('a+') as handle:
        while True:
            authorize('training_allowed')
            try:
                fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
                fcntl.flock(handle,fcntl.LOCK_UN)
                return
            except BlockingIOError:
                time.sleep(30)


def evaluate_epoch(number):
    if number not in (18,36):return
    authorize('evaluation_allowed')
    root=run_dir('mixed');folder=root/f'epoch_{number//18:02d}_dev57'
    if not (folder/'summary.json').exists():wait_for_resources(number)
    status('dev57_evaluation',arm='mixed',batch=number,epoch=number//18,training_started=True)
    log=root/f'evaluation_epoch_{number//18:02d}.log'
    with log.open('a') as out:
        child=subprocess.Popen([config()['paths']['training_python'],str(R/'scripts/b_evaluate.py'),
            '--arm','mixed','--batch',str(number)],env=dict(CPU,USE_TORCH='1',USE_TF='0'),
            cwd=R,stdout=out,stderr=subprocess.STDOUT)
        while child.poll() is None:
            heartbeat(number,child);time.sleep(30)
    if child.returncode:raise RuntimeError(f'Epoch {number//18} evaluation failed; inspect {log}')
    summary=read(folder/'summary.json');assert summary['tasks']==57
    print(json.dumps({'event':'dev57_complete','epoch':number//18,'successes':summary['successes'],
        'task_goal_completion':summary['task_goal_completion'],'at':now()}),flush=True)
    from b_report import main as write_report
    write_report()


def main():
    authorize('training_allowed')
    gate=read(B/'config/execution_gate.json')
    assert gate['allowed_arms']==['mixed'] and gate['automatic_resume']
    root=run_dir('mixed');root.mkdir(parents=True,exist_ok=True)
    with (root/'supervisor.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        write_json(root/'supervisor.json',{'pid':os.getpid(),'started_at':now(),'arm':'mixed','until_batch':36})
        wait_for_existing_runner()
        from b_report import main as write_report
        write_report()
        for number in range(1,37):
            folder=batch_dir('mixed',number)
            if (folder/'checkpoint/COMPLETE.json').exists():
                validate_checkpoint(number);evaluate_epoch(number);continue
            if number>1:
                assert read(B/'analysis/first_batch_acceptance.json')['passed']
            for attempt in range(1,5):
                wait_for_resources(number)
                log=root/f'runner_batch_{number:03d}_attempt_{attempt}.log'
                with log.open('a') as output:
                    process=subprocess.Popen([config()['paths']['training_python'],str(R/'scripts/b_run.py'),
                        '--arm','mixed','--until-batch',str(number),'--execute'],
                        env=dict(CPU,USE_TORCH='1',USE_TF='0'),stdout=output,stderr=subprocess.STDOUT,cwd=R)
                    while process.poll() is None:
                        heartbeat(number,process)
                        time.sleep(30)
                heartbeat(number)
                if process.returncode==0:
                    m=validate_checkpoint(number)
                    print(json.dumps({'event':'batch_accepted','at':now(),'batch':number,'metrics':m}),flush=True)
                    write_report()
                    break
                reason=log.read_text()[-12000:]
                # Retry resource/transport interruption only; do not conceal deterministic or numerical failures.
                transient=any(x in reason for x in ['GPU1 is occupied','GPU1 has insufficient free memory',
                    'Resource temporarily unavailable','Connection reset','Connection refused','RemoteDisconnected'])
                if not transient or attempt==4:
                    raise RuntimeError(f'Batch {number} failed; inspect {log}')
                status('infrastructure_retry',batch=number,attempt=attempt,log=str(log))
                for _ in range(4):
                    authorize('training_allowed');time.sleep(30)
            evaluate_epoch(number)
        report=write_report();assert report['complete']
        summary={'completed_at':now(),'arm':'mixed','epochs':2,'batches':36,
                 'optimizer_updates':read(batch_dir('mixed',36)/'checkpoint/COMPLETE.json')['optimizer_updates'],
                 'final_checkpoint':str(batch_dir('mixed',36)/'checkpoint'),'sft_control_run':False,'evaluation_run':True,
                 'dev57_evaluated_batches':[18,36],'report':str(B/'REPORT.md')}
        write_json(root/'COMPLETE.json',summary);status('mixed_training_and_dev57_complete',**summary)
        current=read(R/'STATUS.json');current.update(phase_b_started=True,phase_b_completed=True,
            phase_b_status=str(B/'STATUS.json'),training_started=True,training_updates=summary['optimizer_updates'],updated_at=now())
        write_json(R/'STATUS.json',current)
        print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    if not args.execute:raise PermissionError('Use --execute only with recorded user authorization')
    try:main()
    except Exception as error:
        status('supervisor_needs_attention',error=str(error),supervisor_pid=os.getpid())
        traceback.print_exc();raise
