#!/usr/bin/env python3
"""Fixed two-epoch prefix experiment; train, verify, then evaluate all 168 tasks."""
import fcntl, hashlib, json, math, os, shlex, shutil, subprocess, sys, time, traceback
from datetime import datetime, timezone
from pathlib import Path
T = Path(__file__).resolve().parent.parent
W = T.parent.parent
M = json.loads((T / 'manifest.json').read_text())
E = Path(M['evaluation_experiment'])
PY = W / '.conda-training/bin/python'
TR = W / '.conda-training/bin/torchrun'
BASE = Path('/root/autodl-tmp/models/Qwen3-8B')
sys.path.insert(0, str(T / 'scripts_snapshot'))
from verify_codex_rft_full_sft_artifacts import model_headers, sha256

def now(): return datetime.now(timezone.utc).isoformat()
def write(path, obj):
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    tmp.replace(path)
def stage(root, status):
    data = json.loads((root / 'manifest.json').read_text())
    data.update(status=status, updated_at_utc=now())
    write(root / 'manifest.json', data)
    (root / 'STATUS.txt').write_text(status + ' updated_at=' + now() + '\n')
    print(now(), root.name, status, flush=True)

env = os.environ.copy()
env.update(CUDA_VISIBLE_DEVICES='0,1', PYTORCH_CUDA_ALLOC_CONF='expandable_segments:True',
    TORCH_NCCL_ASYNC_ERROR_HANDLING='1', TOKENIZERS_PARALLELISM='false',
    HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', OMP_NUM_THREADS='4',
    PYTHONDONTWRITEBYTECODE='1', PYTHONUNBUFFERED='1')
for name, sub in {'TMPDIR':'tmp','TMP':'tmp','TEMP':'tmp', 'XDG_CACHE_HOME':'cache/xdg',
    'HF_HOME':'cache/huggingface','TORCH_HOME':'cache/torch','TRITON_CACHE_DIR':'cache/triton',
    'TORCHINDUCTOR_CACHE_DIR':'cache/inductor','CUDA_CACHE_PATH':'cache/cuda',
    'MPLCONFIGDIR':'cache/matplotlib','NUMBA_CACHE_DIR':'cache/numba'}.items():
    path = T / sub; path.mkdir(parents=True, exist_ok=True); env[name] = str(path)
timing = []
def run(name, command, root=T, extra=None):
    command = list(map(str, command))
    row = dict(stage=name, started_at_utc=now(), command=command)
    timing.append(row); write(T / 'metrics/execution_timing.json', timing)
    with (root / ('logs/' + name + '.log')).open('w') as log:
        result = subprocess.run(command, cwd=W, env=env | (extra or {}), stdout=log, stderr=subprocess.STDOUT)
    row.update(finished_at_utc=now(), exit_code=result.returncode)
    write(T / 'metrics/execution_timing.json', timing)
    if result.returncode: raise RuntimeError(f'{name} failed: exit {result.returncode}')

