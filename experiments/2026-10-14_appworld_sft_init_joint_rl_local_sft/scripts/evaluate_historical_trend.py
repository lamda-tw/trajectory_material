"""Serial DEV57 evaluation using the byte-identical historical Python launcher.

Only --execute starts GPU work; --prepare builds and audits the isolated inputs.
"""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time
import traceback
from collections import defaultdict
from common import ROOT, WORKSPACE, dump, now, read, require, sha

DEST = ROOT / 'evaluation/historical_protocol_trend'
BASELINE = WORKSPACE / 'experiments/2026-09-21_092504_appworld_qwen3-8b_react_lora_codex_rft_train90_dev57'
A0 = WORKSPACE / 'experiments/2026-09-21_015238_appworld_qwen3-8b_lora_codex_rft_train90_epoch5/artifacts/adapter'
APP_ENV = Path('/root/autodl-tmp/envs/appworld-0.2.0-py312')
VLLM_ENV = Path('/root/autodl-tmp/envs/qwen3-vllm-py312')
SITE = APP_ENV / 'lib/python3.12/site-packages'
MODEL = Path('/root/autodl-tmp/models/Qwen3-8B')
REL = Path('simplified_react_code_agent/alibaba/qwen3-8b-with-reasoning/dev')
CONFIG_REL = Path(str(REL) + '.jsonnet')
ORDER = [0, 1, 5, 10, 15]
GPU = 'GPU-35170b76-56ce-240a-19c0-0c092a3e8501'

def source_adapter(step):
    return A0 if step == 0 else ROOT / f'smoke/full_pool_15/step_{step:05d}'

def stage_root(step):
    return DEST / f'step_{step:05d}'

def output_root(step):
    return stage_root(step) / 'experiments/outputs' / REL

