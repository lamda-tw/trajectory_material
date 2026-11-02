"""CPU-only export of committed B metrics. Never imports or changes training code."""
from pathlib import Path
from datetime import datetime
import argparse
import fcntl
import hashlib
import json
import math
import os
import time

os.environ['CUDA_VISIBLE_DEVICES']=''
os.environ['HIP_VISIBLE_DEVICES']=''
os.environ['OMP_NUM_THREADS']='1'
os.environ['TF_CPP_MIN_LOG_LEVEL']='3'

HERE=Path(__file__).resolve().parent
PHASE=HERE.parent
RUN=PHASE/'runs/sft'
EVENTS=HERE/'tensorboard'


def read(path):
    return json.loads(path.read_text())


def write(path,value):
    temporary=path.with_suffix(path.suffix+'.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    temporary.replace(path)


def recorded_steps():
    from tensorboard.backend.event_processing.event_accumulator import EventAccumulator
    if not list(EVENTS.glob('events.out.tfevents.*')):return {'train':set(),'eval':set()}
    reader=EventAccumulator(str(EVENTS),size_guidance={'scalars':0});reader.Reload()
    tags=reader.Tags().get('scalars',[])
    return {kind:{x.step for x in reader.Scalars(tag)} if tag in tags else set()
            for kind,tag in [('train','loss/total'),('eval','eval/dev57_tgc')]}


def pending_events(done):
    events=[]
    mapping={'loss/sft':'sft_loss','loss/sdpo':'sdpo_loss','loss/total':'total_loss',
        'grad/sft_norm':'sft_grad_norm','grad/sdpo_weighted_norm':'weighted_sdpo_grad_norm',
        'grad/total_before_clip':'grad_norm_before_clip','grad/total_after_clip':'grad_norm_after_clip',
        'grad/branch_cosine':'branch_grad_cosine','optimizer/learning_rate':'lr',
        'optimizer/updates':'optimizer_updates','optimizer/clipped':'clipped',
        'optimizer/parameter_delta_norm':'student_parameter_delta_norm',
        'gpu/peak_allocated_GiB':'peak_allocated_gib','gpu/peak_reserved_GiB':'peak_reserved_gib',
        'performance/training_seconds':'seconds','tokens/supervised_response':'supervised_tokens'}
    for path in sorted(list(RUN.glob('batch_*/checkpoint/metrics.json'))):
        completion=path.parent/'COMPLETE.json'
        if not completion.exists():continue
        commit=read(completion);number=commit['batch']
        if number in done['train']:continue
        raw=path.read_bytes()
        assert hashlib.sha256(raw).hexdigest()==commit['files']['metrics.json'], 'Committed metrics checksum mismatch'
        m=json.loads(raw);assert m['arm']=='sft' and m['batch']==number
        values={tag:float(m[key]) for tag,key in mapping.items() if m.get(key) is not None}
        values.update({f'steps/{key}':float(m['counts'].get(key,0)) for key in ['sft','sdpo','mask']})
        assert all(math.isfinite(x) for x in values.values())
        when=datetime.fromisoformat(commit['completed_at']).timestamp()
        events.append((when,'train',number,values))
    for epoch,number in [(i,18*i) for i in range(1,4)]:
        path=RUN/f'epoch_{epoch:02d}_dev57/summary.json'
        if not path.exists() or number in done['eval']:continue
        m=read(path);assert m['tasks']==57 and len(m['results'])==57 and m['checkpoint_batch']==number
        values={'eval/dev57_tgc':m['task_goal_completion'],
                'eval/dev57_macro_test_pass_fraction':m['macro_test_pass_fraction'],
                'eval/dev57_successes':m['successes']}
        report=PHASE/'analysis/lr_summary.json'
        if report.exists():
            behavior=read(report).get('epochs',{}).get(str(epoch),{}).get('behavior',{})
            for key in ['docs_fraction','repeated_docs_fraction','long_loop_tasks','context_limit_tasks','business_api_steps','business_api_tasks','no_python_code_tasks']:
                if key in behavior:values['behavior/'+key]=behavior[key]
        events.append((datetime.fromisoformat(m['completed_at']).timestamp(),'eval',number,values))
    return sorted(events)


def main(watch,interval):
    HERE.mkdir(parents=True,exist_ok=True);EVENTS.mkdir(exist_ok=True)
    with (HERE/'exporter.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        done=recorded_steps()
        from tensorboard.summary.writer.event_file_writer import EventFileWriter
        from tensorboard.compat.proto.event_pb2 import Event
        from tensorboard.compat.proto.summary_pb2 import Summary
        writer=EventFileWriter(str(EVENTS),max_queue_size=10,flush_secs=5)
        try:
            while True:
                try:
                    for when,kind,step,values in pending_events(done):
                        writer.add_event(Event(wall_time=when,step=step,summary=Summary(value=[
                            Summary.Value(tag=tag,simple_value=value) for tag,value in values.items()])))
                        writer.flush();done[kind].add(step)
                        print(json.dumps({'exported':kind,'batch':step,'tags':len(values)}),flush=True)
                    state={'pid':os.getpid(),'updated_at':datetime.now().astimezone().isoformat(),
                        'event_directory':str(EVENTS),'training_batches':sorted(done['train']),
                        'evaluated_batches':sorted(done['eval']),'refresh_seconds':interval,
                        'reads_training_artifacts_only':True,'gpu_used':False}
                    if (PHASE/'STATUS.json').exists():state['training_status']=read(PHASE/'STATUS.json')
                    complete=(RUN/'COMPLETE.json').exists() and len(done['train'])==54 and done['eval']=={18,36,54}
                    state['export_complete']=complete;write(HERE/'status.json',state)
                    if not watch or complete:return
                except (OSError,ValueError,AssertionError,KeyError) as error:
                    print(json.dumps({'export_error':str(error),'time':time.time()}),flush=True)
                    write(HERE/'last_error.json',{'error':str(error),'time':time.time()})
                    if not watch:raise
                time.sleep(interval)
        finally:
            writer.close()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--watch',action='store_true')
    parser.add_argument('--interval',type=int,default=30);args=parser.parse_args()
    assert args.interval>=10
    main(args.watch,args.interval)