monitor = None
lock = None
current_root = T
try:
    assert not (T / 'metrics/training_history.jsonl').exists(), 'Refusing to overwrite an existing run'
    assert json.loads((T / 'config/prefix_preflight.json').read_text())['status'] == 'PASS'
    assert shutil.disk_usage(T).free > 45 * 1024**3
    lock = (W / 'tmp/full_sft_gpu.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    used = subprocess.check_output(['nvidia-smi','--query-gpu=memory.used','--format=csv,noheader,nounits'], text=True)
    assert all(int(x.strip()) < 1000 for x in used.splitlines()), used
    stage(T, 'RUNNING_DDP_PROBE')
    write(T / 'config/runtime_environment.json', {k:env[k] for k in env if k in ('CUDA_VISIBLE_DEVICES','OMP_NUM_THREADS','PYTHONDONTWRITEBYTECODE','PYTORCH_CUDA_ALLOC_CONF') or k.endswith(('_CACHE_DIR','_CACHE_PATH','_HOME','OFFLINE')) or k in ('TMPDIR','TMP','TEMP')})
    write(T / 'config/source_hashes.json', {str(x.relative_to(T)):sha256(x) for x in sorted((T/'scripts_snapshot').glob('*')) if x.is_file()})
    monitor = subprocess.Popen([str(PY),str(T/'scripts_snapshot/monitor_full_sft_resources.py'),'--experiment',str(T)], env=env, cwd=W, stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    run('02_ddp_probe',[TR,'--standalone','--nproc_per_node=2',T/'scripts_snapshot/ddp_probe.py'])
    stage(T, 'RUNNING_TRAINING')
    command=[TR,'--standalone','--nproc_per_node=2',T/'scripts_snapshot/full_sft_train_fsdp_scheduled.py',
        '--model',BASE,'--train-json',W/'data/2026-09-21_appworld_codex_rft_qwen3-8b_sft_train90/train.jsonl',
        '--validation-json',T/'config/diagnostic_last_step_per_task.jsonl','--experiment-dir',T,
        '--max-length','40960','--epochs','2','--schedule-steps','2925','--learning-rate','1e-5',
        '--warmup-ratio','0.03','--min-lr-ratio','0.1','--weight-decay','0',
        '--max-grad-norm','1','--seed','20260921','--checkpoint-every','0','--save-every-epoch']
    (T/'command.txt').write_text(shlex.join(map(str,command))+'\n')
    run('04_train_full_sft',command)
    m=json.loads((T/'metrics/metrics.json').read_text()); tr=m['training']
    assert m['status']=='SUCCESS' and tr['epochs_completed']==2 and tr['global_steps']==1170
    assert tr['schedule_steps']==2925 and tr['warmup_steps']==88
    assert m['model']['trainable_parameters']==m['model']['total_parameters']==8190735360
    assert [x['step'] for x in tr['history']]==list(range(1,1171))
    assert all(math.isfinite(x[k]) for x in tr['history'] for k in ('train_loss','grad_norm'))
    assert not list((T/'artifacts').rglob('rank_*.pt'))
    stage(T, 'VERIFYING_MODEL')
    _, base_headers=model_headers(BASE)
    inventory={}
    for relative in ['artifacts/checkpoints/epoch_1_model','artifacts/model']:
        d=T/relative; index,headers=model_headers(d)
        assert set(headers)==set(base_headers)
        assert all(h['shape']==base_headers[k]['shape'] and h['dtype']=='BF16' for k,h in headers.items())
        inventory[relative]={'tensors':len(headers),'parameters':sum(math.prod(h['shape']) for h in headers.values()),
            'files':{x.name:{'bytes':x.stat().st_size,'sha256':sha256(x)} for x in sorted(d.iterdir()) if x.is_file()}}
    write(T/'metrics/model_inventory.json',inventory)
    (T/'metrics/final_model_weights.sha256').write_text(''.join(v['sha256']+'  '+str(T/'artifacts/model'/k)+'\n' for k,v in inventory['artifacts/model']['files'].items() if k.endswith('.safetensors')))
    run('05_generation_verify',[PY,T/'scripts_snapshot/verify_appworld_full_sft_model.py','--model',T/'artifacts/model',
        '--sample-json',T/'config/diagnostic_last_step_per_task.jsonl','--output',T/'metrics/generation_smoke.json',
        '--max-input-length','40960','--max-new-tokens','512'],extra={'CUDA_VISIBLE_DEVICES':'0'})
    assert json.loads((T/'metrics/generation_smoke.json').read_text())['status']=='PASS'
    stage(T, 'TRAINING_COMPLETE_MODEL_VERIFIED')
    monitor.terminate(); monitor.wait(timeout=20); monitor=None
    fcntl.flock(lock,fcntl.LOCK_UN); lock.close(); lock=None
    current_root=E
    stage(E, 'RUNNING_EVALUATION')
    eval_command=['bash',E/'scripts_snapshot/run_appworld_qwen3_react_full_sft_aligned_dev.sh',E,T/'artifacts/model',
        'codex-rft-train90-epoch2-prefix5','qwen3-8b-with-reasoning','-','none','test_normal']
    (E/'command.txt').write_text(shlex.join(map(str,eval_command))+'\n')
    run('01_evaluation_launcher',eval_command,root=E)
    statuses=[json.loads(x) for x in (E/'task_status.jsonl').read_text().splitlines() if x.strip()]
    assert len(statuses)==168 and all(x['status'] in ('success','failed') for x in statuses)
    assert (E/'logs/run_exit_code.txt').read_text().strip()=='0'
    stage(E, 'EVALUATION_COMPLETE_AWAITING_REPORT')
    print('Pipeline completed; official result and report audit remain.',flush=True)
except BaseException as exc:
    stage(current_root, 'FAILED')
    write(current_root/'metrics/pipeline_failure.json',dict(time_utc=now(),error=repr(exc),traceback=traceback.format_exc()))
    raise
finally:
    if monitor is not None:
        monitor.terminate(); monitor.wait(timeout=20)
    if lock is not None:
        fcntl.flock(lock,fcntl.LOCK_UN); lock.close()