def link(target, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        require(path.resolve() == target.resolve(), f'Changed link: {path}')
    elif path.exists():
        raise ValueError(f'Expected new link: {path}')
    else:
        path.symlink_to(target.resolve(), target_is_directory=target.is_dir())

def normalized_config(path):
    config = read(path)
    config['target_modules'] = sorted(config['target_modules'])
    return config

def prepare():
    DEST.mkdir(parents=True, exist_ok=True)
    snapshot = DEST / 'protocol_snapshot'
    snapshot.mkdir(exist_ok=True)
    # These are preserved verbatim; the historical shell is provenance only (it hardcodes GPU0).
    for name in ('appworld_run_isolated_lora_config.py', 'run_appworld_qwen3_react_lora_full_dev.sh'):
        src = BASELINE / 'scripts_snapshot' / name
        dst = snapshot / name
        if not dst.exists():
            shutil.copy2(src, dst)
        require(sha(src) == sha(dst), f'Historical snapshot changed: {name}')
    historical_config = BASELINE / 'config/agent_configs' / CONFIG_REL
    shutil.copy2(historical_config, snapshot / 'dev.jsonnet')
    (DEST / 'adapters').mkdir(exist_ok=True)
    adapter_inputs = []
    for step in ORDER:
        source = source_adapter(step)
        weight = source / 'adapter_model.safetensors'
        require(normalized_config(source/'adapter_config.json') == normalized_config(A0/'adapter_config.json'), 'LoRA structures differ')
        weight_hash = sha(weight)
        if step:
            record = read(source/'manifest.json')
            require(record['state']['global_update'] == step and record['adapter_sha256'] == weight_hash, f'Checkpoint invalid: {step}')
        else:
            require(weight_hash == read(BASELINE/'manifest.json')['adapter_sha256'], 'A0 identity differs')
        adapter = DEST / 'adapters' / f'step_{step:05d}'
        adapter.mkdir(exist_ok=True)
        # Equal inference metadata/tokenizer for all five; target-module list order is immaterial.
        for src in A0.iterdir():
            if src.is_file() and src.name != 'adapter_model.safetensors':
                link(src, adapter/src.name)
        link(weight, adapter/'adapter_model.safetensors')
        adapter_inputs.append(dict(step=step, source=str(source), adapter=str(adapter), sha256=weight_hash,
                                   source_config_sha256=sha(source/'adapter_config.json')))
        root = stage_root(step)
        for directory in ('logs', 'data/datasets', 'config/agent_configs', 'cache'):
            (root/directory).mkdir(parents=True, exist_ok=True)
        link(SITE/'appworld_agents/configs/_generator', root/'config/agent_configs/_generator')
        config = root/'config/agent_configs'/CONFIG_REL
        config.parent.mkdir(parents=True, exist_ok=True)
        if not config.exists():
            shutil.copy2(historical_config, config)
        require(sha(config) == sha(historical_config), 'Generated config differs from historical snapshot')
        for name in ('CHANGELOG.md', 'LICENSE', 'api_docs', 'base_dbs', 'tasks', 'version.txt'):
            link(BASELINE/'data'/name, root/'data'/name)
        link(BASELINE/'data/datasets/dev.txt', root/'data/datasets/dev.txt')
        if not (root/'cache/tests').exists():
            shutil.copytree(BASELINE/'cache/tests', root/'cache/tests', ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    require(sha(BASELINE/'data/datasets/dev.txt') == read(BASELINE/'manifest.json')['dev_split_sha256'], 'Dev split changed')
    sources = [Path(__file__), ROOT/'scripts/historical_vllm_gpu1.py',
               ROOT/'scripts/vllm_uuid_compat/sitecustomize.py', snapshot/'appworld_run_isolated_lora_config.py',
               snapshot/'dev.jsonnet', A0/'adapter_config.json', MODEL/'config.json', MODEL/'generation_config.json',
               MODEL/'tokenizer_config.json', MODEL/'tokenizer.json',
               SITE/'appworld_agents/prompts/react_code_agent/instructions.txt',
               BASELINE/'data/datasets/dev.txt', BASELINE/'summary.json']
    sources += list((SITE/'appworld_agents/code/simplified').glob('*.py'))
    sources += [SITE/'appworld/cli.py', SITE/'appworld/environment.py', SITE/'appworld/evaluator.py',
                SITE/'appworld/common/background_server.py']
    sources += list((SITE/'appworld_agents/configs/_generator').rglob('*.py'))
    # Freeze base weights too; called once at preparation and independently checked at completion.
    sources += sorted(MODEL.glob('*.safetensors'))
    sources += [p for p in A0.iterdir() if p.is_file() and p.name != 'adapter_model.safetensors']
    manifest = dict(created_at=now(), order=ORDER, physical_gpu_indices=[1], gpu_uuid=GPU,
                    historical_baseline=str(BASELINE), adapters=adapter_inputs,
                    unchanged_historical_launcher=True, unchanged_historical_config=True,
                    allowed_operational_changes=['GPU0 -> fixed GPU1 UUID', 'isolated output/cache paths',
                        'owned-process cleanup instead of broad pkill', 'vLLM NVML UUID-to-physical-index compatibility'],
                    sources=[dict(path=str(p), sha256=sha(p)) for p in sorted(set(sources))])
    if (DEST/'INPUT_MANIFEST.json').exists():
        previous=read(DEST/'INPUT_MANIFEST.json')
        require(previous['sources'] == manifest['sources'] and previous['adapters'] == manifest['adapters'], 'Frozen input identity changed')
    else:
        dump(DEST/'INPUT_MANIFEST.json', manifest)
    # Capture package versions without importing GPU runtimes or capturing credentials.
    for name, env in [('appworld', APP_ENV), ('vllm', VLLM_ENV)]:
        dest=DEST/f'{name}_packages.txt'
        if not dest.exists():
            with dest.open('w') as out:
                subprocess.run([str(env/'bin/python'), '-m', 'pip', 'freeze'], stdout=out, check=True,
                               env={**os.environ, 'CUDA_VISIBLE_DEVICES':''})
    print(json.dumps({'prepared': True, 'directory': str(DEST), 'steps': ORDER}), flush=True)

def environment(step):
    root = stage_root(step)
    env = dict(os.environ, APPWORLD_ROOT=str(root), APPWORLD_CACHE=str(root/'cache'),
               HISTORICAL_STAGE_ROOT=str(root), CUDA_VISIBLE_DEVICES=GPU,
               HF_HOME=str(root/'cache/huggingface'), HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1',
               TOKENIZERS_PARALLELISM='false', PYTHONUNBUFFERED='1', PYTHONDONTWRITEBYTECODE='1',
               NO_API_KEY='none', OPENAI_API_KEY='none',
               VLLM_CACHE_ROOT=str(root/'cache/vllm'), TORCHINDUCTOR_CACHE_DIR=str(root/'cache/torchinductor'),
               XDG_CACHE_HOME=str(root/'cache/xdg'))
    for name in ('HF_HOME','VLLM_CACHE_ROOT','TORCHINDUCTOR_CACHE_DIR','XDG_CACHE_HOME'):
        Path(env[name]).mkdir(parents=True, exist_ok=True)
    return env

def command(step):
    root=stage_root(step)
    return [str(APP_ENV/'bin/python'), str(DEST/'protocol_snapshot/appworld_run_isolated_lora_config.py'),
            '--root',str(root),'--config-root',str(root/'config/agent_configs'),
            '--model-path',str(MODEL),'--adapter-path',str(DEST/'adapters'/f'step_{step:05d}'),
            '--vllm-bin',str(ROOT/'scripts/historical_vllm_gpu1.py'),
            '--model-config-name','qwen3-8b-with-reasoning',
            '--served-adapter-name','appworld-codex-rft-train90-epoch5',
            '--reasoning-parser','none','--per-task-status-path',str(root/'task_status.jsonl')]

def records(step):
    path=stage_root(step)/'task_status.jsonl'
    if not path.exists(): return []
    rows=[]
    for line in path.read_text().splitlines():
        try: rows.append(json.loads(line))
        except json.JSONDecodeError: pass  # Last line may still be in flight.
    return rows

def report(phase, current=None, child_pid=None, error=None):
    points=[]
    for step in ORDER:
        rs=records(step)
        summary_path=stage_root(step)/'SUMMARY.json'
        summary=read(summary_path) if summary_path.exists() else {}
        points.append(dict(step=step, tasks_done=len(rs), successes=sum(r['status']=='success' for r in rs),
                           complete=bool(summary), summary=summary))
    state=dict(at=now(),phase=phase,pid=os.getpid(),child_pid=child_pid,current_step=current,
               total_tasks=285,tasks_done=sum(p['tasks_done'] for p in points),points=points,error=error)
    dump(DEST/'STATUS.json',state)
    lines=['# 同历史协议的 DEV57 训练趋势评测','',f'更新时间：{state["at"]}',
           f'状态：{phase}；当前检查点：{current}；总进度：{state["tasks_done"]}/285。仅物理 GPU1。','',
           '五个点复用历史 Python launcher 与配置，原始 AppWorld agent、Chat Completions、temperature=0、seed=100、最多50步、每次请求3000输出token、32000上下文；单任务串行、vLLM max_num_seqs=3。','',
           '| 更新次数 | 进度 | TGC | SGC | 官方测试通过数 |','| ---: | ---: | ---: | ---: | ---: |']
    for p in points:
        s=p['summary']
        tgc=f'{s["successes"]}/57 = {s["TGC_percent"]:.2f}%' if s else '待完成'
        sgc=f'{s["successful_scenarios"]}/19 = {s["SGC_percent"]:.2f}%' if s else '待完成'
        tests=f'{s["passed_tests"]}/{s["total_tests"]}' if s else '—'
        lines.append(f'| [step {p["step"]}](step_{p["step"]:05d}/task_status.jsonl) | {p["tasks_done"]}/57 | {tgc} | {sgc} | {tests} |')
    if error: lines += ['',f'错误：{error}']
    lines += ['', '历史基线：TGC=23/57、SGC=4/19。step 0 首先检查逐题复现，再进行后续点。',
              '', '[输入与代码哈希](INPUT_MANIFEST.json) · [执行方案](../../HISTORICAL_DEV57_RUN.md)', '']
    (DEST/'RESULTS.md').write_text('\n'.join(lines))

def kill_owned_server(step):
    path=stage_root(step)/'server_owned.json'
    if not path.exists(): return
    info=read(path)
    pid=info['pid']
    proc=Path(f'/proc/{pid}/stat')
    if proc.exists():
        fields=proc.read_text().rsplit(')',1)[1].split()
        require(fields[19] == info['start_ticks'], 'Refusing reused server PID')
        require(os.getpgid(pid)==pid, 'Server is not owned process-group leader')
        try: os.killpg(pid,signal.SIGTERM)
        except ProcessLookupError: pass
        deadline=time.monotonic()+25
        while proc.exists() and time.monotonic()<deadline:
            if proc.read_text().rsplit(')',1)[1].split()[0]=='Z': break
            time.sleep(1)
        if proc.exists() and proc.read_text().rsplit(')',1)[1].split()[0]!='Z':
            os.killpg(pid,signal.SIGKILL)

def validate_live_protocol(step):
    require(sha(stage_root(step)/'config/agent_configs'/CONFIG_REL) == sha(DEST/'protocol_snapshot/dev.jsonnet'),
            'Historical generator produced a different config')
    for p in (output_root(step)/'tasks').glob('*/logs/lm_calls.jsonl'):
        with p.open() as handle: line=handle.readline()
        if not line: continue
        try: first=json.loads(line)
        except json.JSONDecodeError: continue
        historical=BASELINE/'experiments/outputs'/REL/'tasks'/p.parents[1].name/'logs/lm_calls.jsonl'
        with historical.open() as handle: old=json.loads(handle.readline())
        require(first['input']['messages']==old['input']['messages'],f'Initial prompt differs: {p.parents[1].name}')
        for key in ('model','tools','max_completion_tokens','seed','temperature','client_name','api_type'):
            require(first['input'].get(key)==old['input'].get(key), f'Request protocol differs: {key}')

def summarize(step):
    validate_live_protocol(step)
    official=read(output_root(step)/'evaluations/dev.json')
    rs=records(step)
    expected=set((BASELINE/'data/datasets/dev.txt').read_text().split())
    require(len(rs)==57 and {r['task_id'] for r in rs}==expected, 'Incomplete/duplicate task results')
    require(set(official['individual'])==expected, 'Official evaluator task coverage differs')
    require(all(r['status'] in ('success','failed') for r in rs), 'Infrastructure/evaluation error is not a task failure')
    groups=defaultdict(list)
    for r in rs:
        d=official['individual'][r['task_id']]
        require(d['success']==(r['status']=='success') and len(d['passes'])==r['passed_tests'], 'Official/status mismatch')
        groups[r['task_id'].rsplit('_',1)[0]].append(d['success'])
    require(len(groups)==19 and all(len(v)==3 for v in groups.values()), 'Invalid scenario coverage')
    successes=sum(r['status']=='success' for r in rs)
    scenarios=sum(all(v) for v in groups.values())
    result=dict(at=now(),step=step,tasks=57,successes=successes,TGC_percent=100*successes/57,
                scenarios=19,successful_scenarios=scenarios,SGC_percent=100*scenarios/19,
                passed_tests=sum(r['passed_tests'] for r in rs),total_tests=sum(r['num_tests'] for r in rs),
                official_scores=official['aggregate'],initial_messages_exact_match=57,
                adapter_sha256=sha(source_adapter(step)/'adapter_model.safetensors'),
                official_results_sha256=sha(output_root(step)/'evaluations/dev.json'))
    require(round(result['TGC_percent'],1)==official['aggregate']['task_goal_completion'], 'TGC mismatch')
    require(round(result['SGC_percent'],1)==official['aggregate']['scenario_goal_completion'], 'SGC mismatch')
    dump(stage_root(step)/'SUMMARY.json',result)
    with (stage_root(step)/'task_results.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rs[0]));writer.writeheader();writer.writerows(rs)
    if step==0:
        historic=read(BASELINE/'experiments/outputs'/REL/'evaluations/dev.json')['individual']
        changed=[t for t in expected if historic[t]['success']!=official['individual'][t]['success']]
        test_changed=[t for t in expected if historic[t]!=official['individual'][t]]
        dump(DEST/'BASELINE_REPRODUCTION.json',dict(at=now(),same_task_success=not changed,
            changed_task_success_ids=sorted(changed),different_official_records=sorted(test_changed),
            initial_messages_exact_match=57,historical_scores=read(BASELINE/'summary.json')['official_scores'],
            reproduced_scores=official['aggregate']))
        require(not changed and not test_changed, 'A0 differs from historical baseline; inspect before continuing')
    return result

def execute():
    from resources import require_free_gpu
    require(os.environ.get('CUDA_VISIBLE_DEVICES')==GPU, 'Use gpu1_run.py')
    require((DEST/'INPUT_MANIFEST.json').exists(), 'Run --prepare first')
    manifest=read(DEST/'INPUT_MANIFEST.json')
    for source in manifest['sources']:
        require(sha(source['path'])==source['sha256'],f'Frozen source changed: {source["path"]}')
    signal.signal(signal.SIGTERM,lambda *_: (_ for _ in ()).throw(SystemExit('Termination requested')))
    step=None
    child=None
    try:
        for step in ORDER:
            if (stage_root(step)/'SUMMARY.json').exists():
                summarize(step)
                continue
            require_free_gpu(GPU,88)
            # A checkpoint runs from a fresh isolated root. Resume is allowed only for completed tasks.
            argv=command(step)
            with (stage_root(step)/'logs/run.log').open('a') as log:
                child=subprocess.Popen(argv,env=environment(step),stdout=log,stderr=subprocess.STDOUT,
                                       start_new_session=True,cwd=ROOT)
                dump(stage_root(step)/'LAUNCH.json',dict(at=now(),pid=child.pid,argv=argv,gpu_uuid=GPU))
                print(f'{now()} START step={step} pid={child.pid}',flush=True)
                last_done=-1
                while child.poll() is None:
                    validate_live_protocol(step)
                    report('running',step,child.pid)
                    done=len(records(step))
                    if done!=last_done:
                        print(f'{now()} step={step} tasks={done}/57',flush=True);last_done=done
                    time.sleep(10)
                rc=child.returncode
            kill_owned_server(step)
            dump(stage_root(step)/'EXIT.json',dict(at=now(),returncode=rc))
            require(rc==0, f'Historical runner failed at step {step}: {rc}; see its logs/run.log')
            result=summarize(step)
            report('running',step)
            print(f'{now()} COMPLETE step={step} TGC={result["successes"]}/57 SGC={result["successful_scenarios"]}/19',flush=True)
            child=None
            # Release CUDA memory before the next historical server is started.
            deadline=time.monotonic()+60
            while True:
                try: require_free_gpu(GPU,88);break
                except ValueError:
                    if time.monotonic()>deadline: raise
                    time.sleep(3)
        for source in manifest['sources']:
            require(sha(source['path'])==source['sha256'],f'Input changed during evaluation: {source["path"]}')
        report('complete')
        dump(DEST/'COMPLETE.json',dict(at=now(),steps=ORDER,tasks=285,manifest_sha256=sha(DEST/'INPUT_MANIFEST.json'),
             summaries=[read(stage_root(s)/'SUMMARY.json') for s in ORDER]))
    except BaseException as exc:
        dump(DEST/'ERROR.json',dict(at=now(),step=step,error=str(exc),traceback=traceback.format_exc()))
        report('error',step,error=str(exc))
        raise
    finally:
        if child is not None and child.poll() is None:
            os.killpg(child.pid,signal.SIGTERM)
            try: child.wait(timeout=20)
            except subprocess.TimeoutExpired: os.killpg(child.pid,signal.SIGKILL);child.wait()
        if step is not None: kill_owned_server(step)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare',action='store_true')
    parser.add_argument('--execute',action='store_true')
    args=parser.parse_args()
    require(args.prepare != args.execute, 'Choose exactly one of --prepare or --execute')
    if args.prepare: prepare();report('prepared')
    else: execute()

if __name__=='__main__':main()
